import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductReport(Base):
    """A suspicious-product report filed by the AI assistant for a human moderator.

    A report changes nothing by itself (product stays visible) — so a tricked
    agent can at worst create extra work for a moderator, never harm a seller.
    """

    __tablename__ = "product_reports"
    # One report per product per conversation: repeated calls don't pile up.
    __table_args__ = (UniqueConstraint("product_id", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # CASCADE: deleting a product (DELETE /products/{id}) also deletes its reports
    # instead of failing on the foreign key.
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
