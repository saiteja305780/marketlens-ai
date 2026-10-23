from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import require_api_key
from app.api.deps import DbSession
from app.assistant.service import AssistantAnswer, ask

router = APIRouter(prefix="/assistant", tags=["assistant"], dependencies=[Depends(require_api_key)])


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=300)


@router.post("/ask", response_model=AssistantAnswer)
def ask_question(body: AskBody, db: DbSession):
    """Ask about listings in plain English. Answers come from read-only tools over the database; the
    arguments used are returned so every number can be traced."""
    return ask(db, body.question)
