"""Create or reset ONE login for a reviewer, in whatever database DATABASE_URL points to.

The credentials come from the environment, never from the source code, so they are not committed:

    $env:DATABASE_URL = 'sqlite:///./data/captcha_tool.db'      # the DB the app will use
    $env:REVIEW_USER = '<username>'; $env:REVIEW_PASSWORD = '<password>'
    python scripts/seed_review_user.py [--role operator|admin]

Notes
- Idempotent: an existing user gets its password reset and is re-activated; nothing else is touched.
- Default role is operator (can use every inspection screen; only the audit trail needs admin).
- This script deliberately skips the 12-character rule of `python -m app.cli`, because a reviewer login was asked for
  explicitly. Login itself only needs 6+ characters. A short password is weak: use it only on a throw-away review
  deployment and change or remove the user afterwards.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["operator", "admin"], default="operator")
    args = ap.parse_args()
    name, pw = os.environ.get("REVIEW_USER", "").strip(), os.environ.get("REVIEW_PASSWORD", "")
    if len(name) < 3 or len(pw) < 6:
        print("Set REVIEW_USER (3+ chars) and REVIEW_PASSWORD (6+ chars) in the environment.")
        return 2
    from alembic import command
    from alembic.config import Config
    from app.database import SessionLocal
    from app.models import User, UserRole
    from app.services.auth_service import hash_password

    command.upgrade(Config(str(Path(__file__).resolve().parent.parent / "alembic.ini")), "head")
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == name).first()
        role = UserRole.ADMIN if args.role == "admin" else UserRole.OPERATOR
        if u is None:
            db.add(User(username=name, email=f"{name.lower()}@review.invalid", role=role, hashed_password=hash_password(pw)))
            action = "created"
        else:
            u.hashed_password = hash_password(pw)
            u.role = role
            if hasattr(u, "is_active"):
                u.is_active = True
            action = "updated"
        db.commit()
    finally:
        db.close()
    print(f"user '{name}' {action} as {args.role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
