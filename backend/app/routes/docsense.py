"""Docsense: upload a document and ask questions about it. (Databloom lives in databloom.py.)"""
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import ingest_department, require_type, scope_filter
from app.database import get_db
from app.models import User
from app.rag import answer_question, ingest_file
from app.rag.config import DEFAULT_COLLECTION, UPLOAD_DIR
from app.rag.ingest import load_chunks
from app.rag.search import matches

router = APIRouter(tags=["docsense"])

ALLOWED = {".pdf", ".docx", ".txt", ".md"}


@router.post("/docsense/upload")
async def upload(
    file: UploadFile = File(...),
    department: str | None = Form(None),   # admins only: another department, or "all"
    user: User = Depends(require_type("doc")),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported file type {ext}. Allowed: {sorted(ALLOWED)}")

    doc_id = uuid.uuid4().hex[:12]
    dest = UPLOAD_DIR / f"{doc_id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        result = ingest_file(
            dest,
            DEFAULT_COLLECTION,
            {
                "source": file.filename,
                "type": "doc",
                "department": ingest_department(user, department),
                "uploaded_by": user.email,   # from the login, never the form
                "doc_id": doc_id,
            },
        )
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not ingest file: {e}")

    return {"doc_id": doc_id, "filename": file.filename, **result}


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    doc_id: str | None = None      # restrict to one document by id
    file: str | None = None        # ...or by file name (what the Ask page sends)
    department: str | None = None
    detail: Literal["auto", "short", "detailed"] = "auto"


@router.post("/docsense/ask")
def ask(req: AskRequest, user: User = Depends(require_type("doc")), db: Session = Depends(get_db)):
    where = scope_filter(
        user, db,
        type="doc",
        doc_id=req.doc_id,
        source=None if req.doc_id else req.file,
        department=req.department,
    )
    return answer_question(req.question, DEFAULT_COLLECTION, where, detail=req.detail)


@router.get("/docsense/files")
def files(user: User = Depends(require_type("doc")), db: Session = Depends(get_db)):
    """Documents this user may see, newest first, for the Ask page's document picker."""
    where = scope_filter(user, db, type="doc")
    seen: dict[str, dict] = {}
    for c in load_chunks(DEFAULT_COLLECTION):
        m = c["metadata"]
        if m.get("source") and matches(m, where):
            seen[m["source"]] = {"file": m["source"], "name": m["source"], "doc_id": m.get("doc_id")}
    return list(reversed(seen.values()))
