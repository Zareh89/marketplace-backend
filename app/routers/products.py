import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.storage import delete_product_image, upload_product_image
from app.db.session import get_db
from app.models.product import Product
from app.models.user import User, UserRole
from app.routers.auth import get_current_user
from app.schemas.product import ProductCreate, ProductPage, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])


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
    product = Product(**product_in.model_dump(), seller_id=current_user.id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


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
    if search:
        query = query.filter(Product.title.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(Product.created_at.desc()).offset(offset).limit(limit).all()
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
    for field, value in product_update.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
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
