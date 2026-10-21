import logging

import voyageai
import voyageai.error

from app.core.config import settings

logger = logging.getLogger(__name__)

# Products and queries MUST use the same model, or their vectors aren't comparable.
# voyage-4 returns 1024 numbers — must match VECTOR(1024) on Product.embedding.
MODEL = "voyage-4"

# Fail fast (no retries, short timeout): these calls run inside API requests,
# and a missing vector is recoverable later via the backfill script.
_client = voyageai.Client(api_key=settings.voyage_api_key, max_retries=0, timeout=10)


class EmbeddingError(Exception):
    """Raised when Voyage could not return a vector."""


def product_text(title: str, description: str | None) -> str:
    """One product = one text = one vector."""
    return f"{title}\n{description}" if description else title


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    try:
        result = _client.embed(texts, model=MODEL, input_type=input_type)
    except voyageai.error.VoyageError as e:
        logger.error("Voyage embedding error: %s", e)
        raise EmbeddingError from e
    return result.embeddings


def embed_document(text: str) -> list[float]:
    """Vector for a product (stored in the DB)."""
    return _embed([text], input_type="document")[0]


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Batch version: many products in ONE request (used by the backfill)."""
    return _embed(texts, input_type="document")


def embed_query(text: str) -> list[float]:
    """Vector for a search query (compared against stored product vectors)."""
    return _embed([text], input_type="query")[0]
