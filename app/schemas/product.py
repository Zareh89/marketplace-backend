import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ProductCreate(BaseModel):
    title: str
    description: str | None = None
    price: Decimal
    stock: int = 0


class ProductRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    price: Decimal
    stock: int
    seller_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
