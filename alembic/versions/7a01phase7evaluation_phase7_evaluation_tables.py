"""Phase 7 evaluation tables: verification_records, ocr_benchmark_runs

Revision ID: 7a01phase7evaluation
Revises: 6b01phase6security
Create Date: 2026-11-07

Additive and idempotent (development databases are also upgraded by `init_db()` / `create_all`).
Downgrade deletes recorded verification attempts and OCR benchmark runs, so it is guarded by
ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1 like the earlier destructive downgrades.
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7a01phase7evaluation"
down_revision: Union[str, Sequence[str], None] = "6b01phase6security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "verification_records" not in tables:
        op.create_table(
            "verification_records",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("verification_mode", sa.String(length=24), nullable=False),
            sa.Column("scenario", sa.String(length=32), nullable=True),
            sa.Column("outcome", sa.String(length=40), nullable=False),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("provider_called", sa.Boolean(), nullable=False),
            sa.Column("provider_verified", sa.Boolean(), nullable=False),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("error_codes", sa.String(length=255), nullable=True),
            sa.Column("duration_ms", sa.Float(), nullable=True),
            sa.Column("token_source", sa.String(length=24), nullable=True),
            sa.Column("user_id", sa.String(length=36), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("created_at", "provider", "verification_mode", "outcome"):
            op.create_index(f"ix_verification_records_{col}", "verification_records", [col])

    if "ocr_benchmark_runs" not in tables:
        op.create_table(
            "ocr_benchmark_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("source", sa.String(length=24), nullable=False),
            sa.Column("dataset", sa.String(length=64), nullable=False),
            sa.Column("split", sa.String(length=16), nullable=False),
            sa.Column("engine", sa.String(length=32), nullable=False),
            sa.Column("samples", sa.Integer(), nullable=False),
            sa.Column("exact_matches", sa.Integer(), nullable=False),
            sa.Column("exact_match_pct", sa.Float(), nullable=False),
            sa.Column("char_accuracy_pct", sa.Float(), nullable=False),
            sa.Column("latency_ms_mean", sa.Float(), nullable=True),
            sa.Column("latency_ms_p95", sa.Float(), nullable=True),
            sa.Column("failures", sa.Integer(), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("user_id", sa.String(length=36), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("created_at", "split", "engine"):
            op.create_index(f"ix_ocr_benchmark_runs_{col}", "ocr_benchmark_runs", [col])


def downgrade() -> None:
    if os.environ.get("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "This downgrade deletes recorded verification attempts and OCR benchmark runs. "
            "Back up the database and set ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1 to proceed."
        )
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("ocr_benchmark_runs", "verification_records"):
        if table in tables:
            op.drop_table(table)
