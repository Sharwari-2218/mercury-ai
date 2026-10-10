"""Databloom: per-chunk markdown summaries.

Reads the same Chroma store and collection that Docsense and Contribute ingest
into (rag/config.py), so every uploaded document shows up here.
"""
import time

from fastapi import APIRouter, HTTPException
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.rag.config import DEFAULT_COLLECTION, get_llm, get_vectorstore

router = APIRouter(prefix="/databloom", tags=["databloom"])


def get_store(collection: str):
    return get_vectorstore(collection)


PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You summarize document excerpts for busy readers. "
     "Use ONLY the text provided. Do not add outside facts."),
    ("human",
     "Source file: {source}\n\n"
     "Excerpt:\n\"\"\"\n{text}\n\"\"\"\n\n"
     "Write a markdown summary with:\n"
     "## a short heading naming the topic\n"
     "- 3 to 6 bullet points covering the main ideas\n"
     "**Key point:** one sentence with the single most important takeaway.\n"
     "If the excerpt is too short or meaningless to summarize, say so in one line."),
])

# Simple in-memory cache so re-clicking "Summarize" doesn't burn API quota.
_summary_cache: dict[str, str] = {}


def call_llm_with_retry(messages, retries: int = 3) -> str:
    """Free-tier APIs rate-limit; back off and retry instead of failing."""
    for attempt in range(retries):
        try:
            return get_llm(0.2).invoke(messages).content
        except Exception as e:  # groq raises RateLimitError, among others
            if attempt == retries - 1:
                raise HTTPException(502, f"LLM call failed: {e}")
            time.sleep(2 ** attempt)


# ---------- endpoints ----------

@router.get("/files")
def list_files(collection: str = DEFAULT_COLLECTION):
    """Distinct uploaded documents in a collection, for the file picker (wikis excluded)."""
    data = get_store(collection).get(where={"type": "doc"}, include=["metadatas"])
    sources = sorted({m.get("source") for m in data["metadatas"] if m and m.get("source")})
    return {"files": sources}


@router.get("/chunks")
def list_chunks(source: str, collection: str = DEFAULT_COLLECTION):
    """All chunks of one file, in document order, with a short preview."""
    data = get_store(collection).get(
        where={"source": source},
        include=["documents", "metadatas"],
    )
    if not data["ids"]:
        raise HTTPException(404, f"No chunks found for '{source}'")

    chunks = [
        {
            "chunk_id": cid,
            "index": (meta or {}).get("chunk_index", i),
            "preview": text[:200],
            "length": len(text),
            "summarized": cid in _summary_cache,
        }
        for i, (cid, text, meta) in enumerate(
            zip(data["ids"], data["documents"], data["metadatas"])
        )
    ]
    chunks.sort(key=lambda c: c["index"])
    return {"source": source, "count": len(chunks), "chunks": chunks}


class SummarizeRequest(BaseModel):
    source: str
    chunk_id: str
    collection: str = DEFAULT_COLLECTION


@router.post("")
def summarize_chunk(req: SummarizeRequest):
    """Fetch one chunk by ID and return a markdown summary of it."""
    if req.chunk_id in _summary_cache:
        return {"chunk_id": req.chunk_id, "summary": _summary_cache[req.chunk_id], "cached": True}

    data = get_store(req.collection).get(ids=[req.chunk_id], include=["documents", "metadatas"])
    if not data["ids"]:
        raise HTTPException(404, "Chunk not found")

    meta = data["metadatas"][0] or {}
    if meta.get("source") != req.source:
        raise HTTPException(400, "Chunk does not belong to this file")

    text = data["documents"][0]
    messages = PROMPT.format_messages(source=req.source, text=text)
    summary = call_llm_with_retry(messages)

    _summary_cache[req.chunk_id] = summary
    return {"chunk_id": req.chunk_id, "summary": summary, "cached": False}
