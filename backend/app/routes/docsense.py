"""Docsense (upload + ask one document) and Databloom (chunk summaries)."""
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.rag import answer_question, ingest_file, list_chunks, summarize_chunk
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
    doc_id: str | None = None      # restrict to one document
    department: str | None = None
    detail: Literal["auto", "short", "detailed"] = "auto"


@router.post("/docsense/ask")
def ask(req: AskRequest):
    where = {"type": "doc"}
    if req.doc_id:
        where["doc_id"] = req.doc_id
    if req.department:
        where["department"] = req.department
    return answer_question(req.question, DEFAULT_COLLECTION, where, detail=req.detail)


# ---------- Databloom ----------

@router.get("/databloom/{doc_id}/chunks", tags=["databloom"])
def chunks(doc_id: str):
    return list_chunks(DEFAULT_COLLECTION, {"doc_id": doc_id})


class SummarizeRequest(BaseModel):
    chunk_id: str
    collection: str = DEFAULT_COLLECTION


@router.post("/databloom", tags=["databloom"])
def databloom(req: SummarizeRequest):
    try:
        return summarize_chunk(req.collection, req.chunk_id)
    except KeyError:
        raise HTTPException(404, "Chunk not found")
