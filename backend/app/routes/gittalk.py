"""GitTalk: index a GitHub repo and ask questions about its code.

Pipeline (POST /gittalk/index):
  URL -> parse owner/repo -> shallow clone to temp folder -> walk + filter files
  -> one Document per file (path + language) -> group by language
  -> ingest() per group into collection repo_<owner>_<repo> -> delete temp folder
"""
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.documents import Document
from langchain_text_splitters import Language
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import ingest_department, require_type, scope_filter, visible_departments
from app.database import get_db
from app.models import User

from app.rag import answer_question, collection_exists, ingest, reset_collection
from app.rag.config import DATA_DIR, safe_collection_name

router = APIRouter(prefix="/gittalk", tags=["gittalk"])

# ---------- What to keep / skip ----------

# extension -> (language name for metadata, LangChain splitter language or None)
EXTENSIONS: dict[str, tuple[str, Language | None]] = {
    ".py": ("python", Language.PYTHON),
    ".js": ("javascript", Language.JS),
    ".jsx": ("javascript", Language.JS),
    ".mjs": ("javascript", Language.JS),
    ".ts": ("typescript", Language.TS),
    ".tsx": ("typescript", Language.TS),
    ".java": ("java", Language.JAVA),
    ".kt": ("kotlin", Language.KOTLIN),
    ".go": ("go", Language.GO),
    ".rb": ("ruby", Language.RUBY),
    ".php": ("php", Language.PHP),
    ".c": ("c", Language.C),
    ".h": ("c", Language.C),
    ".cpp": ("cpp", Language.CPP),
    ".hpp": ("cpp", Language.CPP),
    ".cs": ("csharp", Language.CSHARP),
    ".rs": ("rust", Language.RUST),
    ".swift": ("swift", Language.SWIFT),
    ".scala": ("scala", Language.SCALA),
    ".md": ("markdown", Language.MARKDOWN),
    ".rst": ("rst", Language.RST),
    ".html": ("html", Language.HTML),
    ".txt": ("text", None),
    ".json": ("json", None),
    ".yml": ("yaml", None),
    ".yaml": ("yaml", None),
    ".toml": ("toml", None),
    ".cfg": ("config", None),
    ".sql": ("sql", None),
    ".sh": ("shell", None),
}
SPECIAL_FILES = {"Dockerfile": "docker", "Makefile": "make"}  # files with no extension

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build",
    "target", ".next", ".nuxt", "out", "coverage", ".idea", ".vscode", ".tox",
    ".mypy_cache", ".pytest_cache", "vendor", "site-packages",
}
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "composer.lock", "Cargo.lock", "go.sum",
}
MAX_FILE_BYTES = 200_000   # bigger files are usually generated data
MAX_FILES = 1500           # safety cap so a huge repo can't run for hours

# ---------- URL parsing ----------

_GITHUB_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/.*)?$"
)


def parse_github_url(url: str) -> tuple[str, str]:
    """'https://github.com/pallets/flask/tree/main' -> ('pallets', 'flask')."""
    m = _GITHUB_RE.match(url.strip())
    if not m:
        raise HTTPException(400, "Invalid GitHub URL. Expected https://github.com/<owner>/<repo>")
    return m.group(1), m.group(2)


def repo_collection(owner: str, repo: str) -> str:
    return safe_collection_name(f"repo_{owner}_{repo}".lower())


# ---------- Clone + cleanup ----------

