"""Jobs the RQ worker runs. POST /contribute queues `process_job(job_id)`.

Start the worker from the backend/ folder (needs Redis running):
    rq worker ingest                       # macOS / Linux
    rq worker ingest --worker-class rq.worker.SimpleWorker   # Windows (no fork)
"""
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from app.database import SessionLocal  # noqa: E402
from app.models import Job  # noqa: E402

log = logging.getLogger("mercury.worker")


def _set(job_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        db.commit()
    finally:
        db.close()


def _original_filename(path: str, job_id: str) -> str:
    """Uploads are saved as '<job_id>_<name>'; show users the plain name."""
    name = os.path.basename(path)
    prefix = f"{job_id}_"
    return name[len(prefix):] if name.startswith(prefix) else name


def _error_text(exc: Exception) -> str:
    # FastAPI's HTTPException keeps the readable message in .detail
    detail = getattr(exc, "detail", None)
    return str(detail or exc)[:1000] or exc.__class__.__name__


def process_job(job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        kind, source = job.type, job.source
        department = job.department or "general"
        uploaded_by = job.uploaded_by or "unknown"
    finally:
        db.close()

    _set(job_id, status="processing")
    try:
        # Imported here so the heavy LangChain / embedding imports only load in the worker.
        if kind == "file":
            from app.rag import ingest_file
            from app.rag.config import DEFAULT_COLLECTION

            result = ingest_file(
                source,
                DEFAULT_COLLECTION,
                {
                    "source": _original_filename(source, job_id),
                    "type": "doc",
                    "department": department,
                    "uploaded_by": uploaded_by,
                    "doc_id": job_id,
                },
            )
            chunks = result["chunks"]
        elif kind == "repo":
            from app.routes.gittalk import index_repo

            chunks = index_repo(source, department, uploaded_by)["chunks"]
        elif kind == "wiki":
            from app.routes.sharebase import add_page

            chunks = add_page(source, department, uploaded_by)["chunks"]
        else:
            raise ValueError(f"Unknown job type '{kind}'")
    except Exception as exc:
        log.exception("Job %s failed", job_id)
        _set(job_id, status="failed", error=_error_text(exc), finished_at=datetime.utcnow())
        raise

    _set(job_id, status="done", chunks_added=chunks, finished_at=datetime.utcnow())
    return {"job_id": job_id, "chunks": chunks}
