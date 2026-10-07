"""One-time upgrade of an existing mercury.db to the login + sign-up version.
Works whether your users table is the original MVP one (id, name, email, department)
or the first auth version. Keeps all users, posts and votes. Safe to run more than once.

    python migrate_signup.py

Users that existed before passwords did can't sign in (they have no password),
so they're set to "disabled". Running create_admin.py with one of their emails
gives that account a password and makes it the admin.
"""
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL", "sqlite:///./mercury.db")
if not url.startswith("sqlite:///"):
    raise SystemExit("This script is for SQLite. On Postgres, use Alembic for migrations.")
path = url.removeprefix("sqlite:///")
if not os.path.exists(path):
    raise SystemExit(f"{path} not found. Nothing to migrate; just run create_admin.py.")

con = sqlite3.connect(path)
if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
    raise SystemExit("No users table yet. Nothing to migrate; just run create_admin.py.")

cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
had_passwords = "password_hash" in cols

ADD = [
    ("password_hash", "VARCHAR(255) NOT NULL DEFAULT ''"),
    ("role", "VARCHAR(20) NOT NULL DEFAULT 'member'"),
    ("token_version", "INTEGER NOT NULL DEFAULT 0"),
    ("created_at", "DATETIME"),
    ("status", "VARCHAR(20) NOT NULL DEFAULT 'active'"),
    ("request_reason", "VARCHAR(500)"),
    ("reviewed_by", "INTEGER REFERENCES users(id)"),
    ("reviewed_at", "DATETIME"),
]
for name, ddl in ADD:
    if name not in cols:
        con.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
        print(f"Added users.{name}")

if "is_active" in cols and "status" not in cols:
    con.execute("UPDATE users SET status = CASE WHEN is_active THEN 'active' ELSE 'disabled' END")
if "is_active" in cols:
    # The old column is NOT NULL with no default, so new sign-ups would fail while it exists.
    con.execute("ALTER TABLE users DROP COLUMN is_active")   # needs SQLite 3.35+
    print("Removed old users.is_active")

# Fill in blanks left by the original MVP table.
con.execute("UPDATE users SET department = 'engineering' WHERE department IS NULL OR department = ''")
con.execute("UPDATE users SET name = email WHERE name IS NULL OR name = ''")
n = con.execute("UPDATE users SET status = 'disabled' WHERE password_hash = ''").rowcount
if n:
    print(f"{n} old user(s) have no password and were set to 'disabled'.")
    print("  -> They can't sign in. Re-create them from the Admin page, or run create_admin.py with")
    print("     your own old email to turn your account into the admin with a password.")
con.execute("CREATE INDEX IF NOT EXISTS ix_users_status ON users (status)")
con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")

con.commit()
con.close()
print("Done." if had_passwords or n == 0 else "Done. Next: python create_admin.py")
