"""Database tables: users and department policies (auth), ingestion jobs,
and the feed (posts, votes, tag subscriptions)."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)

from .database import Base

# A user's status. Only "active" users can log in.
PENDING = "pending"     # signed up, waiting for an admin
ACTIVE = "active"       # approved (or created by an admin)
REJECTED = "rejected"   # an admin said no; they may request again
DISABLED = "disabled"   # was active, access removed by an admin
STATUSES = (PENDING, ACTIVE, REJECTED, DISABLED)


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)   # never the real password
    # The department the user actually has. For a pending user this is what
    # they asked for; the admin confirms or changes it when approving.
    department = Column(String(50), nullable=False)
    role = Column(String(20), nullable=False, default="member")  # "member" or "admin"
    status = Column(String(20), nullable=False, default=ACTIVE, server_default=ACTIVE, index=True)
    request_reason = Column(String(500))                  # "why I need access", from the sign-up form
    reviewed_by = Column(Integer, ForeignKey("users.id"))  # admin who approved/rejected
    reviewed_at = Column(DateTime)
    # Bump this number to log a user out everywhere (invalidates old tokens).
    token_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_now)

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE


class DepartmentPolicy(Base):
    """The 'rulebook': which content types each department may search."""
    __tablename__ = "department_policies"

    department = Column(String(50), primary_key=True)
    allowed_types = Column(String(100), nullable=False)  # comma-separated: "doc,wiki"

    @property
    def types(self) -> list[str]:
        return [t.strip() for t in self.allowed_types.split(",") if t.strip()]

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)          # uuid4
    type = Column(String)                          # "file" | "repo" | "wiki"
    source = Column(String)                        # filename / URL
    status = Column(String, default="queued")      # queued | processing | done | failed
    error = Column(Text, nullable=True)
    chunks_added = Column(Integer, default=0)
    uploaded_by = Column(String)
    department = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


# ---------- Feed ----------

class Post(Base):
    """An answer someone shared from the Ask page."""
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    official_tag = Column(String(50))           # the Ask mode it came from: all, gittalk, ...
    dept_tag = Column(String(50), index=True)   # the poster's department
    is_official = Column(Boolean, nullable=False, default=False)  # posted by an admin
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # naive UTC


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("user_id", "post_id"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    value = Column(Integer, nullable=False)     # +1 or -1 (a 0 vote deletes the row)


class Subscription(Base):
    """A user follows a tag and gets an email when a post carries it."""
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "tag"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tag = Column(String(50), nullable=False, index=True)
