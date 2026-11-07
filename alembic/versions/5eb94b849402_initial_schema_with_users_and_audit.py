"""baseline: Phase 1-5 schema (users, audit log, scans, reviews, ...)

Revision ID: 5eb94b849402
Revises:
Create Date: 2026-11-07

This revision was an EMPTY stub in Phase 5 (every database was built by
`Base.metadata.create_all`). It now creates the Phase 1-5 schema, but only for tables that
do not exist yet, so:

  * a brand-new database gets the full Phase 5 schema from `alembic upgrade head`;
  * an existing Phase 5 database (already stamped with this revision, or never stamped)
    is left untouched by this step and only receives the Phase 6 changes.

Downgrading this revision drops EVERY application table. That is intentionally guarded.
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5eb94b849402"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_created: set[str] = set()


def _existing() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _ct(name, *args, **kwargs):
    """create_table only if absent (idempotent against databases built by create_all)."""
    if name not in _existing():
        op.create_table(name, *args, **kwargs)
        _created.add(name)


def _ci(name, table, columns, unique=False):
    """Create indexes only for tables created by this run (existing tables keep theirs)."""
    if table in _created:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    _created.clear()
    _ct('audit_logs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.Column('actor_id', sa.String(length=36), nullable=True),
    sa.Column('actor_username', sa.String(length=64), nullable=True),
    sa.Column('actor_role', sa.String(length=32), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('resource_type', sa.String(length=64), nullable=True),
    sa.Column('resource_id', sa.String(length=64), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('details', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    _ci('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'], unique=False)
    _ci('ix_audit_logs_request_id', 'audit_logs', ['request_id'], unique=False)
    _ci('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'], unique=False)
    _ct('batch_jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=True),
    sa.Column('total_records', sa.Integer(), nullable=True),
    sa.Column('processed_records', sa.Integer(), nullable=True),
    sa.Column('successful_records', sa.Integer(), nullable=True),
    sa.Column('failed_records', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_batch_jobs_status', 'batch_jobs', ['status'], unique=False)
    _ct('captcha_intelligence',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('scan_id', sa.String(length=36), nullable=True),
    sa.Column('page_url', sa.String(length=1024), nullable=True),
    sa.Column('classification', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('challenge_type', sa.String(length=64), nullable=True),
    sa.Column('is_active_challenge', sa.Boolean(), nullable=True),
    sa.Column('detection_confidence', sa.Float(), nullable=True),
    sa.Column('detection_evidence', sa.Text(), nullable=True),
    sa.Column('handling_strategy', sa.String(length=64), nullable=False),
    sa.Column('human_review_required', sa.Boolean(), nullable=True),
    sa.Column('processing_status', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_captcha_intelligence_classification', 'captcha_intelligence', ['classification'], unique=False)
    _ci('ix_captcha_intelligence_scan_id', 'captcha_intelligence', ['scan_id'], unique=False)
    _ct('human_reviews',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('scan_id', sa.String(length=36), nullable=True),
    sa.Column('page_url', sa.String(length=1024), nullable=False),
    sa.Column('captcha_provider', sa.String(length=128), nullable=False),
    sa.Column('challenge_type', sa.String(length=64), nullable=True),
    sa.Column('reason_for_review', sa.Text(), nullable=False),
    sa.Column('review_status', sa.String(length=32), nullable=True),
    sa.Column('operator_notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_human_reviews_review_status', 'human_reviews', ['review_status'], unique=False)
    _ci('ix_human_reviews_scan_id', 'human_reviews', ['scan_id'], unique=False)
    _ct('ocr_evaluations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('ground_truth', sa.String(length=128), nullable=False),
    sa.Column('predicted_text', sa.String(length=128), nullable=False),
    sa.Column('exact_match', sa.Boolean(), nullable=True),
    sa.Column('character_accuracy', sa.Float(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('ocr_engine', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _ct('url_scans',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('submitted_url', sa.String(length=1024), nullable=False),
    sa.Column('domain', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=True),
    sa.Column('pages_crawled', sa.Integer(), nullable=True),
    sa.Column('contact_pages_found', sa.Integer(), nullable=True),
    sa.Column('captcha_detected', sa.Boolean(), nullable=True),
    sa.Column('captcha_providers', sa.String(length=255), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('crawl_duration_ms', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_url_scans_domain', 'url_scans', ['domain'], unique=False)
    _ci('ix_url_scans_status', 'url_scans', ['status'], unique=False)
    _ct('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_users_email', 'users', ['email'], unique=True)
    _ci('ix_users_username', 'users', ['username'], unique=True)
    _ct('discovered_pages',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('scan_id', sa.String(length=36), nullable=False),
    sa.Column('url', sa.String(length=1024), nullable=False),
    sa.Column('depth', sa.Integer(), nullable=True),
    sa.Column('page_title', sa.String(length=512), nullable=True),
    sa.Column('canonical_url', sa.String(length=1024), nullable=True),
    sa.Column('classification', sa.String(length=32), nullable=True),
    sa.Column('confidence_score', sa.Float(), nullable=True),
    sa.Column('evidence', sa.Text(), nullable=True),
    sa.Column('contact_form_found', sa.Boolean(), nullable=True),
    sa.Column('forms_count', sa.Integer(), nullable=True),
    sa.Column('has_inputs', sa.Boolean(), nullable=True),
    sa.Column('has_textarea', sa.Boolean(), nullable=True),
    sa.Column('captcha_detected', sa.Boolean(), nullable=True),
    sa.Column('captcha_provider', sa.String(length=128), nullable=True),
    sa.Column('is_active_challenge', sa.Boolean(), nullable=True),
    sa.Column('human_review_required', sa.Boolean(), nullable=True),
    sa.Column('detection_method', sa.String(length=128), nullable=True),
    sa.Column('screenshot_path', sa.String(length=512), nullable=True),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('crawl_duration_ms', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['scan_id'], ['url_scans.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_discovered_pages_classification', 'discovered_pages', ['classification'], unique=False)
    _ci('ix_discovered_pages_scan_id', 'discovered_pages', ['scan_id'], unique=False)
    _ct('website_inspections',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('batch_id', sa.String(length=36), nullable=False),
    sa.Column('company_name', sa.String(length=255), nullable=False),
    sa.Column('website_url', sa.String(length=1024), nullable=False),
    sa.Column('scan_status', sa.String(length=64), nullable=True),
    sa.Column('page_title', sa.String(length=512), nullable=True),
    sa.Column('contact_page_url', sa.String(length=1024), nullable=True),
    sa.Column('contact_form_found', sa.Boolean(), nullable=True),
    sa.Column('captcha_detected', sa.Boolean(), nullable=True),
    sa.Column('captcha_provider', sa.String(length=128), nullable=True),
    sa.Column('detection_method', sa.String(length=128), nullable=True),
    sa.Column('is_active_challenge', sa.Boolean(), nullable=True),
    sa.Column('human_review_required', sa.Boolean(), nullable=True),
    sa.Column('error_details', sa.Text(), nullable=True),
    sa.Column('inspection_duration_ms', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['batch_id'], ['batch_jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ci('ix_website_inspections_batch_id', 'website_inspections', ['batch_id'], unique=False)
    _ci('ix_website_inspections_scan_status', 'website_inspections', ['scan_status'], unique=False)


def downgrade() -> None:
    if os.environ.get("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Downgrading the baseline revision drops ALL application tables (users, audit log, "
            "scans, reviews...). Back up the database and set ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1 "
            "if you really intend this."
        )
    existing = _existing()
    for table in ['website_inspections', 'discovered_pages', 'users', 'url_scans', 'ocr_evaluations', 'human_reviews', 'captcha_intelligence', 'batch_jobs', 'audit_logs']:
        if table in existing:
            op.drop_table(table)
