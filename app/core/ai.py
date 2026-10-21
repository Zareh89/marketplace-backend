import base64
import logging

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cheapest model; good enough for short product descriptions.
MODEL = "claude-haiku-5-5"

SYSTEM_PROMPT = (
    "You write product descriptions for an online marketplace. "
    "Buyers mostly read on their phones, so keep it to 2-3 short sentences. "
    "Only describe what the seller gave you — never invent specs like size, "
    "material or brand, because a wrong spec leads to returns and complaints. "
    "If the details are limited, write a shorter description rather than "
    "mentioning what's missing — the seller publishes this text as their own. "
    "Write in the same language as the product title."
)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


class AIGenerationError(Exception):
    """Raised when Claude could not produce a usable description."""


def generate_product_description(
    title: str, image: bytes | None, media_type: str | None
) -> str:
    content: list[dict] = []
    if image is not None:
        # Image before text — the vision docs say Claude works best in that order.
        image_b64 = base64.standard_b64encode(image).decode("utf-8")
        content.append(
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}}
        )
    content.append({"type": "text", "text": f"<title>{title}</title>"})

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError as e:
        # The SDK already retried 429/5xx twice; any error here is final for this request.
        logger.error("Claude API error: %s", e)
        raise AIGenerationError from e

    if response.stop_reason != "end_turn":
        logger.error("Unexpected stop_reason: %s", response.stop_reason)
        raise AIGenerationError

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise AIGenerationError
    return text
