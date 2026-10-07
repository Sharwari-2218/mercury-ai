"""Login, sign-up requests, admin approval, and user management."""
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .. import notify
from ..auth import (REFRESH_TOKEN_DAYS, allowed_types, check_password, create_access_token,
                    create_refresh_token, decode_token, get_current_user, hash_password,
                    require_admin)
from ..database import get_db
from ..models import ACTIVE, DISABLED, PENDING, REJECTED, DepartmentPolicy, User

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------- Settings (.env) ----------
# Set COOKIE_SECURE=false only for local http development.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
# "/" works behind any proxy prefix (Vite's /api, nginx). The cookie is only
# ever *accepted* by /auth/refresh and /auth/logout, so sending it elsewhere is harmless.
COOKIE_PATH = os.getenv("COOKIE_PATH", "/")
# Comma-separated company domains allowed to sign up, e.g. "acme.com,acme.in".
# Empty = any email may request access (the admin still has to approve).
ALLOWED_EMAIL_DOMAINS = [d.strip().lower().lstrip("@") for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()]
SIGNUPS_PER_HOUR = int(os.getenv("SIGNUPS_PER_HOUR", "10"))
VALID_TYPES = {"code", "doc", "wiki"}

STATUS_MESSAGES = {
    PENDING: "Your access request is waiting for an administrator to approve it. You'll get an email once it's done.",
    REJECTED: "Your access request was not approved. Contact your administrator if you think this is a mistake.",
    DISABLED: "Your account has been disabled. Contact your administrator.",
}


# ---------- Small helpers ----------
_signup_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit_signup(request: Request) -> None:
    """Simple in-memory limit per IP address. Fine for one backend process; if you run
    several, move this to Redis (or use slowapi with a Redis backend)."""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = _signup_hits[ip]
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= SIGNUPS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many sign-up attempts. Please try again later.")
    hits.append(now)


def _set_refresh_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        key="refresh_token",
        value=create_refresh_token(user),
        httponly=True,              # JavaScript can't read it, so XSS can't steal it
        secure=COOKIE_SECURE,       # only sent over HTTPS
        samesite="strict",          # not sent from other websites (CSRF protection)
        max_age=REFRESH_TOKEN_DAYS * 24 * 3600,
        path=COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie("refresh_token", path=COOKIE_PATH)


def _department_exists(db: Session, dept: str) -> bool:
    return db.get(DepartmentPolicy, dept) is not None


def _active_admin_emails(db: Session) -> list[str]:
    return [u.email for u in db.query(User).filter(User.role == "admin", User.status == ACTIVE).all()]


# ---------- Schemas ----------
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    department: str
    role: str
    status: str
    allowed_types: list[str] = []


class RequestOut(BaseModel):
    id: int
    name: str
    email: str
    department: str        # what the user asked for
    reason: str | None
    created_at: datetime | None


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    department: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    role: str = Field(default="member", pattern="^(member|admin)$")


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    department: str = Field(min_length=1, max_length=50)
    reason: str | None = Field(default=None, max_length=500)


class ApproveIn(BaseModel):
    department: str = Field(min_length=1, max_length=50)   # admin can change it here
    role: str = Field(default="member", pattern="^(member|admin)$")


class PolicyIn(BaseModel):
    department: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    allowed_types: list[str]


def _user_out(user: User, db: Session) -> UserOut:
    return UserOut(id=user.id, name=user.name, email=user.email, department=user.department,
                   role=user.role, status=user.status, allowed_types=allowed_types(user, db))


# ---------- Public: sign up ----------
@router.get("/signup-options")
def signup_options(db: Session = Depends(get_db)):
    """What the sign-up form needs: the department list and allowed email domains."""
    depts = [p.department for p in db.query(DepartmentPolicy).order_by(DepartmentPolicy.department).all()]
    return {"departments": depts, "allowed_domains": ALLOWED_EMAIL_DOMAINS}


SIGNUP_RECEIVED = {"message": "Request received. An administrator will review it, and you'll get an email when it's approved."}


@router.post("/signup", status_code=202)
def signup(body: SignupIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    _rate_limit_signup(request)
    email = body.email.lower().strip()
    dept = body.department.lower().strip()

    if ALLOWED_EMAIL_DOMAINS and email.rsplit("@", 1)[-1] not in ALLOWED_EMAIL_DOMAINS:
        raise HTTPException(status_code=422, detail="Please use your company email address.")
    if not _department_exists(db, dept):
        raise HTTPException(status_code=422, detail="Please choose a department from the list.")

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None and existing.status != REJECTED:
        # Already pending, active or disabled. Give the same answer as a new request,
        # so this form can't be used to check whether someone has an account.
        return SIGNUP_RECEIVED

    if existing is not None:   # rejected before: let them ask again
        user = existing
        user.name, user.department = body.name.strip(), dept
        user.password_hash = hash_password(body.password)
        user.status, user.role = PENDING, "member"
        user.reviewed_by = user.reviewed_at = None
        user.token_version += 1
    else:
        user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password),
                    department=dept, role="member", status=PENDING)
        db.add(user)
    user.request_reason = (body.reason or "").strip() or None
    db.commit()

    background.add_task(notify.notify_admins_of_request, _active_admin_emails(db), user.name, email, dept)
    return SIGNUP_RECEIVED


