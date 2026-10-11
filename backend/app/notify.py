"""Emails for sign-up requests. Reuses the same Gmail SMTP settings as your tag alerts.

.env:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=you@gmail.com
    SMTP_PASSWORD=<Gmail app password>
    APP_URL=http://localhost:5173

If SMTP_HOST is not set, emails are only printed to the log, so the app works without it.
"""
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("mercury.notify")


def send_email(to: str, subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    if not host:
        log.warning("SMTP not configured; would have emailed %s: %s", to, subject)
        return
    msg = EmailMessage()   # EmailMessage rejects newlines in headers (no header injection)
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
            smtp.starttls()
            smtp.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
    except Exception:  # an email failure must never break sign-up or approval
        log.exception("Could not send email to %s", to)


def _app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:5173").rstrip("/")


def notify_admins_of_request(admin_emails: list[str], name: str, email: str, department: str) -> None:
    for admin in admin_emails:
        send_email(
            admin,
            "Mercury AI: new access request",
            f"{name} ({email}) has asked to join Mercury AI as part of '{department}'.\n\n"
            f"Review it here: {_app_url()}/admin\n",
        )


def notify_user_approved(to: str, name: str, department: str) -> None:
    send_email(
        to,
        "Your Mercury AI access was approved",
        f"Hi {name},\n\nYour access request was approved. You've been added to '{department}'.\n\n"
        f"Sign in here: {_app_url()}/login\n",
    )


def notify_user_rejected(to: str, name: str) -> None:
    send_email(
        to,
        "Your Mercury AI access request",
        f"Hi {name},\n\nYour access request was not approved. "
        "If you think this is a mistake, please contact your administrator.\n",
    )


# ---------- Feed tag alerts ----------

def notify_tag_subscribers(recipients: list[str], tags: list[str], author: str,
                           question: str, answer: str) -> None:
    """Runs in a FastAPI BackgroundTask after a post is created, so the request isn't blocked."""
    if not recipients:
        return
    tag_text = ", ".join(f"#{t}" for t in tags)
    preview = answer.strip()
    if len(preview) > 600:
        preview = preview[:600].rsplit(" ", 1)[0] + "…"
    for to in recipients:
        send_email(
            to,
            f"Mercury AI: new post in {tag_text}",
            f"{author} posted an answer tagged {tag_text}.\n\n"
            f"Q: {question.strip()}\n\n{preview}\n\n"
            f"Read it on the feed: {_app_url()}/feed\n\n"
            "You get this email because you follow one of these tags. "
            "Unfollow it on the Feed page to stop these alerts.\n",
        )
