"""Real-world QA: preserved CSV row, expected-vs-detected, widget evidence, review link

Revision ID: 8a01realworldqa
Revises: 7a01phase7evaluation
Create Date: 2026-11-07

Additive and idempotent: only adds nullable/defaulted columns (development databases are also upgraded in place by
`init_db()`). Downgrade drops those columns, which discards the preserved CSV rows and per-site evidence, so it is
guarded by ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1 like the other destructive downgrades.
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8a01realworldqa"
down_revision: Union[str, Sequence[str], None] = "7a01phase7evaluation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INSPECTION_COLUMNS = [
    ("source_row", sa.Text()), ("expected_captcha_raw", sa.String(128)), ("expected_captcha", sa.String(40)),
    ("expected_contact_page", sa.String(1024)), ("platform", sa.String(128)), ("city", sa.String(128)),
    ("state", sa.String(64)), ("category", sa.String(128)), ("captcha_subtype", sa.String(40)),
    ("widget_state", sa.String(24)), ("widget_loaded", sa.Boolean()), ("result_category", sa.String(24)),
    ("robots_status", sa.String(24)), ("form_probe", sa.Text()), ("evidence", sa.Text()),
    ("screenshot_path", sa.String(512)),
]


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)} if table in insp.get_table_names() else set()


def upgrade() -> None:
    present = _cols("website_inspections")
    if present:
        for name, typ in INSPECTION_COLUMNS:
            if name not in present:
                op.add_column("website_inspections", sa.Column(name, typ, nullable=True))
        if "result_category" not in present:
            op.create_index("ix_website_inspections_result_category", "website_inspections", ["result_category"])
    if _cols("human_reviews") and "inspection_id" not in _cols("human_reviews"):
        op.add_column("human_reviews", sa.Column("inspection_id", sa.String(36), nullable=True))
        op.create_index("ix_human_reviews_inspection_id", "human_reviews", ["inspection_id"])


def downgrade() -> None:
    if os.environ.get("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "This downgrade discards preserved CSV rows, expected-vs-detected data and per-site evidence. "
            "Back up the database and set ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1 to proceed."
        )
    with op.batch_alter_table("human_reviews") as b:
        if "inspection_id" in _cols("human_reviews"):
            b.drop_index("ix_human_reviews_inspection_id")
            b.drop_column("inspection_id")
    present = _cols("website_inspections")
    with op.batch_alter_table("website_inspections") as b:
        if "result_category" in present:
            b.drop_index("ix_website_inspections_result_category")
        for name, _ in INSPECTION_COLUMNS:
            if name in present:
                b.drop_column(name)
