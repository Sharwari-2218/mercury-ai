"""Ingestion pipeline: load -> split -> embed into Chroma + save raw chunks for BM25."""
import json
import threading
import uuid
from pathlib import Path
from typing import Iterable

from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from .config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKS_DIR,
    get_vectorstore,
    safe_collection_name,
)

_chunk_file_lock = threading.Lock()

REQUIRED_META = ("source", "type", "department", "uploaded_by")


# ---------- Loaders ----------

def load_file(path: str | Path) -> list[Document]:
    """Load PDF / DOCX / TXT / MD into LangChain Documents (one per page or file)."""
    path = Path(path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        from langchain_community.document_loaders import PyPDFLoader

        docs = PyPDFLoader(str(path)).load()  # one Document per page, has `page` meta
    elif ext == ".docx":
        import docx  # python-docx

        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        # Tables often hold the important stuff in company docs.
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        docs = [Document(page_content="\n".join(parts))]
    elif ext in (".txt", ".md"):
        docs = [Document(page_content=path.read_text(encoding="utf-8", errors="ignore"))]
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return [d for d in docs if d.page_content.strip()]


# ---------- Splitting ----------

def split_documents(docs: list[Document], language: Language | None = None) -> list[Document]:
    if language is not None:  # GitTalk: split along function/class boundaries
        splitter = RecursiveCharacterTextSplitter.from_language(
            language, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
    return splitter.split_documents(docs)


# ---------- Raw chunk store (for BM25 + Databloom) ----------

def chunk_file(collection_name: str) -> Path:
    return CHUNKS_DIR / f"{safe_collection_name(collection_name)}.json"


def load_chunks(collection_name: str) -> list[dict]:
    f = chunk_file(collection_name)
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8"))


def _append_chunks(collection_name: str, records: list[dict]) -> None:
    with _chunk_file_lock:
        existing = load_chunks(collection_name)
        existing.extend(records)
        tmp = chunk_file(collection_name).with_suffix(".tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
        tmp.replace(chunk_file(collection_name))  # atomic swap


# ---------- Main entry point ----------

def reset_collection(collection_name: str) -> None:
    """Wipe a collection from both stores (used before re-indexing a repo)."""
    get_vectorstore(collection_name).reset_collection()  # delete + recreate empty
    with _chunk_file_lock:
        chunk_file(collection_name).unlink(missing_ok=True)


def delete_where(collection_name: str, key: str, value) -> int:
    """Remove every chunk whose metadata[key] == value from both stores.
    Used when a wiki page is re-added, so old versions don't linger."""
    with _chunk_file_lock:
        chunks = load_chunks(collection_name)
        keep = [c for c in chunks if c["metadata"].get(key) != value]
        removed = len(chunks) - len(keep)
        if removed:
            get_vectorstore(collection_name)._collection.delete(where={key: value})
            tmp = chunk_file(collection_name).with_suffix(".tmp")
            tmp.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
            tmp.replace(chunk_file(collection_name))
    return removed


def collection_exists(collection_name: str) -> bool:
    return chunk_file(collection_name).exists()


def ingest(
    docs: Iterable[Document],
    collection_name: str,
    metadata: dict,
    language: Language | None = None,
    path_header: bool = False,
) -> dict:
    """Split, tag, embed and store documents.

    metadata must include: source, type (doc|code|wiki), department, uploaded_by.
    Extra keys (e.g. doc_id, repo) are kept too. Per-document metadata from the
    loader (page numbers, file paths) is preserved and merged underneath.

    path_header=True (GitTalk) writes "# File: <path>" at the top of EVERY chunk,
    so both BM25 and the embeddings know which file a chunk came from.
    """
    missing = [k for k in REQUIRED_META if k not in metadata]
    if missing:
        raise ValueError(f"metadata missing keys: {missing}")

    docs = list(docs)
    chunks = split_documents(docs, language)
    if not chunks:
        return {"collection": collection_name, "chunks": 0}

    if path_header:
        for c in chunks:
            if c.metadata.get("path"):
                c.page_content = f"# File: {c.metadata['path']}\n{c.page_content}"
            elif c.metadata.get("title"):
                c.page_content = f"# Page: {c.metadata['title']}\n{c.page_content}"

    records, ids = [], []
    for i, c in enumerate(chunks):
        chunk_id = uuid.uuid4().hex
        # Chroma only accepts str/int/float/bool metadata values.
        meta = {
            k: v
            for k, v in {**c.metadata, **metadata}.items()
            if isinstance(v, (str, int, float, bool))
        }
        meta["chunk_id"] = chunk_id
        meta["chunk_index"] = i
        c.metadata = meta
        ids.append(chunk_id)
        records.append({"id": chunk_id, "text": c.page_content, "metadata": meta})

    vs = get_vectorstore(collection_name)
    # Batch so big repos don't hit Chroma's max batch size.
    for start in range(0, len(chunks), 500):
        vs.add_documents(chunks[start : start + 500], ids=ids[start : start + 500])

    _append_chunks(collection_name, records)
    return {"collection": collection_name, "chunks": len(chunks)}


def ingest_file(path: str | Path, collection_name: str, metadata: dict) -> dict:
    """Convenience wrapper used by Docsense and the Contribute worker."""
    return ingest(load_file(path), collection_name, metadata)
