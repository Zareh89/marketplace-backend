import json
import logging
from dataclasses import dataclass
from typing import Any

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


@dataclass
class AssistantResult:
    answer: str
    products: list[Product]
    # Everything this turn added to the conversation (the question, every model
    # message incl. thinking/tool_use blocks, every tool_result) — to be appended
    # to the stored history exactly as-is.
    new_messages: list[dict[str, Any]]


def count_questions(messages: list[dict[str, Any]]) -> int:
    """Buyer questions in a history. tool_result turns are also role=user but
    carry a list of blocks; the buyer's own questions are plain strings."""
    return sum(1 for m in messages if m["role"] == "user" and isinstance(m["content"], str))


def _to_json_message(message: Any) -> dict[str, Any]:
    """A model message as plain JSON for the JSONB history column.

    to_param() keeps blocks as SDK (pydantic) objects, which Postgres can't store.
    `parsed_output` is an SDK-only field the API would reject when replayed.
    """
    param = message.to_param()
    blocks = [
        {k: v for k, v in b.to_dict(exclude_none=True).items() if k != "parsed_output"}
        if isinstance(b, BaseModel)
        else b
        for b in param["content"]
    ]
    return {"role": param["role"], "content": blocks}


def _ids_returned_in(messages: list[dict[str, Any]]) -> set[str]:
    """Product ids our search tool returned in earlier turns of this conversation."""
    ids: set[str] = set()
    for m in messages:
        if m["role"] != "user" or isinstance(m["content"], str):
            continue
        for block in m["content"]:
            if block.get("type") == "tool_result" and isinstance(block.get("content"), str):
                try:
                    ids.update(p["id"] for p in json.loads(block["content"]))
                except (ValueError, TypeError, KeyError):
                    pass  # e.g. the "search unavailable" text
    return ids


def ask_assistant(question: str, history: list[dict[str, Any]], db: Session) -> AssistantResult:
    # Ids the search tool actually returned in THIS conversation (earlier turns
    # included — "which of those is warmer?" may answer without a new search).
    # Used to drop any id the model might invent.
    seen_ids: set[str] = _ids_returned_in(history)
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

    question_message = {"role": "user", "content": question}
    new_messages: list[dict[str, Any]] = [question_message]

    runner = _client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4000,
        max_iterations=MAX_STEPS,
        system=SYSTEM_PROMPT,
        tools=[search_products],
        output_format=_AgentReply,
        messages=[*history, question_message],
    )

    steps = 0
    try:
        final = None
        for message in runner:
            final = message
            steps += 1
            # Record the model's message exactly as the API expects it back.
            new_messages.append(_to_json_message(message))
            if message.stop_reason == "tool_use":
                # Runs our tool now; the SDK caches the result, so the runner
                # reuses it on the next step instead of calling the tool twice.
                tool_results = runner.generate_tool_call_response()
                if tool_results is not None:
                    new_messages.append(tool_results)
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
    return AssistantResult(
        answer=reply.answer,
        products=[by_id[pid] for pid in valid_ids if pid in by_id],
        new_messages=new_messages,
    )
