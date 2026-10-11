import os
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from rq import Queue

from app.database import SessionLocal
from app.auth import allowed_types, get_current_user
from app.models import Job
from app.rag.config import UPLOAD_DIR as _DEFAULT_UPLOAD_DIR

router = APIRouter(prefix="/contribute", tags=["contribute"])

# Folder where uploaded files are saved before the worker processes them.
# Absolute (backend/data/uploads) so the API and the worker agree on it
# no matter which folder each one was started from.
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(_DEFAULT_UPLOAD_DIR))
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# Redis connection + queue (the worker must listen to the same queue name: "ingest")
redis_conn = Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
)
queue = Queue("ingest", connection=redis_conn)


def _user_field(user, field: str, default: str = "") -> str:
    """Works whether get_current_user returns a dict or a SQLAlchemy object."""
    if isinstance(user, dict):
        return user.get(field) or default
    return getattr(user, field, None) or default


def _safe_filename(name: str) -> str:
    """Remove characters that could break file paths."""
    name = os.path.basename(name)
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _job_to_dict(job: Job) -> dict:
    return {
        "job_id": job.id,
        "type": job.type,
        "source": job.source,
        "status": job.status,
        "chunks_added": job.chunks_added,
        "error": job.error,
        "uploaded_by": job.uploaded_by,
        "department": job.department,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.post("")
async def contribute(
    type: str = Form(...),                       # "file" | "repo" | "wiki"
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    current_user=Depends(get_current_user),
):
    # Who is uploading comes from the login, not from the form
    uploaded_by = _user_field(current_user, "email", "unknown")
    department = _user_field(current_user, "department", "general")

    # Each kind of upload needs the matching permission (same rule as the feature itself)
    needed = {"file": "doc", "repo": "code", "wiki": "wiki"}.get(type)
    if needed:
        db = SessionLocal()
        try:
            permitted = allowed_types(current_user, db)
        finally:
            db.close()
        if needed not in permitted:
            raise HTTPException(403, f"Your department can't add '{needed}' content")

    job_id = str(uuid.uuid4())

    # ---------- Validate input ----------
    if type == "file":
        if file is None or not file.filename:
            raise HTTPException(400, "Please choose a file.")

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type {ext}. Allowed: PDF, DOCX, TXT, MD.")

        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(400, "The file is empty.")
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(400, "File is too large (max 20 MB).")

        # Save to disk so the worker can read it (files can't go through Redis)
        path = os.path.join(UPLOAD_DIR, f"{job_id}_{_safe_filename(file.filename)}")
        with open(path, "wb") as f:
            f.write(contents)
        source = path

    elif type == "repo":
        if not url or not url.strip():
            raise HTTPException(400, "Please enter a GitHub URL.")
        url = url.strip()
        if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?(\.git)?$", url):
            raise HTTPException(400, "Enter a valid GitHub repo URL, e.g. https://github.com/user/repo")
        source = url

    elif type == "wiki":
        if not url or not url.strip():
            raise HTTPException(400, "Please enter a wiki URL.")
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400, "URL must start with http:// or https://")
        source = url

    else:
        raise HTTPException(400, "type must be 'file', 'repo' or 'wiki'.")

    # ---------- Save the job in SQLite ----------
    db = SessionLocal()
    try:
        job = Job(
            id=job_id,
            type=type,
            source=source,
            status="queued",
            uploaded_by=uploaded_by,
            department=department,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    # ---------- Put the job on the Redis queue ----------
    try:
        queue.enqueue(
            "app.worker_tasks.process_job",   # path to the function the worker runs
            job_id,
            job_timeout=1800,                 # 30 min, repos can be slow
        )
    except RedisConnectionError:
        # Redis is down: mark the job failed so it doesn't sit in "queued" forever
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            job.status = "failed"
            job.error = "Could not connect to Redis. Is it running?"
            job.finished_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()
        raise HTTPException(503, "Queue is unavailable. Make sure Redis is running.")

    return {"job_id": job_id, "status": "queued", "type": type, "source": source}


def _my_uploader_ids(user) -> list[str]:
    # Older jobs stored the name, newer ones the email.
    return [v for v in (_user_field(user, "email"), _user_field(user, "name")) if v]


def _owns(user, job: Job) -> bool:
    return _user_field(user, "role") == "admin" or job.uploaded_by in _my_uploader_ids(user)


@router.get("/status/{job_id}")
def contribute_status(job_id: str, current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or not _owns(current_user, job):
            raise HTTPException(404, "Job not found.")
        return _job_to_dict(job)
    finally:
        db.close()


@router.get("/jobs")
def recent_jobs(limit: int = 20, current_user=Depends(get_current_user)):
    """Your recent contributions (admins: everyone's), newest first."""
    db = SessionLocal()
    try:
        q = db.query(Job)
        if _user_field(current_user, "role") != "admin":
            q = q.filter(Job.uploaded_by.in_(_my_uploader_ids(current_user)))
        jobs = q.order_by(Job.created_at.desc()).limit(min(limit, 100)).all()
        return [_job_to_dict(j) for j in jobs]
    finally:
        db.close()