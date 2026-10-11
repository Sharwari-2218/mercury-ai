"""'All' mode on the Ask page: one question across every document and wiki."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, scope_filter
from app.database import get_db
from app.models import User
from app.rag import answer_question
from app.rag.config import DEFAULT_COLLECTION

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    department: str | None = None
    detail: Literal["auto", "short", "detailed"] = "auto"


@router.post("/ask")
def ask_all(req: AskRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Docs and wikis share DEFAULT_COLLECTION (separated by `type`). The filter
    # limits results to the types and departments this user may see. GitHub repos
    # live in their own collections and are queried through GitTalk.
    where = scope_filter(user, db, department=req.department)
    return answer_question(req.question, DEFAULT_COLLECTION, where, detail=req.detail)
