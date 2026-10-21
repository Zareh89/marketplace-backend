import json
import logging

import anthropic
from anthropic import beta_tool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.embeddings import EmbeddingError, embed_query
from app.models.product import Product

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"
# Safety net for cost/latency. Normal questions take 1-3 steps; the runner stops
# SILENTLY at the limit, so we check stop_reason afterwards.
MAX_STEPS = 8
SEARCH_RESULTS = 5

SYSTEM_PROMPT = (
    "You are a shopping assistant for an online marketplace. "
    "When the buyer is looking for a product, call search_products BEFORE answering — "
    "never reply that you are searching, because the buyer only sees your final answer "
    "and cannot wait for a second message. "
    "Recommend ONLY products the tool returns — "
    "never invent products, prices or specs, because buyers will order what you name. "
    "Skip results that don't fit what the buyer asked for. "
    "Prices are in US dollars. "
    "Answer in the buyer's language, briefly."
)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


class AssistantError(Exception):
    """Raised when the agent could not produce a usable answer."""


class _AgentReply(BaseModel):
    """Structured output the model must end with (API-enforced schema)."""

    answer: str  # text shown to the buyer
    product_ids: list[str]  # ids (from search results) of the products you recommend


def ask_assistant(question: str, db: Session) -> tuple[str, list[Product]]:
    # Ids the search tool actually returned during THIS conversation.
    # Used to drop any id the model might invent.
    seen_ids: set[str] = set()
    searches: list[str] = []  # queries the model searched for — for the log line below

    @beta_tool
    def search_products(query: str, max_price: float | None = None) -> str:
        """Search the marketplace catalog by meaning. Call this whenever the buyer
        describes something they want to find or buy.

        Args:
            query: What the buyer is looking for, e.g. "warm winter jacket".
            max_price: Upper price limit in dollars, only if the buyer gave one.
        """
        searches.append(query)
        try:
            query_vector = embed_query(query)
        except EmbeddingError:
            # Tell the model instead of crashing; it will explain this to the buyer.
            return "Search is temporarily unavailable. Ask the buyer to try again later."
        # In-stock only: recommending something the buyer can't order is useless.
        q = db.query(Product).filter(Product.embedding.is_not(None), Product.stock > 0)
        if max_price is not None:
            q = q.filter(Product.price <= max_price)
        products = q.order_by(Product.embedding.cosine_distance(query_vector)).limit(SEARCH_RESULTS).all()
        seen_ids.update(str(p.id) for p in products)
        return json.dumps(
            [{"id": str(p.id), "title": p.title, "price": str(p.price), "description": p.description} for p in products],
            ensure_ascii=False,
        )

    runner = _client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4000,
        max_iterations=MAX_STEPS,
        system=SYSTEM_PROMPT,
        tools=[search_products],
        output_format=_AgentReply,
        messages=[{"role": "user", "content": question}],
    )

    steps = 0
    try:
        final = None
        for message in runner:
            final = message
            steps += 1
    except anthropic.APIError as e:
        logger.error("Claude API error in assistant: %s", e)
        raise AssistantError from e

    if final is None or final.stop_reason != "end_turn" or final.parsed_output is None:
        logger.error("Assistant did not finish: stop_reason=%s", final and final.stop_reason)
        raise AssistantError

    reply = final.parsed_output
    # Keep only ids the search really returned, in the order the model gave them.
    valid_ids = [pid for pid in reply.product_ids if pid in seen_ids]
    # One line per question: lets us spot "answered without searching" in Cloud Run logs.
    logger.info(
        "assistant: steps=%d searches=%s recommended=%d dropped_ids=%d",
        steps, searches, len(valid_ids), len(reply.product_ids) - len(valid_ids),
    )
    by_id = {str(p.id): p for p in db.query(Product).filter(Product.id.in_(valid_ids)).all()} if valid_ids else {}
    return reply.answer, [by_id[pid] for pid in valid_ids if pid in by_id]
