"""Shared settings and lazily-created clients (embeddings, vector store, LLM)."""
import os
import re
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
CHROMA_DIR = DATA_DIR / "chroma_db"
CHUNKS_DIR = DATA_DIR / "chunks"   # raw chunk JSON for BM25
UPLOAD_DIR = DATA_DIR / "uploads"
for _d in (CHROMA_DIR, CHUNKS_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Docs and wikis share one collection (separated by the `type` metadata);
# each GitHub repo gets its own collection, e.g. repo_flask.
DEFAULT_COLLECTION = "mercury"


def safe_collection_name(name: str) -> str:
    """Chroma names: 3-63 chars, alphanumerics plus _ - and ., alnum at both ends."""
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("_.-")
    name = name[:63] or "default"
    return name if len(name) >= 3 else f"{name}___"[:3]


@lru_cache
def get_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=None)
def get_vectorstore(collection_name: str):
    from langchain_chroma import Chroma

    return Chroma(
        collection_name=safe_collection_name(collection_name),
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


@lru_cache(maxsize=None)
def get_llm(temperature: float = 0.0):
    from langchain_groq import ChatGroq

    # max_retries handles free-tier 429s with backoff.
    return ChatGroq(model=LLM_MODEL, temperature=temperature, max_retries=4)
