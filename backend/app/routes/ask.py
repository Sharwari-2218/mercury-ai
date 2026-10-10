"""'All' mode on the Ask page: one question across every document and wiki."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.rag import answer_question
from app.rag.config import DEFAULT_COLLECTION

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    department: str | None = None
    detail: Literal["auto", "short", "detailed"] = "auto"


@router.post("/ask")
def ask_all(req: AskRequest):
    # Docs and wikis share DEFAULT_COLLECTION (separated by `type`), so no type
    # filter here means "search everything". GitHub repos live in their own
    # collections and are queried through GitTalk.
    where = {"department": req.department} if req.department else None
    return answer_question(req.question, DEFAULT_COLLECTION, where, detail=req.detail)
