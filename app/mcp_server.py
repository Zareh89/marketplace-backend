"""Public MCP server: lets any MCP client (claude.ai, Claude Desktop, Claude Code…)
search the catalog. Served by the main FastAPI app at /mcp (see main.py).

Read-only on purpose (decided): no auth, and no write tools like
flag_suspicious_product — we don't control the agents that call this.
"""

import uuid
from datetime import datetime, timedelta, timezone

from mcp.server import MCPServer
from sqlalchemy import func

from app.core.config import settings
from app.core.embeddings import EmbeddingError
from app.core.search import search_in_stock
from app.db.session import SessionLocal
from app.models.mcp_search_call import McpSearchCall
from app.models.product import Product
from app.models.user import User  # noqa: F401 — registers User so Product.seller resolves

mcp = MCPServer("Marketplace")

MAX_RESULTS = 10

# Shared by ALL MCP users (see McpSearchCall). Only search is limited: it calls
# Voyage; get_product is a plain DB read.
SEARCH_LIMIT_PER_MINUTE = 20


def _product_dict(p: Product) -> dict:
    return {
        "id": str(p.id),
        "title": p.title,
        "price_usd": str(p.price),
        "in_stock": p.stock,
        "description": p.description,
        "image_url": p.image_url,
        # A link the person can open to buy — the whole point of shopping via Claude.
        "url": f"{settings.frontend_url}/products/{p.id}",
    }


@mcp.tool()
def search_products(query: str, max_price: float | None = None) -> list[dict] | str:
    """Search this marketplace's catalog by meaning (in-stock products only).
    Use it whenever the user wants to find or buy something here. Each result
    has a `url` to the product page — share it so the user can buy.

    Args:
        query: What the user is looking for, e.g. "warm winter jacket".
        max_price: Upper price limit in US dollars, only if the user gave one.
    """
    db = SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(minutes=1)
        recent = (
            db.query(func.count(McpSearchCall.id))
            .filter(McpSearchCall.created_at > since)
            .scalar()
        )
        if recent >= SEARCH_LIMIT_PER_MINUTE:
            # Same style as the EmbeddingError branch: a readable text result
            # the calling model can relay ("try again in a minute").
            return "Search is busy right now. Try again in a minute."
        db.add(McpSearchCall())
        db.commit()
        return [_product_dict(p) for p in search_in_stock(db, query, max_price, MAX_RESULTS)]
    except EmbeddingError:
        return "Search is temporarily unavailable. Try again in a minute."
    finally:
        db.close()


@mcp.tool()
def get_product(product_id: str) -> dict | str:
    """Full details of one product from this marketplace, by the id returned by search_products.

    Args:
        product_id: The product id from search_products results.
    """
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        return "Invalid product id."
    db = SessionLocal()
    try:
        product = db.get(Product, pid)
        return _product_dict(product) if product else "Product not found."
    finally:
        db.close()
