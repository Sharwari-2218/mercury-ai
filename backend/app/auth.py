"""Authentication (who are you?) and authorization (what can you see?)."""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .database import get_db
from .models import DepartmentPolicy, User

# --- Settings (put JWT_SECRET in .env; generate with: python -c "import secrets; print(secrets.token_hex(32))")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET missing or too short. Set a 64-char random value in .env")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 7

password_hasher = PasswordHash.recommended()  # Argon2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# A real hash of a random string, used so "unknown email" takes as long as
# "wrong password". Otherwise attackers can time responses to find valid emails.
_DUMMY_HASH = password_hasher.hash("timing-attack-dummy-password")


# ---------- Passwords ----------
def hash_password(plain: str) -> str:
    return password_hasher.hash(plain)


def check_password(db: Session, email: str, password: str) -> User | None:
    """Returns the user if the email and password match, whatever their status.
    The caller decides what to say about pending/rejected/disabled accounts, and
    only does so AFTER the password was correct, so the status can't be used to
    discover which emails have accounts."""
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user is None:
        password_hasher.verify(password, _DUMMY_HASH)
        return None
    try:
        ok = password_hasher.verify(password, user.password_hash)
    except Exception:   # empty/old hash, e.g. users from before passwords existed
        ok = False
    return user if ok else None


# ---------- Tokens ----------
def _make_token(user: User, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "type": token_type,          # "access" or "refresh"; never accept one as the other
        "ver": user.token_version,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(user: User) -> str:
    return _make_token(user, "access", timedelta(minutes=ACCESS_TOKEN_MINUTES))


def create_refresh_token(user: User) -> str:
    return _make_token(user, "refresh", timedelta(days=REFRESH_TOKEN_DAYS))


def decode_token(token: str, expected_type: str, db: Session) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # algorithms= must be a fixed list; never trust the algorithm named in the token.
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise unauthorized
    if payload.get("type") != expected_type:
        raise unauthorized
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or payload.get("ver") != user.token_version:
        raise unauthorized
    return user


# ---------- FastAPI dependencies: use these in your routes ----------
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Add `user: User = Depends(get_current_user)` to any endpoint that needs login."""
    return decode_token(token, "access", db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return user


def allowed_types(user: User, db: Session) -> list[str]:
    if user.role == "admin":
        return ["code", "doc", "wiki"]
    policy = db.get(DepartmentPolicy, user.department)
    return policy.types if policy else []   # no policy = no access (fail closed)


def require_type(content_type: str):
    """Blocks a whole feature. Example: Depends(require_type("code")) on /gittalk routes."""
    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if content_type not in allowed_types(user, db):
            raise HTTPException(status_code=403, detail=f"Your department can't access '{content_type}' content")
        return user
    return checker


def access_filter(user: User, db: Session) -> dict | None:
    """Chroma `where` filter for this user. Pass it to EVERY similarity search,
    and apply can_see_chunk() to BM25 results too."""
    if user.role == "admin":
        return None
    return {"$and": [
        {"type": {"$in": allowed_types(user, db) or ["__none__"]}},
        {"department": {"$in": [user.department, "all"]}},
    ]}


def can_see_chunk(user: User, metadata: dict, db: Session) -> bool:
    """Same rule as access_filter, for results that didn't come from Chroma (BM25, chunk IDs)."""
    if user.role == "admin":
        return True
    return (metadata.get("type") in allowed_types(user, db)
            and metadata.get("department") in (user.department, "all"))


# ---------- Filters for the RAG routes ----------
# Content tagged department "all" is visible to every department.
PUBLIC_DEPARTMENT = "all"


def visible_departments(user: User) -> list[str] | None:
    """Departments whose content this user may see. None = everything (admins)."""
    if user.role == "admin":
        return None
    return [user.department, PUBLIC_DEPARTMENT]


def scope_filter(user: User, db: Session, **fixed) -> dict | None:
    """The search filter for this user, in the simple format the RAG layer uses
    ({"key": value} = equal, {"key": [a, b]} = any of). Pass the result as `where`
    to answer_question / hybrid_search: it's applied to BM25 AND vector results.

    `fixed` adds the feature's own conditions, e.g. type="doc" or source="a.pdf".
    A department in `fixed` narrows the search only if the user may see it;
    otherwise it's ignored and the user's normal departments apply.
    """
    fixed = {k: v for k, v in fixed.items() if v is not None}
    if user.role == "admin":
        return fixed or None

    where = dict(fixed)
    if "type" not in where:  # routes with a fixed type already passed require_type
        where["type"] = allowed_types(user, db) or ["__none__"]
    allowed_depts = visible_departments(user)
    if where.get("department") not in allowed_depts:
        where["department"] = allowed_depts
    return where


def ingest_department(user: User, requested: str | None = None) -> str:
    """Department to tag new content with. Members always use their own;
    admins may choose another one, or "all" to share it with everyone."""
    if user.role == "admin" and requested and requested.strip():
        return requested.strip().lower()
    return user.department
