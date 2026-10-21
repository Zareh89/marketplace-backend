"""Fill in missing product vectors (old products, or ones saved while Voyage was down).

Run: make backfill-embeddings
"""

from app.core.embeddings import embed_documents, product_text
from app.db.session import SessionLocal
from app.models.product import Product
from app.models.user import User  # noqa: F401 — registers User so Product.seller resolves

# Products per Voyage request. Batching = one request for many texts,
# which matters with the 3 requests/minute limit on accounts without a card.
BATCH_SIZE = 100


def main() -> None:
    db = SessionLocal()
    try:
        products = db.query(Product).filter(Product.embedding.is_(None)).all()
        print(f"Products without a vector: {len(products)}")

        for start in range(0, len(products), BATCH_SIZE):
            batch = products[start : start + BATCH_SIZE]
            vectors = embed_documents([product_text(p.title, p.description) for p in batch])
            for product, vector in zip(batch, vectors):
                product.embedding = vector
            db.commit()  # commit per batch: a later failure doesn't lose finished work
            print(f"  saved {start + len(batch)}/{len(products)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
