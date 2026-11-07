import os
import sys
import getpass
import secrets
import argparse
import shutil
import json
import sqlite3
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


def _db_file() -> Path:
    """Path of the configured SQLite database (the CLI backup/restore only supports SQLite)."""
    from app.database import engine
    if engine.dialect.name != "sqlite":
        print("[ERROR] backup/restore commands support SQLite only; use your database's native tooling.")
        sys.exit(2)
    return Path(engine.url.database)


def _chain_report_for_file(path: Path, expected_seq=None, expected_hash=None) -> dict:
    """Verify the audit chain of ANY sqlite file (live DB, backup, or restore candidate)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.services.audit import verify_audit_chain
    eng = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with sessionmaker(bind=eng)() as session:
            return verify_audit_chain(session, expected_head_seq=expected_seq, expected_head_hash=expected_hash)
    finally:
        eng.dispose()


def backup_db_command():
    """
    Consistent online backup (SQLite backup API, safe while the app is running) plus a
    `.head.json` sidecar with the audit-chain head. COPY THE HEAD (seq + hash) TO WRITE-ONCE
    STORAGE: it is what lets a later restore prove the log was not truncated or rolled back.
    """
    db_file = _db_file()
    if not db_file.exists():
        print(f"[ERROR] Database file not found at {db_file}")
        return False

    backup_dir = settings.BASE_DIR / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"captcha_tool_backup_{timestamp}.db"

    src = sqlite3.connect(str(db_file))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    report = _chain_report_for_file(backup_path)
    sidecar = backup_path.with_suffix(".head.json")
    sidecar.write_text(json.dumps({
        "backup": backup_path.name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "audit_chain_valid": report.get("valid"),
        "audit_head_seq": report.get("head_seq"),
        "audit_head_hash": report.get("head_hash"),
    }, indent=2), encoding="utf-8")
    print(f"[SUCCESS] Database safely backed up to:\n  {backup_path}")
    print(f"  audit chain valid={report.get('valid')} head_seq={report.get('head_seq')}")
    print(f"  head hash recorded in {sidecar.name} - also store it OFF this machine (write-once).")
    return True


def restore_db_command(backup_file: str, expected_seq=None, expected_hash=None, assume_yes=False):
    """
    Restore a backup over the live database (STOP THE APPLICATION FIRST).
    Safety: SQLite integrity check + audit-chain verification of the candidate (optionally
    against an externally recorded head) BEFORE anything is replaced, and the current database
    is preserved as data/backups/pre_restore_<timestamp>.db.
    """
    candidate = Path(backup_file)
    if not candidate.exists():
        print(f"[ERROR] Backup file not found: {candidate}")
        return False

    con = sqlite3.connect(str(candidate))
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    if integrity != "ok":
        print(f"[ERROR] SQLite integrity check failed: {integrity}")
        return False

    report = _chain_report_for_file(candidate, expected_seq, expected_hash)
    if not report.get("valid"):
        print(f"[ERROR] Audit chain verification FAILED for the backup: {report.get('problem')}")
        return False
    print(f"[OK] Backup integrity ok; audit chain valid (head_seq={report.get('head_seq')}).")

    if not assume_yes:
        print("[ABORT] Re-run with --yes to replace the live database (application must be stopped).")
        return False

    live = _db_file()
    safety = None
    if live.exists():
        safety_dir = settings.BASE_DIR / "data" / "backups"
        safety_dir.mkdir(parents=True, exist_ok=True)
        safety = safety_dir / f"pre_restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(live, safety)
    for suffix in ("-wal", "-shm"):
        side = Path(str(live) + suffix)
        if side.exists():
            side.unlink()
    shutil.copy2(candidate, live)
    print(f"[SUCCESS] Restored {candidate.name} -> {live}")
    if safety:
        print(f"  previous database preserved at {safety}")
    return True


def audit_verify_command(expected_seq=None, expected_hash=None) -> bool:
    report = _chain_report_for_file(_db_file(), expected_seq, expected_hash)
    print(json.dumps({k: v for k, v in report.items()}, indent=2))
    return bool(report.get("valid"))


def invalidate_sessions_command(username=None, everyone=False) -> bool:
    """Bump token_version so every outstanding JWT (of one user, or of everyone) stops working."""
    init_db()
    db = SessionLocal()
    try:
        query = db.query(User)
        if username:
            query = query.filter(User.username == username)
        elif not everyone:
            print("[ERROR] Specify --user NAME or --all.")
            return False
        users = query.all()
        for u in users:
            u.token_version = (u.token_version or 0) + 1
        db.commit()
        print(f"[SUCCESS] Invalidated all sessions for {len(users)} user(s).")
        return bool(users)
    finally:
        db.close()


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

    # backup-db / restore-db
    subparsers.add_parser("backup-db", help="Consistent SQLite backup + audit head sidecar")
    p_restore = subparsers.add_parser("restore-db", help="Verify then restore a backup (stop the app first)")
    p_restore.add_argument("--file", required=True, help="Backup file to restore")
    p_restore.add_argument("--expected-head-seq", type=int, help="Externally recorded audit head sequence")
    p_restore.add_argument("--expected-head-hash", help="Externally recorded audit head hash")
    p_restore.add_argument("--yes", action="store_true", help="Actually replace the live database")

    # audit tooling
    p_av = subparsers.add_parser("audit-verify", help="Verify the audit hash chain (exit code 1 if invalid)")
    p_av.add_argument("--expected-head-seq", type=int)
    p_av.add_argument("--expected-head-hash")
    subparsers.add_parser("generate-audit-key", help="Print a NEW random AUDIT_HMAC_KEY value")

    # sessions
    p_inv = subparsers.add_parser("invalidate-sessions", help="Revoke all issued tokens of a user or everyone")
    p_inv.add_argument("--user", help="Username")
    p_inv.add_argument("--all", action="store_true", help="Every user")

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

    elif args.command == "restore-db":
        ok = restore_db_command(args.file, args.expected_head_seq, args.expected_head_hash, args.yes)
        sys.exit(0 if ok else 1)

    elif args.command == "audit-verify":
        sys.exit(0 if audit_verify_command(args.expected_head_seq, args.expected_head_hash) else 1)

    elif args.command == "generate-audit-key":
        print(secrets.token_hex(32))

    elif args.command == "invalidate-sessions":
        sys.exit(0 if invalidate_sessions_command(args.user, args.all) else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
