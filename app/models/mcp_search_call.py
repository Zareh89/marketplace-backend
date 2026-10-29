import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class McpSearchCall(Base):
    """One row per MCP search_products call — a GLOBAL rate limit counts these.

    Global, not per-IP: every claude.ai user reaches us from Anthropic's servers
    (Cloud Run logs show the same address for all of them), so per-IP would make
    them one client. What we protect is the shared Voyage key — site search too.
    """

    __tablename__ = "mcp_search_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
        default=lambda: datetime.now(timezone.utc),
    )
