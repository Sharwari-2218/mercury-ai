"""Feed: shared answers, votes, trending, and tag subscriptions with email alerts.

Who is posting, voting or subscribing always comes from the login, never from
the request body, so nobody can act as someone else.
"""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import ACTIVE, Post, Subscription, User, Vote
from ..notify import notify_tag_subscribers

router = APIRouter(tags=["feed"])

FEED_LIMIT = 100        # newest posts returned by /feed
TRENDING_POOL = 300     # newest posts considered when ranking /feed/trending
GRAVITY = 1.5           # Hacker News style decay


def clean_tag(tag: str | None) -> str | None:
    tag = (tag or "").strip().lstrip("#").lower()
    return tag[:50] or None


def post_tags(post: Post) -> list[str]:
    return [t for t in dict.fromkeys([post.dept_tag, post.official_tag]) if t]


# ---------- Reading the feed ----------

def _load_posts(db: Session, user: User, limit: int) -> list[dict]:
    """Newest posts with author name, vote totals and the viewer's own vote."""
    up = func.coalesce(func.sum(case((Vote.value > 0, 1), else_=0)), 0)
    down = func.coalesce(func.sum(case((Vote.value < 0, 1), else_=0)), 0)
    totals = (
        db.query(Vote.post_id, up.label("up"), down.label("down"))
        .group_by(Vote.post_id)
        .subquery()
    )
    rows = (
        db.query(Post, User.name, totals.c.up, totals.c.down)
        .join(User, User.id == Post.user_id)
        .outerjoin(totals, totals.c.post_id == Post.id)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit)
        .all()
    )
    ids = [p.id for p, *_ in rows]
    mine = dict(
        db.query(Vote.post_id, Vote.value)
        .filter(Vote.user_id == user.id, Vote.post_id.in_(ids))
        .all()
    ) if ids else {}

    out = []
    for post, author, upvotes, downvotes in rows:
        upvotes, downvotes = upvotes or 0, downvotes or 0
        out.append({
            "id": post.id,
            "question": post.question,
            "answer": post.answer,
            "official": post.is_official,
            "official_tag": post.official_tag,
            "dept_tag": post.dept_tag,
            "tags": post_tags(post),
            "user_name": author,
            # stored as naive UTC; the "Z" tells the browser it's UTC
            "created_at": post.created_at.isoformat() + "Z" if post.created_at else None,
            "upvotes": upvotes,
            "downvotes": downvotes,
            "score": upvotes - downvotes,
            "my_vote": mine.get(post.id, 0),
        })
    return out


def trending_score(score: int, created_at: datetime | None, now: datetime) -> float:
    """(upvotes - downvotes) / (hours_since_posted + 2) ** 1.5 — the Hacker News formula."""
    hours = max((now - created_at).total_seconds() / 3600, 0) if created_at else 0
    return score / (hours + 2) ** GRAVITY


@router.get("/feed")
def feed(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Newest first."""
    return _load_posts(db, user, FEED_LIMIT)


@router.get("/feed/trending")
def feed_trending(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Votes weighted toward newer posts. Ties go to the newer post."""
    posts = _load_posts(db, user, TRENDING_POOL)
    now = datetime.utcnow()
    for p in posts:
        created = datetime.fromisoformat(p["created_at"].rstrip("Z")) if p["created_at"] else None
        p["trending_score"] = round(trending_score(p["score"], created, now), 6)
    # Python's sort is stable and posts arrive newest first, so ties stay newest first.
    posts.sort(key=lambda p: -p["trending_score"])
    return posts[:FEED_LIMIT]


# ---------- Posting ----------

class PostIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    official_tag: str | None = Field(default=None, max_length=50)  # the Ask mode
    # The frontend also sends dept_tag, user_email and user_name. They're
    # ignored: the department and author come from the login.


@router.post("/posts", status_code=status.HTTP_201_CREATED)
def create_post(
    body: PostIn,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = Post(
        user_id=user.id,
        question=body.question.strip(),
        answer=body.answer.strip(),
        official_tag=clean_tag(body.official_tag),
        dept_tag=clean_tag(user.department),
        is_official=user.role == "admin",
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    # Email everyone following one of this post's tags (not the author, only active users).
    tags = post_tags(post)
    recipients = [
        email for (email,) in db.query(User.email)
        .join(Subscription, Subscription.user_id == User.id)
        .filter(Subscription.tag.in_(tags), User.id != user.id, User.status == ACTIVE)
        .distinct()
        .all()
    ] if tags else []
    if recipients:
        background.add_task(notify_tag_subscribers, recipients, tags, user.name, post.question, post.answer)

    return {"id": post.id, "tags": tags, "official": post.is_official, "alerts_sent_to": len(recipients)}


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Authors can delete their own posts; admins can delete any."""
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    if post.user_id != user.id and user.role != "admin":
        raise HTTPException(403, "You can only delete your own posts")
    db.query(Vote).filter(Vote.post_id == post_id).delete()
    db.delete(post)
    db.commit()


# ---------- Voting ----------

class VoteIn(BaseModel):
    value: int = Field(ge=-1, le=1)   # 1 = up, -1 = down, 0 = remove my vote


@router.post("/posts/{post_id}/vote")
def vote(post_id: int, body: VoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.get(Post, post_id) is None:
        raise HTTPException(404, "Post not found")
    existing = db.query(Vote).filter_by(user_id=user.id, post_id=post_id).one_or_none()
    if body.value == 0:
        if existing:
            db.delete(existing)
    elif existing:
        existing.value = body.value
    else:
        db.add(Vote(user_id=user.id, post_id=post_id, value=body.value))
    db.commit()

    up, down = db.query(
        func.coalesce(func.sum(case((Vote.value > 0, 1), else_=0)), 0),
        func.coalesce(func.sum(case((Vote.value < 0, 1), else_=0)), 0),
    ).filter(Vote.post_id == post_id).one()
    return {"post_id": post_id, "my_vote": body.value, "upvotes": up, "downvotes": down, "score": up - down}


# ---------- Tag subscriptions ----------
# The frontend passes ?email=..., which is ignored: you can only manage your own.

@router.get("/subscriptions")
def list_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Subscription.tag).filter_by(user_id=user.id).order_by(Subscription.tag).all()
    return [tag for (tag,) in rows]


class SubscriptionIn(BaseModel):
    tag: str = Field(min_length=1, max_length=50)


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def subscribe(body: SubscriptionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tag = clean_tag(body.tag)
    if not tag:
        raise HTTPException(422, "Tag can't be empty")
    if not db.query(Subscription).filter_by(user_id=user.id, tag=tag).one_or_none():
        db.add(Subscription(user_id=user.id, tag=tag))
        db.commit()
    return {"tag": tag, "following": True}


@router.delete("/subscriptions")
def unsubscribe(tag: str = Query(..., min_length=1), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    db.query(Subscription).filter_by(user_id=user.id, tag=clean_tag(tag)).delete()
    db.commit()
    return {"tag": clean_tag(tag), "following": False}
