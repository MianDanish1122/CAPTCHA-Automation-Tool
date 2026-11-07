from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.models import Base

# SQLite connect_args for multithreaded / async access
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

# Columns added after the first release. `create_all` never alters existing tables, so
# databases created by earlier phases are upgraded in place (additive, idempotent).
_ADDITIVE_COLUMNS = {
    "users": [("token_version", "INTEGER NOT NULL DEFAULT 0")],
    "audit_logs": [
        ("seq", "INTEGER"),
        ("prev_hash", "VARCHAR(64)"),
        ("entry_hash", "VARCHAR(64)"),
        ("key_id", "VARCHAR(16)"),
    ],
    "website_inspections": [
        ("source_row", "TEXT"), ("expected_captcha_raw", "VARCHAR(128)"), ("expected_captcha", "VARCHAR(40)"),
        ("expected_contact_page", "VARCHAR(1024)"), ("platform", "VARCHAR(128)"), ("city", "VARCHAR(128)"),
        ("state", "VARCHAR(64)"), ("category", "VARCHAR(128)"), ("captcha_subtype", "VARCHAR(40)"),
        ("widget_state", "VARCHAR(24)"), ("widget_loaded", "BOOLEAN DEFAULT 0"), ("result_category", "VARCHAR(24)"),
        ("robots_status", "VARCHAR(24)"), ("form_probe", "TEXT"), ("evidence", "TEXT"),
        ("screenshot_path", "VARCHAR(512)"),
    ],
    "human_reviews": [
        ("inspection_id", "VARCHAR(36)"),
        ("reviewed_by_id", "VARCHAR(36)"),
        ("reviewed_by_username", "VARCHAR(64)"),
        ("decision_count", "INTEGER NOT NULL DEFAULT 0"),
    ],
}

# Database-level append-only guard for the audit trail (SQLite). Updates and deletes are
# aborted; tampering by anyone who bypasses the app is additionally detectable via the HMAC chain.
_AUDIT_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
    BEFORE UPDATE ON audit_logs
    BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
    BEFORE DELETE ON audit_logs
    BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS review_decisions_no_update
    BEFORE UPDATE ON review_decisions
    BEGIN SELECT RAISE(ABORT, 'review_decisions is append-only'); END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS review_decisions_no_delete
    BEFORE DELETE ON review_decisions
    BEGIN SELECT RAISE(ABORT, 'review_decisions is append-only'); END;
    """,
]


def _upgrade_schema() -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        if "audit_logs" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_seq ON audit_logs (seq)"))
        if engine.dialect.name == "sqlite":
            for trigger in _AUDIT_TRIGGERS:
                conn.execute(text(trigger))


def init_db() -> None:
    """Initialize database tables, apply additive upgrades, and install audit guards."""
    Base.metadata.create_all(bind=engine)
    _upgrade_schema()


# Auto-ensure tables exist on module import
init_db()


def get_db():
    """FastAPI database session dependency."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
