"""Answer generation: retrieve -> grounded answer with citations -> follow-up suggestions."""
import re

from langchain_core.documents import Document

from .config import get_llm
from .ingest import load_chunks
from .search import _lines, hybrid_search, matches

# ---------- Prompts ----------

BASE = {
    "default": """You are Mercury, a company knowledge assistant.
Answer ONLY from the context below. If the answer isn't in the context, say
"I couldn't find that in the knowledge base." Do not make things up.
Cite sources inline as [1], [2] matching the numbered context blocks.""",
    "code": """You are Mercury GitTalk, an assistant that explains a codebase.
Answer ONLY from the code context below. Say what the code does and name the
exact file path(s). Suggest a fix or improvement only if the user asks or there
is an obvious bug. If the answer isn't in the context, say so.
Cite sources inline as [1], [2].""",
}

STYLES = {
    "short": """
How to write the answer:
- Keep it short: under 150 words.
- Start with a one or two sentence direct answer.
- Then at most 3-5 short bullet points if they add something.
- Plain, simple language. No long introductions, no repeating the question.
- No tables. No headings unless the answer has clearly separate parts.""",
    "detailed": """
How to write the answer:
- Give a thorough, well-organised explanation (roughly 300-600 words).
- Start with a 2-3 sentence overview, then use short "##" headings for each part.
- Cover EVERY important point in the context: purpose, features, how it works,
  installation/usage, examples, configuration, etc. Don't skip sections.
- Use bullet points and simple language; explain technical terms briefly.
- End with a short "In short" line summarising the main idea.""",
}

CODE_EXTRA = {
    "short": "\n- Include at most ONE short code snippet (under 10 lines), only if it helps.",
    "detailed": "\n- Include short code snippets where they help explain (under 15 lines each).",
}

# Words that mean the user wants a detailed answer.
_DETAIL_WORDS = re.compile(
    r"\b(explain|explanation|detail|detailed|in depth|describe|overview|walk ?through|"
    r"elaborate|summari[sz]e|everything|full|complete|tell me about|what is this project)\b",
    re.I,
)


def pick_detail(question: str, detail: str = "auto") -> str:
    if detail in ("short", "detailed"):
        return detail
    return "detailed" if _DETAIL_WORDS.search(question) else "short"


def build_prompt(mode: str, detail: str) -> str:
    mode = mode if mode in BASE else "default"
    prompt = BASE[mode] + STYLES[detail]
    if mode == "code":
        prompt += CODE_EXTRA[detail]
    return prompt


# ---------- File-aware retrieval ----------
# If the question names a file ("explain the README", "what does signer.py do?"),
# read that whole file in order instead of only the few chunks search picks.

MAX_PINNED_CHUNKS = {"short": 4, "detailed": 12}


# Files people name without an extension ("explain the readme").
KNOWN_FILES = {"readme", "changelog", "changes", "contributing", "license", "install", "usage"}


def _mentioned_paths(question: str, paths: set[str]) -> list[str]:
    """A file counts as 'named' only when the question clearly refers to it:
    its full name ("signer.py", "README.md"), a well-known doc ("the readme"),
    or "<name> file" ("the signer file"). Just using the word "signer" doesn't count."""
    q = question.lower()
    hits = []
    for p in paths:
        base = p.rsplit("/", 1)[-1].lower()           # "readme.md"
        stem = base.rsplit(".", 1)[0]                  # "readme"
        if (
            p.lower() in q
            or re.search(rf"(?<![\w.]){re.escape(base)}(?![\w])", q)
            or (stem in KNOWN_FILES and re.search(rf"\b{stem}\b", q))
            or re.search(rf"\b{re.escape(stem)}\s+file\b", q)
        ):
            hits.append(p)
    # Prefer code over docs when a name is ambiguous ("signer file" -> signer.py, not
    # docs/signer.rst), then top-level files (the main README over docs/sub/README.md).
    is_doc = lambda p: p.lower().endswith((".md", ".rst", ".txt"))
    return sorted(hits, key=lambda p: (is_doc(p), p.count("/"), len(p)))[:2]


def pinned_file_chunks(question: str, collection_name: str, where: dict | None, limit: int) -> list[Document]:
    chunks = [
        c for c in load_chunks(collection_name)
        if c["metadata"].get("path") and matches(c["metadata"], where)
    ]
    paths = _mentioned_paths(question, {c["metadata"]["path"] for c in chunks})
    out = []
    for p in paths:
        file_chunks = sorted(
            (c for c in chunks if c["metadata"]["path"] == p),
            key=lambda c: c["metadata"].get("chunk_index", 0),
        )
        for c in file_chunks:
            if len(out) >= limit:
                return out
            out.append(Document(page_content=c["text"], metadata=dict(c["metadata"])))
    return out

