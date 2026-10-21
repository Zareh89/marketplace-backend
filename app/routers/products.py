import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.ai import AIGenerationError, generate_product_description
from app.core.embeddings import EmbeddingError, embed_document, embed_query, product_text
from app.core.storage import delete_product_image, upload_product_image
from app.db.session import get_db
from app.models.product import Product
from app.models.user import User, UserRole
from app.routers.auth import get_current_user
from app.schemas.product import (
    ProductCreate,
    ProductDescription,
    ProductPage,
    ProductRead,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])

# Formats Claude's vision accepts.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
# Claude's limit is 10 MB base64; base64 adds ~33%, so 5 MB raw leaves headroom.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# Semantic search ranks EVERY product, so we cap how far down the ranking we go.
MAX_SEARCH_RESULTS = 50


def get_current_seller(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.seller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only sellers can perform this action",
        )
    return current_user


def get_own_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Product:
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this product",
        )
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    product_in: ProductCreate,
    current_user: User = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Product:
    product = Product(
        **product_in.model_dump(),
        seller_id=current_user.id,
        embedding=build_embedding(product_in.title, product_in.description),
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def build_embedding(title: str, description: str | None) -> list[float] | None:
    # None if Voyage fails: the product still saves, and the backfill script
    # fills the vector in later.
    try:
        return embed_document(product_text(title, description))
    except EmbeddingError:
        return None


@router.post("/generate-description", response_model=ProductDescription)
def generate_description(
    title: str = Form(...),
    image: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_seller),
) -> ProductDescription:
    image_bytes = None
    media_type = None
    if image is not None:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Image must be JPEG, PNG, GIF or WebP",
            )
        image_bytes = image.file.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Image must be 5 MB or smaller",
            )
        media_type = image.content_type

    try:
        description = generate_product_description(title, image_bytes, media_type)
    except AIGenerationError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate a description. Please try again.",
        )
    return ProductDescription(description=description)


@router.get("/mine", response_model=list[ProductRead])
def list_my_products(
    current_user: User = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> list[Product]:
    return (
        db.query(Product)
        .filter(Product.seller_id == current_user.id)
        .order_by(Product.created_at.desc())
        .all()
    )


@router.get("", response_model=ProductPage)
def list_products(
    search: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ProductPage:
    query = db.query(Product)
    if not search:
        # No search text: newest first, and no Voyage call.
        total = query.count()
        items = query.order_by(Product.created_at.desc()).offset(offset).limit(limit).all()
        return ProductPage(items=items, total=total)

    title_match = Product.title.ilike(f"%{search}%")
    try:
        query_vector = embed_query(search)
    except EmbeddingError:
        # Voyage down or rate-limited: degrade to the old title search instead of failing.
        query = query.filter(title_match)
        total = query.count()
        items = query.order_by(Product.created_at.desc()).offset(offset).limit(limit).all()
        return ProductPage(items=items, total=total)

    # Hybrid ranking: exact title matches first, then everything else by meaning.
    query = query.filter(Product.embedding.is_not(None))
    total = min(query.count(), MAX_SEARCH_RESULTS)
    window = max(0, min(limit, MAX_SEARCH_RESULTS - offset))
    items = (
        query.order_by(title_match.desc(), Product.embedding.cosine_distance(query_vector))
        .offset(offset)
        .limit(window)
        .all()
    )
    return ProductPage(items=items, total=total)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> Product:
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_update: ProductUpdate,
    product: Product = Depends(get_own_product),
    db: Session = Depends(get_db),
) -> Product:
    changes = product_update.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(product, field, value)
    # Only text changes alter the meaning; price/stock edits keep the old vector.
    # On failure we store None rather than keep a vector of the old text.
    if "title" in changes or "description" in changes:
        product.embedding = build_embedding(product.title, product.description)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product: Product = Depends(get_own_product),
    db: Session = Depends(get_db),
) -> None:
    if product.image_url:
        delete_product_image(product.image_url)
    db.delete(product)
    db.commit()


@router.post("/{product_id}/image", response_model=ProductRead)
def upload_image(
    file: UploadFile = File(...),
    product: Product = Depends(get_own_product),
    db: Session = Depends(get_db),
) -> Product:
    if product.image_url:
        delete_product_image(product.image_url)
    product.image_url = upload_product_image(file.file, file.content_type)
    db.commit()
    db.refresh(product)
    return product
