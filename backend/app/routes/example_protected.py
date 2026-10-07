"""How to protect your existing routes. Copy these patterns into
gittalk.py, docsense.py, sharebase.py, databloom.py and the feed routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import access_filter, can_see_chunk, get_current_user, require_type
from ..database import get_db
from ..models import User

router = APIRouter()


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    repo: str | None = None


# Pattern 1: block a whole feature by content type.
# HR has no "code" permission, so they get 403 here no matter what the UI shows.
@router.post("/gittalk/ask")
def gittalk_ask(body: AskIn, user: User = Depends(require_type("code")), db: Session = Depends(get_db)):
    where = access_filter(user, db)
    # results = vectorstore.similarity_search(body.question, k=10, filter=where)
    return {"filter_used": where}


# Pattern 2: "All" mode search. Filter BOTH layers before RRF.
@router.post("/ask")
def ask_all(body: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    where = access_filter(user, db)
    # vector_hits = vectorstore.similarity_search(body.question, k=10, filter=where)
    # bm25_hits = bm25_search(body.question, k=50)                       # fetch extra...
    # bm25_hits = [d for d in bm25_hits if can_see_chunk(user, d.metadata, db)][:10]  # ...then filter
    # merged = rrf([vector_hits, bm25_hits])
    return {"filter_used": where}


# Pattern 3: anything fetched by ID must be checked (stops ID guessing).
@router.post("/databloom/{chunk_id}")
def databloom(chunk_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # chunk = vectorstore.get(ids=[chunk_id])
    chunk_metadata = {"type": "doc", "department": "hr"}  # placeholder for chunk["metadatas"][0]
    if not can_see_chunk(user, chunk_metadata, db):
        # 404 rather than 403, so users can't tell that the chunk exists.
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# Pattern 4: when ingesting, take department and uploaded_by from the user, never the form.
# metadata = {"source": filename, "type": "doc",
#             "department": user.department,     # or "all" if an admin marks it public
#             "uploaded_by": user.id}
