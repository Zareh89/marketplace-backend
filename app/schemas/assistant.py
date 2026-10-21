from pydantic import BaseModel, Field

from app.schemas.product import ProductRead


class AssistantQuestion(BaseModel):
    # Length cap: every character becomes paid input tokens on every agent step.
    question: str = Field(min_length=1, max_length=500)


class AssistantAnswer(BaseModel):
    answer: str
    products: list[ProductRead]
