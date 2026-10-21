from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.assistant import AssistantError, ask_assistant
from app.db.session import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.assistant import AssistantAnswer, AssistantQuestion

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAnswer)
def ask(
    payload: AssistantQuestion,
    # Logged-in users only: every question costs Claude tokens.
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantAnswer:
    try:
        answer, products = ask_assistant(payload.question, db)
    except AssistantError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant could not answer right now. Please try again.",
        )
    return AssistantAnswer(answer=answer, products=products)
