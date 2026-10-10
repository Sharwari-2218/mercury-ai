"""Docsense: upload a document and ask questions about it. (Databloom lives in databloom.py.)"""
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.rag import answer_question, ingest_file
from app.rag.ingest import load_chunks
from app.rag.config import DEFAULT_COLLECTION, UPLOAD_DIR

router = APIRouter(tags=["docsense"])

ALLOWED = {".pdf", ".docx", ".txt", ".md"}


@router.post("/docsense/upload")
async def upload(
    file: UploadFile = File(...),
    department: str = Form("general"),
    uploaded_by: str = Form("anonymous"),
):
    ext = Path(file.filename).suffix.lower()
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
                "department": department,
                "uploaded_by": uploaded_by,
                "doc_id": doc_id,
            },
        )
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not ingest file: {e}")

    return {"doc_id": doc_id, "filename": file.filename, **result}


class AskRequest(BaseModel):
    question: str
    doc_id: str | None = None      # restrict to one document by id
    file: str | None = None        # ...or by file name (what the Ask page sends)
    department: str | None = None
    detail: Literal["auto", "short", "detailed"] = "auto"


@router.post("/docsense/ask")
def ask(req: AskRequest):
    where = {"type": "doc"}
    if req.doc_id:
        where["doc_id"] = req.doc_id
    elif req.file:
        where["source"] = req.file
    if req.department:
        where["department"] = req.department
    return answer_question(req.question, DEFAULT_COLLECTION, where, detail=req.detail)


@router.get("/docsense/files")
def files():
    """Uploaded documents, newest first, for the Ask page's document picker."""
    seen: dict[str, dict] = {}
    for c in load_chunks(DEFAULT_COLLECTION):
        m = c["metadata"]
        if m.get("type") == "doc" and m.get("source"):
            seen[m["source"]] = {"file": m["source"], "name": m["source"], "doc_id": m.get("doc_id")}
    return list(reversed(seen.values()))
