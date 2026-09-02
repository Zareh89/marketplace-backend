import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ProductCreate(BaseModel):
    title: str
    description: str | None = None
    price: Decimal
    stock: int = 0


class ProductUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    price: Decimal | None = None
    stock: int | None = None


class ProductRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    price: Decimal
    stock: int
    seller_id: uuid.UUID
    image_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductPage(BaseModel):
    items: list[ProductRead]
    total: int
