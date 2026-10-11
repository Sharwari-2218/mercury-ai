"""3-layer search: BM25 keyword + Chroma vector, fused with RRF, driven by LLM query rewrites."""
import re
from pathlib import Path

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from .config import get_llm, get_vectorstore
from .ingest import chunk_file, load_chunks

TOP_K = 10      # per layer, per query
FINAL_K = 5     # after fusion


# ---------- Layer 1: keyword (BM25) ----------

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    # Splits snake_case and camelCase too, so code identifiers match natural queries.
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [t.lower() for t in _TOKEN_RE.findall(text.replace("_", " "))]


_bm25_cache: dict[str, tuple[tuple, BM25Okapi, list[dict]]] = {}


def _get_bm25(collection_name: str):
    """Build the index once and rebuild only when the chunk file changes."""
    f: Path = chunk_file(collection_name)
    if not f.exists():
        return None, []
    st = f.stat()
    mtime = (st.st_mtime_ns, st.st_size)  # size too, so a quick reset+reindex is caught
    cached = _bm25_cache.get(collection_name)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    chunks = load_chunks(collection_name)
    if not chunks:
        return None, []
    index = BM25Okapi([tokenize(c["text"]) for c in chunks])
    _bm25_cache[collection_name] = (mtime, index, chunks)
    return index, chunks


def matches(meta: dict, where: dict | None) -> bool:
    """Simple filter used everywhere: {"key": value} must be equal, and
    {"key": [a, b]} means the value must be one of the list (access control)."""
    if not where:
        return True
    for k, v in where.items():
        got = meta.get(k)
        if isinstance(v, (list, tuple, set)):
            if got not in v:
                return False
        elif got != v:
            return False
    return True


_matches = matches  # old name


def keyword_search(query: str, collection_name: str, where: dict | None = None, k: int = TOP_K) -> list[Document]:
    index, chunks = _get_bm25(collection_name)
    if index is None:
        return []
    q_tokens = tokenize(query)
    q_set = set(q_tokens)
    scores = index.get_scores(q_tokens)
    ranked = sorted(range(len(chunks)), key=lambda i: -scores[i])
    out = []
    for i in ranked:
        # Check term overlap rather than score > 0: on small corpora BM25's IDF
        # goes to ~0 or negative for terms found in most chunks.
        if q_set.isdisjoint(index.doc_freqs[i]):
            continue
        if _matches(chunks[i]["metadata"], where):
            out.append(Document(page_content=chunks[i]["text"], metadata=chunks[i]["metadata"]))
            if len(out) == k:
                break
    return out


# ---------- Layer 2: vector (Chroma) ----------

def to_chroma_filter(where: dict | None):
    """Turn the simple filter into Chroma's syntax: lists become $in, and
    several keys need an explicit $and."""
    if not where:
        return None
    parts = [
        {k: {"$in": list(v)}} if isinstance(v, (list, tuple, set)) else {k: v}
        for k, v in where.items()
    ]
    return parts[0] if len(parts) == 1 else {"$and": parts}


_chroma_filter = to_chroma_filter  # old name


def vector_search(query: str, collection_name: str, where: dict | None = None, k: int = TOP_K) -> list[Document]:
    vs = get_vectorstore(collection_name)
    try:
        return vs.similarity_search(query, k=k, filter=_chroma_filter(where))
    except Exception:
        return []  # empty / missing collection


# ---------- Fusion: Reciprocal Rank Fusion ----------

def rrf(result_lists: list[list[Document]], k: int = 60, top_n: int = FINAL_K) -> list[Document]:
    """score(d) = sum over lists of 1 / (k + rank). Rank-based, so BM25 and cosine
    scores never need to be normalised against each other."""
    scores: dict[str, tuple[float, Document]] = {}
    for results in result_lists:
        for rank, doc in enumerate(results):
            key = doc.metadata.get("chunk_id") or doc.page_content
            prev = scores.get(key, (0.0, doc))[0]
            scores[key] = (prev + 1 / (k + rank + 1), doc)
    fused = sorted(scores.values(), key=lambda x: -x[0])[:top_n]
    for score, doc in fused:
        doc.metadata["rrf_score"] = round(score, 5)
    return [d for _, d in fused]


# ---------- Layer 3: LLM query rewriting ----------

REWRITE_PROMPT = """Rewrite the search query below into {n} alternative phrasings that could match
relevant passages in a company knowledge base. Use synonyms, expand acronyms, and vary the
wording. Return one phrasing per line, no numbering, no extra text.

Query: {query}"""


def _lines(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"')
        if line:
            out.append(line)
    return out


def rewrite_query(query: str, n: int = 3) -> list[str]:
    try:
        resp = get_llm(0.3).invoke(REWRITE_PROMPT.format(n=n, query=query))
        alts = _lines(resp.content)[:n]
    except Exception:
        alts = []  # rate limit etc. -> fall back to the original query only
    seen, queries = set(), []
    for q in [query, *alts]:
        if q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    return queries


def hybrid_search(
    query: str,
    collection_name: str,
    where: dict | None = None,
    use_rewrites: bool = True,
    top_n: int = FINAL_K,
) -> tuple[list[Document], list[str]]:
    """Run BM25 + vector for the original query and each rewrite, then fuse everything."""
    queries = rewrite_query(query) if use_rewrites else [query]
    lists: list[list[Document]] = []
    for q in queries:
        lists.append(keyword_search(q, collection_name, where))
        lists.append(vector_search(q, collection_name, where))
    return rrf(lists, top_n=top_n), queries