# ---------- Login / session ----------
@router.post("/login", response_model=TokenOut)
def login(response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form uses the field name "username"; we put the email in it.
    user = check_password(db, form.username, form.password)
    if user is None:
        # Same message for wrong email and wrong password, so attackers can't find valid emails.
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.status != ACTIVE:
        # Only reached with the correct password, so it's safe to explain.
        raise HTTPException(status_code=403, detail=STATUS_MESSAGES.get(user.status, "Account not active"))
    _set_refresh_cookie(response, user)
    return TokenOut(access_token=create_access_token(user))


@router.post("/refresh", response_model=TokenOut)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Not logged in")
    user = decode_token(refresh_token, "refresh", db)
    _set_refresh_cookie(response, user)   # rotate the refresh token too
    return TokenOut(access_token=create_access_token(user))


@router.post("/logout")
def logout(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    """Works even if the access token has expired: it uses the refresh cookie."""
    if refresh_token:
        try:
            user = decode_token(refresh_token, "refresh", db)
            user.token_version += 1   # every existing token for this user stops working
            db.commit()
        except HTTPException:
            pass                      # already invalid; just clear the cookie
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_out(user, db)


# ---------- Admin: access requests ----------
@router.get("/requests", response_model=list[RequestOut])
def list_requests(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    pending = db.query(User).filter(User.status == PENDING).order_by(User.created_at).all()
    return [RequestOut(id=u.id, name=u.name, email=u.email, department=u.department,
                       reason=u.request_reason, created_at=u.created_at) for u in pending]


def _get_pending(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.status != PENDING:
        raise HTTPException(status_code=404, detail="Request not found or already handled")
    return user


@router.post("/requests/{user_id}/approve", response_model=UserOut)
def approve_request(user_id: int, body: ApproveIn, background: BackgroundTasks,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = _get_pending(db, user_id)
    dept = body.department.lower().strip()
    if not _department_exists(db, dept):
        raise HTTPException(status_code=422, detail=f"Department '{dept}' doesn't exist. Add it under permissions first.")
    user.department, user.role, user.status = dept, body.role, ACTIVE
    user.reviewed_by, user.reviewed_at = admin.id, datetime.now(timezone.utc)
    db.commit()
    background.add_task(notify.notify_user_approved, user.email, user.name, dept)
    return _user_out(user, db)


@router.post("/requests/{user_id}/reject")
def reject_request(user_id: int, background: BackgroundTasks,
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = _get_pending(db, user_id)
    user.status = REJECTED
    user.reviewed_by, user.reviewed_at = admin.id, datetime.now(timezone.utc)
    db.commit()
    background.add_task(notify.notify_user_rejected, user.email, user.name)
    return {"ok": True}


# ---------- Admin: users ----------
@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.status != PENDING).order_by(User.id).all()
    return [_user_out(u, db) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admins can still add someone directly, skipping the request step."""
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered (check pending requests too)")
    dept = body.department.lower()
    if not _department_exists(db, dept):
        raise HTTPException(status_code=422, detail=f"Department '{dept}' doesn't exist")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password),
                department=dept, role=body.role, status=ACTIVE)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user, db)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't disable your own account")
    user = db.get(User, user_id)
    if user is None or user.status != ACTIVE:
        raise HTTPException(status_code=404, detail="Active user not found")
    user.status = DISABLED
    user.token_version += 1   # logs them out everywhere immediately
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/activate")
def activate_user(user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.status != DISABLED:
        raise HTTPException(status_code=404, detail="Disabled user not found")
    user.status = ACTIVE
    db.commit()
    return {"ok": True}


# ---------- Admin: department permissions ----------
@router.get("/policies")
def list_policies(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"department": p.department, "allowed_types": p.types}
            for p in db.query(DepartmentPolicy).order_by(DepartmentPolicy.department).all()]


@router.put("/policies")
def set_policy(body: PolicyIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    bad = set(body.allowed_types) - VALID_TYPES
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown types: {sorted(bad)}")
    dept = body.department.lower()
    policy = db.get(DepartmentPolicy, dept)
    if policy is None:
        policy = DepartmentPolicy(department=dept, allowed_types="")
        db.add(policy)
    policy.allowed_types = ",".join(sorted(set(body.allowed_types)))
    db.commit()
    return {"department": dept, "allowed_types": policy.types}
