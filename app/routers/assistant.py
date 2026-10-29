import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.assistant import AssistantError, ask_assistant, count_questions
from app.db.session import get_db
from app.models.assistant_conversation import AssistantConversation
from app.models.assistant_request import AssistantRequest
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.assistant import AssistantAnswer, AssistantQuestion

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Session memory rules (product decisions): a conversation lives 24h after its
# last message and holds at most 20 buyer questions. History is append-only
# (Haiku 5.5 thinking blocks), so we can't trim it — a full chat must restart.
SESSION_TTL = timedelta(hours=24)
MAX_QUESTIONS = 20

# Per-user cost cap across ALL conversations ("New chat" resets MAX_QUESTIONS).
# Sliding window over assistant_requests, not a calendar day.
DAILY_QUESTION_LIMIT = 50
RATE_LIMIT_WINDOW = timedelta(hours=24)


def count_recent_requests(user: User, db: Session) -> int:
    since = datetime.now(timezone.utc) - RATE_LIMIT_WINDOW
    return (
        db.query(func.count(AssistantRequest.id))
        .filter(AssistantRequest.user_id == user.id, AssistantRequest.created_at > since)
        .scalar()
    )


def get_conversation(
    conversation_id: uuid.UUID | None, current_user: User, db: Session
) -> AssistantConversation:
    """The user's live conversation, or a fresh one if none/expired."""
    if conversation_id is not None:
        conversation = db.get(AssistantConversation, conversation_id)
        # Someone else's id looks exactly like a missing one — don't reveal it exists.
        if conversation is None or conversation.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if datetime.now(timezone.utc) - conversation.updated_at < SESSION_TTL:
            return conversation
    conversation = AssistantConversation(user_id=current_user.id, messages=[])
    db.add(conversation)
    # Flush = INSERT now (not committed yet) so the row exists and has its id —
    # reports filed during this turn point at it via a foreign key.
    db.flush()
    return conversation


@router.post("/ask", response_model=AssistantAnswer)
def ask(
    payload: AssistantQuestion,
    # Logged-in users only: every question costs Claude tokens.
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantAnswer:
    # Checked first, so a rejected request doesn't even create a conversation.
    if count_recent_requests(current_user, db) >= DAILY_QUESTION_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You've reached today's assistant limit. Please try again later.",
        )

    conversation = get_conversation(payload.conversation_id, current_user, db)
    if count_questions(conversation.messages) >= MAX_QUESTIONS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This chat is full. Please start a new chat.",
        )

    # Committed BEFORE the model call: a failed call (502 below) must still count,
    # or a flaky API would let tokens burn unlimited. Bonus: the first model call no
    # longer runs inside an open transaction (Neon idle-in-transaction timeout) —
    # though the first tool query opens a new one until the final commit.
    db.add(AssistantRequest(user_id=current_user.id))
    db.commit()

    try:
        result = ask_assistant(payload.question, conversation.messages, conversation.id, db)
    except AssistantError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant could not answer right now. Please try again.",
        )

    # Assign a NEW list (not .extend) so SQLAlchemy notices the JSONB change.
    conversation.messages = [*conversation.messages, *result.new_messages]
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    return AssistantAnswer(
        conversation_id=conversation.id,
        answer=result.answer,
        products=result.products,
    )
