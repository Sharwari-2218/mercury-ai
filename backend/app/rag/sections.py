"""Section-aware chunking for uploaded documents (Docsense).

Why: plain fixed-size splitting of a PDF loses the heading a passage belongs to.
In a syllabus, the chunk holding "1. Implement LAN ... 8. Configure routing" never
says "Computer Networks Lab", so neither BM25 nor the embeddings can match it to
"list the experiments for computer networks lab". Lists also get cut at page
breaks, and page footers ("Page 11 of 94") land in the middle of them.

What this does:
1. Cleans each page: drops page-number lines and running headers/footers.
2. Joins all pages into one text, so a list that crosses a page break stays whole.
3. Finds section headings and splits the text into sections.
4. Splits each section on its own and writes "Section: <heading path>" at the top
   of every chunk, so search and the LLM always know where a chunk came from.
   Each chunk keeps the page it starts on, and gets `section` metadata so a
   question that names a section can pull in the whole section (see chat.py).
"""
from __future__ import annotations

import bisect
import re
from collections import Counter

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------- Page cleaning ----------

_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:page\s*)?\d{1,4}\s*(?:(?:of|/)\s*\d{1,4})?\s*$|^\s*-\s*\d{1,4}\s*-\s*$",
    re.I,
)


def _norm_line(line: str) -> str:
    # Running headers often differ only by numbers ("Page 9", "AY 2026-27").
    return re.sub(r"\d+", "#", line.strip().lower())


def clean_pages(pages: list[str]) -> list[str]:
    """Remove page numbers and lines repeated at the top/bottom of many pages."""
    edge_counts: Counter[str] = Counter()
    for text in pages:
        lines = [l for l in text.splitlines() if l.strip()]
        edges = lines[:3] + lines[-2:]
        edge_counts.update({_norm_line(l) for l in edges})

    # A header/footer shows up at the edge of at least 30% of pages (and >= 4 pages).
    threshold = max(4, int(len(pages) * 0.3))
    running = {k for k, n in edge_counts.items() if n >= threshold} if len(pages) >= 4 else set()

    cleaned = []
    for text in pages:
        lines = text.splitlines()
        nonblank = [i for i, l in enumerate(lines) if l.strip()]
        edge_idx = set(nonblank[:3] + nonblank[-2:])
        keep = []
        for i, line in enumerate(lines):
            if _PAGE_NUMBER_RE.match(line):
                continue
            if i in edge_idx and _norm_line(line) in running:
                continue
            keep.append(line.rstrip())
        cleaned.append("\n".join(keep).strip("\n"))
    return cleaned


# ---------- Heading detection ----------
# Level 1 = a top-level unit (a course, a chapter, a policy). Level 2 = a part inside it.

_LEVEL1 = [
    re.compile(r"^\s*\[(?=[^\]]*[A-Za-z])[A-Za-z0-9][\w./-]{1,30}\]\s*:?\s*[A-Za-z].{2,120}$"),  # [2625PC31]: Computer Networks Lab
    re.compile(r"^\s*#{1,2}\s+\S.{0,150}$"),                              # # Title / ## Title (md, docx)
    re.compile(r"^\s*(?:chapter|part|annexure|appendix|schedule)\b[\s\-:]*[\dIVXLA-Z]*\b.{0,100}$", re.I),
]
_LEVEL2 = [
    re.compile(r"^\s*#{3,6}\s+\S.{0,150}$"),
    re.compile(r"^\s*(?:module|unit|section|clause)\s*[-:]?\s*[\dIVXL]+\b.{0,100}$", re.I),
    re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){1,2}\.?\s+[A-Z][^.]{2,80}$"),   # 2.1 Leave Policy
    re.compile(r"^\s*[A-Z][A-Z&/\- ]{3,60}[A-Z]\s*:?\s*$"),               # COURSE CONTENTS
]


_TOC_LINE_RE = re.compile(r"(?:\.{4,}|…{2,}|(?:\. ){4,})\s*\d+\s*$")  # "Intro ........ 12"


def heading_level(line: str) -> int:
    s = line.strip()
    if not s or len(s) > 160 or _TOC_LINE_RE.search(s):
        return 0  # table-of-contents entries are not headings
    if any(p.match(s) for p in _LEVEL1):
        return 1
    if any(p.match(s) for p in _LEVEL2):
        # ALL-CAPS lines need at least two words, so "CO1" or "NOTE" don't count.
        if s.isupper() and len(s.split()) < 2:
            return 0
        return 2
    return 0


def clean_heading(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().lstrip("#").strip()).rstrip(":")


# ---------- Splitting ----------

