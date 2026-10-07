"""Create the first administrator (and starter department permissions).

Run from the backend folder:
    python create_admin.py

Or without prompts (useful in Docker):
    python create_admin.py --email admin@company.com --name "Admin"
    (the password is still asked for, or read from the ADMIN_PASSWORD env variable)

Running it again is safe: existing users and policies are left alone.
"""
import argparse
import getpass
import os

from dotenv import load_dotenv

load_dotenv()

from app.auth import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import DepartmentPolicy, User  # noqa: E402

DEFAULT_POLICIES = {
    "engineering": "code,doc,wiki",
    "hr": "doc,wiki",
    "sales": "doc,wiki",
}

parser = argparse.ArgumentParser(description="Create a Mercury AI administrator")
parser.add_argument("--email")
parser.add_argument("--name")
parser.add_argument("--department", default="engineering")
args = parser.parse_args()

Base.metadata.create_all(engine)
db = SessionLocal()

for dept, types in DEFAULT_POLICIES.items():
    if db.get(DepartmentPolicy, dept) is None:
        db.add(DepartmentPolicy(department=dept, allowed_types=types))
        print(f"Added department '{dept}' -> {types}")

def ask_password() -> str:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password (min 10 chars, typing is hidden): ")
    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters.")
    if not os.environ.get("ADMIN_PASSWORD") and getpass.getpass("Type it again: ") != password:
        raise SystemExit("The passwords didn't match. Nothing was changed.")
    return password


email = (args.email or input("Admin email: ")).lower().strip()
existing = db.query(User).filter(User.email == email).first()
if existing:
    if not existing.password_hash:   # account from before passwords existed
        existing.password_hash = hash_password(ask_password())
        print(f"Set a password for {email}.")
    if existing.role != "admin" or existing.status != "active":
        existing.role, existing.status = "admin", "active"
        print(f"{email} already existed; made an active admin.")
    else:
        print(f"{email} is already an admin. Nothing to do.")
else:
    name = (args.name or input("Admin name: ")).strip()
    password = ask_password()
    db.add(User(name=name, email=email, password_hash=hash_password(password),
                department=args.department.lower(), role="admin", status="active"))
    print(f"Admin {email} created.")

db.commit()
db.close()