def _force_remove(func, path, _exc):
    """Windows marks files in .git read-only; clear the flag and retry the delete."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_dir(path: str) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_remove)
    else:
        shutil.rmtree(path, onerror=_force_remove)


def clone_repo(owner: str, repo: str, dest: str) -> None:
    try:
        from git import GitCommandError, Repo  # import here: fails if Git isn't installed
    except ImportError:
        raise HTTPException(500, "Git is not installed on the server. Install Git and restart.")
    try:
        Repo.clone_from(
            f"https://github.com/{owner}/{repo}.git",
            dest,
            depth=1,
            # Never ask for a password: private/missing repos fail fast instead of
            # hanging (or opening a Windows login pop-up).
            env={"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
        )
    except GitCommandError:
        raise HTTPException(
            400, f"Could not clone {owner}/{repo}. Check that it exists and is public."
        )


# ---------- Walk + filter ----------

def _is_binary(raw: bytes) -> bool:
    return b"\x00" in raw[:1024]


def collect_files(root: str) -> tuple[list[tuple[Document, Language | None]], int]:
    """Return ([(Document, splitter_language), ...], skipped_count)."""
    out, skipped = [], 0
    root_path = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # Editing dirnames in place stops os.walk from going into skipped folders.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            full = Path(dirpath) / name
            ext = full.suffix.lower()
            if name in SKIP_FILES or name.endswith((".min.js", ".min.css", ".map")):
                skipped += 1
                continue
            if ext in EXTENSIONS:
                lang_name, splitter = EXTENSIONS[ext]
            elif name in SPECIAL_FILES:
                lang_name, splitter = SPECIAL_FILES[name], None
            else:
                skipped += 1
                continue
            try:
                if full.stat().st_size > MAX_FILE_BYTES:
                    skipped += 1
                    continue
                raw = full.read_bytes()
            except OSError:
                skipped += 1
                continue
            if _is_binary(raw):
                skipped += 1
                continue
            text = raw.decode("utf-8", errors="ignore")
            if not text.strip():
                continue
            rel = full.relative_to(root_path).as_posix()  # forward slashes on Windows too
            out.append(
                (Document(page_content=text, metadata={"path": rel, "language": lang_name}), splitter)
            )
            if len(out) >= MAX_FILES:
                return out, skipped
    return out, skipped


# ---------- Registry of indexed repos (for GET /gittalk/repos) ----------

REGISTRY = DATA_DIR / "repos.json"
_registry_lock = threading.Lock()


def _load_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}


def _save_registry_entry(collection: str, entry: dict) -> None:
    with _registry_lock:
        reg = _load_registry()
        reg[collection] = entry
        REGISTRY.write_text(json.dumps(reg, indent=2), encoding="utf-8")


# ---------- Core indexing function (reused by the Contribute worker on Day 2) ----------

def index_repo(url: str, department: str = "engineering", uploaded_by: str = "anonymous") -> dict:
    owner, repo = parse_github_url(url)
    collection = repo_collection(owner, repo)
    tmp = tempfile.mkdtemp(prefix="gittalk_")
    try:
        clone_repo(owner, repo, tmp)
        files, skipped = collect_files(tmp)
        if not files:
            raise HTTPException(422, "No supported code or docs files found in this repo.")

        # Re-indexing starts fresh, so results never show duplicates or stale code.
        reset_collection(collection)

        groups: dict[Language | None, list[Document]] = defaultdict(list)
        for doc, splitter in files:
            groups[splitter].append(doc)

        base_meta = {
            "source": f"https://github.com/{owner}/{repo}",
            "type": "code",
            "repo": f"{owner}/{repo}",
            "department": department,
            "uploaded_by": uploaded_by,
        }
        total_chunks = 0
        for splitter, docs in groups.items():
            result = ingest(docs, collection, base_meta, language=splitter, path_header=True)
            total_chunks += result["chunks"]

        languages = sorted({d.metadata["language"] for d, _ in files})
        summary = {
            "repo": f"{owner}/{repo}",
            "url": f"https://github.com/{owner}/{repo}",
            "collection": collection,
            "department": department,
            "uploaded_by": uploaded_by,
            "files_indexed": len(files),
            "files_skipped": skipped,
            "chunks": total_chunks,
            "languages": languages,
            "truncated": len(files) >= MAX_FILES,
            "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _save_registry_entry(collection, summary)
        return summary
    finally:
        remove_dir(tmp)  # always clean up, even if something failed


# ---------- Endpoints ----------

class IndexRequest(BaseModel):
    repo_url: str
    department: str | None = None   # admins only: another department, or "all"


@router.post("/index")
def index(req: IndexRequest, user: User = Depends(require_type("code"))):
    # plain def: runs in a thread so slow clones don't freeze the API
    return index_repo(req.repo_url, ingest_department(user, req.department), user.email)


class AskRequest(BaseModel):
    repo_url: str
    question: str = Field(min_length=1, max_length=2000)
    detail: Literal["auto", "short", "detailed"] = "auto"


@router.post("/ask")
def ask(req: AskRequest, user: User = Depends(require_type("code")), db: Session = Depends(get_db)):
    owner, repo = parse_github_url(req.repo_url)
    collection = repo_collection(owner, repo)
    entry = _load_registry().get(collection)
    if not collection_exists(collection) or not _can_see_repo(user, entry):
        # Same message whether it's missing or not yours, so repos can't be probed.
        raise HTTPException(404, f"{owner}/{repo} hasn't been indexed yet. Call /gittalk/index first.")
    where = scope_filter(user, db, type="code")
    return answer_question(req.question, collection, where=where, mode="code", detail=req.detail)


def _can_see_repo(user: User, entry: dict | None) -> bool:
    depts = visible_departments(user)
    if depts is None:  # admin
        return True
    # Repos indexed before access control have no registry department; let the
    # chunk-level filter in /ask decide for those.
    return entry is None or entry.get("department") in depts


@router.get("/repos")
def repos(user: User = Depends(require_type("code"))):
    visible = [r for r in _load_registry().values() if _can_see_repo(user, r)]
    return sorted(visible, key=lambda r: r["indexed_at"], reverse=True)