SUGGEST_PROMPT = """Given this question and answer, suggest 3 short follow-up questions the
user might ask next (under 10 words each). One per line, no numbering, no extra text.

Question: {question}
Answer: {answer}"""


def format_context(docs: list[Document]) -> str:
    blocks = []
    for i, d in enumerate(docs, 1):
        m = d.metadata
        where = m.get("source", "unknown")
        if "page" in m:
            where += f" (page {int(m['page']) + 1})"
        if m.get("path"):
            where = m["path"]
        elif m.get("title"):  # wiki pages: show the page title as well as the URL
            where = f'{m["title"]} ({m.get("source", "")})'
        blocks.append(f"[{i}] Source: {where}\n{d.page_content}")
    return "\n\n---\n\n".join(blocks)


def to_sources(docs: list[Document]) -> list[dict]:
    return [
        {
            "n": i,
            "source": d.metadata.get("source"),
            "path": d.metadata.get("path"),
            "title": d.metadata.get("title"),
            "page": d.metadata.get("page"),
            "type": d.metadata.get("type"),
            "chunk_id": d.metadata.get("chunk_id"),
            "score": d.metadata.get("rrf_score"),
            "snippet": d.page_content[:150],
        }
        for i, d in enumerate(docs, 1)
    ]


def suggest_followups(question: str, answer: str) -> list[str]:
    try:
        resp = get_llm(0.5).invoke(SUGGEST_PROMPT.format(question=question, answer=answer[:2000]))
        return _lines(resp.content)[:3]
    except Exception:
        return []


SEARCH_TOP_N = {"short": 5, "detailed": 8}


def answer_question(
    question: str,
    collection_name: str,
    where: dict | None = None,
    mode: str = "default",
    detail: str = "auto",
) -> dict:
    """detail: "short", "detailed", or "auto" (detailed when the question says
    explain / describe / overview / in detail ...)."""
    detail = pick_detail(question, detail)

    searched, queries = hybrid_search(question, collection_name, where, top_n=SEARCH_TOP_N[detail])
    pinned = pinned_file_chunks(question, collection_name, where, MAX_PINNED_CHUNKS[detail])

    # Whole named file first (in order), then other search hits, no duplicates.
    seen = {d.metadata.get("chunk_id") for d in pinned}
    docs = pinned + [d for d in searched if d.metadata.get("chunk_id") not in seen]
    if pinned:
        docs = docs[: len(pinned) + 3]  # a few extra hits for related context

    if not docs:
        return {
            "answer": "I couldn't find anything relevant in the knowledge base.",
            "sources": [],
            "suggestions": [],
            "queries": queries,
            "detail": detail,
        }

    messages = [
        ("system", build_prompt(mode, detail)),
        ("human", f"Context:\n{format_context(docs)}\n\nQuestion: {question}"),
    ]
    answer = get_llm(0.0).invoke(messages).content

    return {
        "answer": answer,
        "sources": to_sources(docs),
        "suggestions": suggest_followups(question, answer),
        "queries": queries,  # handy for the demo: shows the LLM rewrites
        "detail": detail,    # which length was used
    }


# ---------- Databloom ----------

SUMMARY_PROMPT = """Summarize the following text as clean markdown:
- a short heading
- 3-6 bullet points of the key ideas
- a "Key takeaway" line at the end
Only use information from the text.

Text:
{text}"""


def list_chunks(collection_name: str, where: dict | None = None) -> list[dict]:
    chunks = load_chunks(collection_name)
    if where:
        chunks = [c for c in chunks if matches(c["metadata"], where)]
    return [
        {"id": c["id"], "index": c["metadata"].get("chunk_index"), "preview": c["text"][:200]}
        for c in chunks
    ]


def summarize_chunk(collection_name: str, chunk_id: str) -> dict:
    chunk = next((c for c in load_chunks(collection_name) if c["id"] == chunk_id), None)
    if chunk is None:
        raise KeyError(chunk_id)
    summary = get_llm(0.2).invoke(SUMMARY_PROMPT.format(text=chunk["text"])).content
    return {"chunk_id": chunk_id, "source": chunk["metadata"].get("source"), "summary": summary}
