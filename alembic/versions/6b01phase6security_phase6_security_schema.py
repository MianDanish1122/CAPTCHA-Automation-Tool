"""Phase 6A/6B security schema: token versions, revocation list, audit hash chain, review history

Revision ID: 6b01phase6security
Revises: 5eb94b849402
Create Date: 2026-11-07

Additive and IDEMPOTENT: every step checks whether the object already exists, because
development databases are also upgraded in place by `app.database.init_db()`.

Upgrade
  users.token_version             invalidation counter for issued JWTs (default 0)
  audit_logs.seq/prev_hash/       tamper-evident HMAC hash chain (existing rows stay NULL =
    entry_hash/key_id               "legacy, unchained"; nothing is rewritten)
  human_reviews.reviewed_by_*,    reviewer identity of the latest decision
    decision_count
  revoked_tokens                  denylist of individually revoked JWTs
  review_decisions                append-only decision history
  SQLite triggers                 block UPDATE/DELETE on audit_logs and review_decisions

Downgrade is INTENTIONALLY DESTRUCTIVE (it deletes the revocation list, review decision history
and the audit hash chain) and therefore requires ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1.
Existing users, scans, pages, reviews and audit rows themselves are preserved.
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6b01phase6security"
down_revision: Union[str, Sequence[str], None] = "5eb94b849402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRIGGERS = {
    "audit_logs_no_update": "CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs "
                            "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;",
    "audit_logs_no_delete": "CREATE TRIGGER audit_logs_no_delete BEFORE DELETE ON audit_logs "
                            "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;",
    "review_decisions_no_update": "CREATE TRIGGER review_decisions_no_update BEFORE UPDATE ON review_decisions "
                                  "BEGIN SELECT RAISE(ABORT, 'review_decisions is append-only'); END;",
    "review_decisions_no_delete": "CREATE TRIGGER review_decisions_no_delete BEFORE DELETE ON review_decisions "
                                  "BEGIN SELECT RAISE(ABORT, 'review_decisions is append-only'); END;",
}

NEW_COLUMNS = {
    "users": [sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")],
    "audit_logs": [
        sa.Column("seq", sa.Integer(), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("entry_hash", sa.String(length=64), nullable=True),
        sa.Column("key_id", sa.String(length=16), nullable=True),
    ],
    "human_reviews": [
        sa.Column("reviewed_by_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by_username", sa.String(length=64), nullable=True),
        sa.Column("decision_count", sa.Integer(), nullable=False, server_default="0"),
    ],
}


def _inspector():
    return sa.inspect(op.get_bind())


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    insp = _inspector()
    tables = set(insp.get_table_names())

    for table, columns in NEW_COLUMNS.items():
        present = {c["name"] for c in insp.get_columns(table)}
        for column in columns:
            if column.name not in present:
                op.add_column(table, column)

    if "revoked_tokens" not in tables:
        op.create_table(
            "revoked_tokens",
            sa.Column("jti", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(length=64), nullable=True),
            sa.PrimaryKeyConstraint("jti"),
        )
        op.create_index("ix_revoked_tokens_user_id", "revoked_tokens", ["user_id"])
        op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])

    if "review_decisions" not in tables:
        op.create_table(
            "review_decisions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("review_id", sa.String(length=36), nullable=False),
            sa.Column("decided_at", sa.DateTime(), nullable=False),
            sa.Column("decided_by_id", sa.String(length=36), nullable=False),
            sa.Column("decided_by_username", sa.String(length=64), nullable=False),
            sa.Column("decided_by_role", sa.String(length=32), nullable=True),
            sa.Column("previous_status", sa.String(length=32), nullable=False),
            sa.Column("new_status", sa.String(length=32), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.ForeignKeyConstraint(["review_id"], ["human_reviews.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_review_decisions_review_id", "review_decisions", ["review_id"])

    existing_audit_indexes = {i["name"] for i in _inspector().get_indexes("audit_logs")}
    if "ix_audit_logs_seq" not in existing_audit_indexes:
        op.create_index("ix_audit_logs_seq", "audit_logs", ["seq"])

    if _is_sqlite():
        present_triggers = {
            r[0] for r in op.get_bind().execute(sa.text("SELECT name FROM sqlite_master WHERE type='trigger'"))
        }
        for name, ddl in TRIGGERS.items():
            if name not in present_triggers:
                op.execute(ddl)


def downgrade() -> None:
    if os.environ.get("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "This downgrade permanently deletes the token revocation list, review decision history "
            "and the audit hash chain columns. Back up the database and set "
            "ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1 to proceed."
        )
    if _is_sqlite():
        for name in TRIGGERS:
            op.execute(f"DROP TRIGGER IF EXISTS {name}")

    insp = _inspector()
    tables = set(insp.get_table_names())
    for table in ("review_decisions", "revoked_tokens"):
        if table in tables:
            op.drop_table(table)

    if "ix_audit_logs_seq" in {i["name"] for i in _inspector().get_indexes("audit_logs")}:
        op.drop_index("ix_audit_logs_seq", table_name="audit_logs")

    for table, columns in NEW_COLUMNS.items():
        present = {c["name"] for c in _inspector().get_columns(table)}
        to_drop = [c.name for c in columns if c.name in present]
        if to_drop:
            with op.batch_alter_table(table) as batch:
                for name in to_drop:
                    batch.drop_column(name)
