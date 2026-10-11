"""Sharebase: add wiki / web pages by URL and ask questions across them.

Pipeline (POST /sharebase/add):
  URL -> fetch with WebBaseLoader -> BeautifulSoup -> strip menus/ads/scripts
  -> keep the main content as markdown-ish text (headings, lists, paragraphs)
  -> remove any old version of this page -> ingest() with type=wiki
"""
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

os.environ.setdefault("USER_AGENT", "MercuryAI/0.1 (company knowledge assistant)")

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.documents import Document
from langchain_text_splitters import Language
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import ingest_department, require_type, scope_filter, visible_departments
from app.database import get_db
from app.models import User

from app.rag import answer_question, delete_where, ingest
from app.rag.config import DATA_DIR, DEFAULT_COLLECTION

router = APIRouter(prefix="/sharebase", tags=["sharebase"])

MAX_CHARS = 300_000   # a very long page is cut here
MIN_CHARS = 200       # less than this means we didn't find real content

# Parts of a page that are never the actual content.
JUNK_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "aside",
             "form", "svg", "iframe", "button", "input", "select"]
JUNK_SELECTORS = [
    ".mw-editsection", ".navbox", ".sidebar", "#toc", ".toc", ".reference",
    ".reflist", ".mw-jump-link", ".noprint", ".cookie", ".breadcrumb",
    "[role=navigation]", "[aria-hidden=true]",
]
# Where the main content usually lives, best guess first.
MAIN_SELECTORS = ["#mw-content-text", "main", "article", "[role=main]",
                  "#content", ".content", ".markdown-body", "body"]


# ---------- URL helpers ----------

def normalize_url(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise HTTPException(400, "Invalid URL. It must start with http:// or https://")
    # Drop "#section" and a trailing slash so the same page always gets the same id.
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, parts.query, ""))


def wiki_id_for(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:12]


# ---------- Fetch + clean ----------

def fetch_page(url: str):
    from langchain_community.document_loaders import WebBaseLoader

    loader = WebBaseLoader(
        url,
        raise_for_status=True,
        requests_kwargs={"timeout": 20},
    )
    try:
        return loader.scrape()  # returns a BeautifulSoup object
    except Exception as e:
        raise HTTPException(400, f"Could not fetch the page: {e}")


def html_to_text(soup) -> tuple[str, str]:
    """Return (title, clean markdown-ish text)."""
    title = (soup.title.get_text(strip=True) if soup.title else "") or "Untitled page"
    title = re.sub(r"\s+[-|–]\s+(Wikipedia|Confluence|Notion|GitHub).*$", "", title)

    for tag in soup(JUNK_TAGS):
        tag.decompose()
    for sel in JUNK_SELECTORS:
        for el in soup.select(sel):
            el.decompose()

    # First candidate that actually holds a decent amount of text.
    main = soup
    for sel in MAIN_SELECTORS:
        el = soup.select_one(sel)
        if el is not None and len(el.get_text(strip=True)) >= MIN_CHARS:
            main = el
            break

    # Mark structure so the markdown splitter can cut along sections.
    for level in range(1, 7):
        for h in main.find_all(f"h{level}"):
            h.insert_before(f"\n\n{'#' * level} ")
            h.insert_after("\n\n")
    for li in main.find_all("li"):
        li.insert_before("\n- ")
    for block in main.find_all(["p", "pre", "tr", "br", "div", "table", "blockquote", "dd"]):
        block.insert_after("\n")
    for cell in main.find_all(["td", "th"]):
        cell.insert_after(" | ")

    text = main.get_text()
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text[:MAX_CHARS]


# ---------- Registry of added pages ----------

REGISTRY = DATA_DIR / "wikis.json"
_registry_lock = threading.Lock()


def _load_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}


def _write_registry(reg: dict) -> None:
    REGISTRY.write_text(json.dumps(reg, indent=2), encoding="utf-8")


# ---------- Core function (reused by the Contribute worker) ----------

def add_page(url: str, department: str = "general", uploaded_by: str = "anonymous") -> dict:
    url = normalize_url(url)
    wiki_id = wiki_id_for(url)

    title, text = html_to_text(fetch_page(url))
    if len(text) < MIN_CHARS:
        raise HTTPException(
            422,
            "Couldn't find readable text on this page. It may need a login or "
            "JavaScript to load. Try saving it as PDF and using Docsense instead.",
        )

    # Re-adding a page replaces the old version instead of duplicating it.
    replaced = delete_where(DEFAULT_COLLECTION, "wiki_id", wiki_id)

    # Add the title as a heading only if the page doesn't already start with it.
    if not text.lstrip("# ").lower().startswith(title.lower()):
        text = f"# {title}\n\n{text}"
    doc = Document(page_content=text, metadata={"title": title})
    result = ingest(
        [doc],
        DEFAULT_COLLECTION,
        {
            "source": url,
            "type": "wiki",
            "department": department,
            "uploaded_by": uploaded_by,
            "wiki_id": wiki_id,
        },
        language=Language.MARKDOWN,  # split along headings
        path_header=True,            # every chunk starts with "# Page: <title>"
    )

    entry = {
        "wiki_id": wiki_id,
        "url": url,
        "title": title,
        "department": department,
        "uploaded_by": uploaded_by,
        "chars": len(text),
        "chunks": result["chunks"],
        "updated": replaced > 0,
        "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _registry_lock:
        reg = _load_registry()
        reg[wiki_id] = entry
        _write_registry(reg)
    return entry


# ---------- Endpoints ----------

class AddRequest(BaseModel):
    url: str
    department: str | None = None   # admins only: another department, or "all"


@router.post("/add")
def add(req: AddRequest, user: User = Depends(require_type("wiki"))):
    # plain def: fetching can be slow, so run it in a thread
    return add_page(req.url, ingest_department(user, req.department), user.email)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    url: str | None = None          # ask about one page only
    department: str | None = None
    detail: Literal["auto", "short", "detailed"] = "auto"


def _can_see_page(user: User, entry: dict) -> bool:
    depts = visible_departments(user)
    return depts is None or entry.get("department") in depts


@router.post("/ask")
def ask(req: AskRequest, user: User = Depends(require_type("wiki")), db: Session = Depends(get_db)):
    wiki_id = None
    if req.url:
        wiki_id = wiki_id_for(req.url)
        entry = _load_registry().get(wiki_id)
        if entry is None or not _can_see_page(user, entry):
            raise HTTPException(404, "This page hasn't been added yet. Call /sharebase/add first.")
    where = scope_filter(user, db, type="wiki", wiki_id=wiki_id, department=req.department)
    return answer_question(req.question, DEFAULT_COLLECTION, where, detail=req.detail)


@router.get("/pages")
def pages(user: User = Depends(require_type("wiki"))):
    visible = [p for p in _load_registry().values() if _can_see_page(user, p)]
    return sorted(visible, key=lambda p: p["added_at"], reverse=True)


@router.delete("/pages/{wiki_id}")
def delete_page(wiki_id: str, user: User = Depends(require_type("wiki"))):
    """Admins can remove any page; members only pages they added."""
    with _registry_lock:
        reg = _load_registry()
        entry = reg.get(wiki_id)
        if entry is None or not _can_see_page(user, entry):
            raise HTTPException(404, "Page not found")
        if user.role != "admin" and entry.get("uploaded_by") not in (user.email, user.name):
            raise HTTPException(403, "Only the person who added this page or an admin can remove it")
        removed = delete_where(DEFAULT_COLLECTION, "wiki_id", wiki_id)
        reg.pop(wiki_id)
        _write_registry(reg)
    return {"deleted": entry["url"], "chunks_removed": removed}