def _split_sections(text: str) -> list[tuple[int, str | None, str | None]]:
    """Return (start_offset, level1_title, level2_title) for each section start."""
    starts: list[tuple[int, str | None, str | None]] = [(0, None, None)]
    h1 = h2 = None
    pos = 0
    for line in text.splitlines(keepends=True):
        level = heading_level(line)
        if level == 1:
            h1, h2 = clean_heading(line), None
            starts.append((pos, h1, h2))
        elif level == 2:
            h2 = clean_heading(line)
            starts.append((pos, h1, h2))
        pos += len(line)
    return starts


def section_documents(
    docs: list[Document],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """Turn loader output (one Document per page, or one per file) into
    section-labelled chunks."""
    if not docs:
        return []
    base_meta = {k: v for k, v in docs[0].metadata.items() if k != "page"}
    pages = clean_pages([d.page_content for d in docs])

    # Join pages, remembering where each page starts so chunks keep page numbers.
    page_starts, page_nums, parts, pos = [], [], [], 0
    for d, text in zip(docs, pages):
        if not text.strip():
            continue
        page_starts.append(pos)
        page_nums.append(d.metadata.get("page"))
        parts.append(text)
        pos += len(text) + 1
    full = "\n".join(parts)

    def page_at(offset: int):
        if not page_starts:
            return None
        return page_nums[max(0, bisect.bisect_right(page_starts, offset) - 1)]

    starts = _split_sections(full)
    chunks: list[Document] = []
    for i, (start, h1, h2) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(full)
        body = full[start:end]
        if not body.strip():
            continue
        title = " > ".join(t for t in (h1, h2) if t)
        header = f"Section: {title}\n" if title else ""
        # Leave room for the header so chunks stay near chunk_size.
        size = max(200, chunk_size - len(header))
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=size, chunk_overlap=min(chunk_overlap, size // 4), add_start_index=True
        )
        for piece in splitter.split_documents([Document(page_content=body)]):
            meta = dict(base_meta)
            page = page_at(start + piece.metadata.get("start_index", 0))
            if page is not None:
                meta["page"] = page
            if h1:
                meta["section"] = h1
            if h2:
                meta["subsection"] = h2
            chunks.append(Document(page_content=header + piece.page_content, metadata=meta))
    return chunks


# ---------- Matching a question to a section ----------

_PAREN_RE = re.compile(r"\(([^)]{2,15})\)")
_CODE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*:?\s*")


def section_names(title: str) -> tuple[str, list[str]]:
    """'[2625PC31]: Computer Networks Lab (CNL)' -> ('computer networks lab', ['CNL', '2625PC31'])."""
    aliases = []
    m = _CODE_RE.match(title)
    if m:
        aliases.append(m.group(1))
        title = title[m.end():]
    aliases += [a.strip() for a in _PAREN_RE.findall(title) if " " not in a.strip()]
    core = _PAREN_RE.sub(" ", title)
    core = re.sub(r"[^\w&+ ]+", " ", core).lower()
    core = re.sub(r"\s+", " ", core).strip()
    return core, aliases


def sections_named_in(question: str, titles: set[str], max_hits: int = 2) -> list[str]:
    """Sections the question clearly names: the full name ("computer networks lab"),
    its code ("2625PC31") or its abbreviation ("CNL"). When one name is part of
    another ("computer networks" vs "computer networks lab"), the longer one wins."""
    q_norm = " " + re.sub(r"\s+", " ", re.sub(r"[^\w&+ ]+", " ", question.lower())) + " "
    hits: dict[str, str] = {}
    for t in titles:
        core, aliases = section_names(t)
        named = len(core.split()) >= 2 and f" {core} " in q_norm
        for a in aliases:
            # Short abbreviations ("ML", "CN") must be written in capitals.
            flags = re.I if len(a) >= 4 else 0
            if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", question, flags):
                named = True
        if named:
            hits[t] = core
    # "ML lab" names "Machine Learning (ML)" by its abbreviation, but if there is a
    # "Machine Learning Lab" section and the question has "lab", that is the one meant.
    q_words = set(q_norm.split())
    all_cores = {t: section_names(t)[0] for t in titles}
    for t, core in list(hits.items()):
        for other, other_core in all_cores.items():
            extra = other_core[len(core):].split() if other_core.startswith(core + " ") else []
            if extra and set(extra) <= q_words:
                hits.pop(t, None)
                hits[other] = other_core
    # Drop a hit whose name is inside a longer hit's name.
    out = [
        t for t, core in hits.items()
        if not any(core != other and f" {core} " in f" {other} " for other in hits.values())
    ]
    return sorted(out, key=lambda t: -len(hits[t]))[:max_hits]
