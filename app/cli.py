import sys
import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import User, UserRole
from app.services.auth_service import hash_password
from app.config import settings


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
    p_admin.add_argument("--password", required=True, help="Strong password (min 8 chars)")

    # create-user
    p_user = subparsers.add_parser("create-user", help="Create a standard operator account")
    p_user.add_argument("--username", required=True, help="Operator username")
    p_user.add_argument("--email", required=True, help="Operator email")
    p_user.add_argument("--password", required=True, help="Password")
    p_user.add_argument("--role", default=UserRole.OPERATOR, choices=[UserRole.OPERATOR, UserRole.ADMIN])

    # list-users
    subparsers.add_parser("list-users", help="List registered users")

    # backup-db
    subparsers.add_parser("backup-db", help="Create safe timestamped SQLite backup")

    args = parser.parse_args()

    if args.command == "create-admin":
        if len(args.password) < 8:
            print("[ERROR] Password must be at least 8 characters long.")
            sys.exit(1)
        create_user_command(args.username, args.email, args.password, role=UserRole.ADMIN)

    elif args.command == "create-user":
        create_user_command(args.username, args.email, args.password, role=args.role)

    elif args.command == "list-users":
        list_users_command()

    elif args.command == "backup-db":
        backup_db_command()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
