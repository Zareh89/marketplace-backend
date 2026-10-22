from sqlalchemy.orm import Session

from app.core.embeddings import embed_query
from app.models.product import Product


def search_in_stock(db: Session, query: str, max_price: float | None, limit: int) -> list[Product]:
    """Semantic product search shared by the assistant and the MCP server.

    In-stock only (recommending something the buyer can't order is useless) and
    only products that already have a vector. Raises EmbeddingError if Voyage fails.
    """
    q = db.query(Product).filter(Product.embedding.is_not(None), Product.stock > 0)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)
    return q.order_by(Product.embedding.cosine_distance(embed_query(query))).limit(limit).all()
