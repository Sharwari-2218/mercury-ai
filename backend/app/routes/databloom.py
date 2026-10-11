"""Databloom: list a document's chunks and summarize any one of them as markdown.

Reads from the same place every other feature writes to: the shared chunk store
(app.rag.ingest.load_chunks) for DEFAULT_COLLECTION in app.rag.config.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import can_see_chunk, require_type
from app.database import get_db
from app.models import User
from app.rag.config import DEFAULT_COLLECTION, get_llm
from app.rag.ingest import load_chunks

router = APIRouter(prefix="/databloom", tags=["databloom"])

PROMPT = """You summarize document excerpts for busy readers.
Use ONLY the text provided. Do not add outside facts.

Source file: {source}

Excerpt:
\"\"\"
{text}
\"\"\"

Write a markdown summary with:
## a short heading naming the topic
- 3 to 6 bullet points covering the main ideas
**Key point:** one sentence with the single most important takeaway.
If the excerpt is too short or meaningless to summarize, say so in one line."""

# So re-clicking "Summarize" doesn't burn API quota. Resets when the server restarts.
_summary_cache: dict[str, str] = {}


def _visible_doc_chunks(user: User, db: Session) -> list[dict]:
    """Document chunks (not wikis) this user is allowed to see."""
    return [
        c for c in load_chunks(DEFAULT_COLLECTION)
        if c["metadata"].get("type") == "doc" and can_see_chunk(user, c["metadata"], db)
    ]


@router.get("/files")
def list_files(user: User = Depends(require_type("doc")), db: Session = Depends(get_db)):
    """File names for the picker."""
    sources = {c["metadata"].get("source") for c in _visible_doc_chunks(user, db)}
    return {"files": sorted(s for s in sources if s)}


@router.get("/chunks")
def list_chunks(source: str, user: User = Depends(require_type("doc")), db: Session = Depends(get_db)):
    """All chunks of one file, in document order, with a short preview."""
    chunks = [c for c in _visible_doc_chunks(user, db) if c["metadata"].get("source") == source]
    if not chunks:
        raise HTTPException(404, f"No chunks found for '{source}'")

    out = [
        {
            "chunk_id": c["id"],
            "index": c["metadata"].get("chunk_index", i),
            "preview": c["text"][:200],
            "length": len(c["text"]),
            "summarized": c["id"] in _summary_cache,
        }
        for i, c in enumerate(chunks)
    ]
    out.sort(key=lambda c: c["index"])
    return {"source": source, "count": len(out), "chunks": out}


class SummarizeRequest(BaseModel):
    source: str
    chunk_id: str


@router.post("")
def summarize_chunk(req: SummarizeRequest, user: User = Depends(require_type("doc")),
                    db: Session = Depends(get_db)):
    """Fetch one chunk by ID and return a markdown summary of it."""
    chunk = next((c for c in load_chunks(DEFAULT_COLLECTION) if c["id"] == req.chunk_id), None)

    # Permission check comes BEFORE the cache, so a cached summary can't leak to the wrong person.
    # 404 rather than 403, so users can't tell that a chunk they can't see exists.
    if chunk is None or chunk["metadata"].get("type") != "doc" or not can_see_chunk(user, chunk["metadata"], db):
        raise HTTPException(404, "Chunk not found")
    if chunk["metadata"].get("source") != req.source:
        raise HTTPException(400, "Chunk does not belong to this file")

    if req.chunk_id in _summary_cache:
        return {"chunk_id": req.chunk_id, "summary": _summary_cache[req.chunk_id], "cached": True}

    try:
        # get_llm() already retries free-tier rate limits with backoff.
        summary = get_llm(0.2).invoke(PROMPT.format(source=req.source, text=chunk["text"])).content
    except Exception as e:
        raise HTTPException(502, f"LLM call failed: {e}")

    _summary_cache[req.chunk_id] = summary
    return {"chunk_id": req.chunk_id, "summary": summary, "cached": False}
