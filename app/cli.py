import os
import sys
import getpass
import secrets
import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import User, UserRole
from app.services.auth_service import hash_password
from app.config import settings


MIN_PASSWORD_LENGTH = 12


def obtain_password(args) -> tuple[str, bool]:
    """
    Resolve a password WITHOUT embedding it in source or (preferably) the command line.
    Order: --generate-password, ADMIN_PASSWORD env var, --password (warned), interactive prompt.
    Returns (password, was_generated).
    """
    if getattr(args, "generate_password", False):
        return secrets.token_urlsafe(24), True
    env_pw = os.environ.get("ADMIN_PASSWORD")
    if env_pw:
        return env_pw, False
    if getattr(args, "password", None):
        print("[WARN] --password exposes the secret in shell history and process listings.")
        return args.password, False
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Confirm password: "):
        print("[ERROR] Passwords do not match.")
        sys.exit(1)
    return first, False


def create_user_command(username, email, password, role=UserRole.ADMIN):
    """CLI utility to create an initial or administrative user."""
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"[ERROR] User with username '{username}' already exists.")
            return False

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"[SUCCESS] Created {role.upper()} user '{username}' (ID: {user.id}) successfully.")
        return True
    finally:
        db.close()


def list_users_command():
    """List all registered system users."""
    init_db()
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print("\nRegistered Users:")
        print("-" * 65)
        print(f"{'Username':<20} {'Email':<25} {'Role':<10} {'Active':<8}")
        print("-" * 65)
        for u in users:
            print(f"{u.username:<20} {u.email:<25} {u.role:<10} {str(u.is_active):<8}")
        print("-" * 65)
    finally:
        db.close()


def backup_db_command():
    """Create a point-in-time timestamped backup of the SQLite database."""
    db_file = settings.BASE_DIR / "data" / "captcha_tool.db"
    if not db_file.exists():
        print(f"[ERROR] Database file not found at {db_file}")
        return False

    backup_dir = settings.BASE_DIR / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"captcha_tool_backup_{timestamp}.db"

    shutil.copy2(db_file, backup_path)
    print(f"[SUCCESS] Database safely backed up to:\n  {backup_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="CAPTCHA Inspector Security & Administration CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # create-admin
    p_admin = subparsers.add_parser("create-admin", help="Create an administrator account")
    p_admin.add_argument("--username", required=True, help="Administrator username")
    p_admin.add_argument("--email", required=True, help="Administrator email")
    p_admin.add_argument(
        "--password",
        help="NOT RECOMMENDED (visible in shell history/process list). "
             "Omit to be prompted securely, or use --generate-password / ADMIN_PASSWORD env var.",
    )
    p_admin.add_argument(
        "--generate-password",
        action="store_true",
        help="Generate a strong random password and print it ONCE.",
    )

    # create-user
    p_user = subparsers.add_parser("create-user", help="Create a standard operator account")
    p_user.add_argument("--username", required=True, help="Operator username")
    p_user.add_argument("--email", required=True, help="Operator email")
    p_user.add_argument("--password", help="NOT RECOMMENDED; omit to be prompted or use --generate-password.")
    p_user.add_argument("--generate-password", action="store_true", help="Generate a random password and print it once.")
    p_user.add_argument("--role", default=UserRole.OPERATOR, choices=[UserRole.OPERATOR, UserRole.ADMIN])

    # list-users
    subparsers.add_parser("list-users", help="List registered users")

    # backup-db
    subparsers.add_parser("backup-db", help="Create safe timestamped SQLite backup")

    args = parser.parse_args()

    if args.command == "create-admin":
        password, generated = obtain_password(args)
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"[ERROR] Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
            sys.exit(1)
        if create_user_command(args.username, args.email, password, role=UserRole.ADMIN) and generated:
            print("\nGenerated administrator password (shown ONCE, store it in a password manager):")
            print(f"  {password}")

    elif args.command == "create-user":
        password, generated = obtain_password(args)
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"[ERROR] Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
            sys.exit(1)
        if create_user_command(args.username, args.email, password, role=args.role) and generated:
            print("\nGenerated password (shown ONCE, store it in a password manager):")
            print(f"  {password}")

    elif args.command == "list-users":
        list_users_command()

    elif args.command == "backup-db":
        backup_db_command()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
