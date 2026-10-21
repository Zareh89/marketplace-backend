import uuid

from pydantic import BaseModel, Field

from app.schemas.product import ProductRead


class AssistantQuestion(BaseModel):
    # Length cap: every character becomes paid input tokens on every agent step.
    question: str = Field(min_length=1, max_length=500)
    # Omit to start a new conversation; send back the id from the previous answer to continue it.
    conversation_id: uuid.UUID | None = None


class AssistantAnswer(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    products: list[ProductRead]
