import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssistantRequest(Base):
    """One row per question sent to the assistant — the daily rate limit counts these.

    Separate from conversations on purpose: "New chat" starts a fresh conversation,
    so a per-conversation counter alone can't cap what one user costs us per day.
    """

    __tablename__ = "assistant_requests"
    # The limit query is "this user's rows newer than X" — one index covers both columns.
    __table_args__ = (Index("ix_assistant_requests_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
