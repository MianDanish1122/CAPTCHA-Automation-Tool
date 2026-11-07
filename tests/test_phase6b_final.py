"""
Phase 6B final-review tests: audit key independence/rotation (A), Alembic migrations on Phase 5
databases (B), JWT session migration (C), audit backup/restore/head verification (E).
"""
import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app import cli
from app.config import settings
from app.database import SessionLocal, _AUDIT_TRIGGERS
from app.main import app
from app.models import AuditLog, Base, RevokedToken, User, UserRole
from app.services import audit
from app.services.audit import (
    AuditKeyError,
    audit_key_status,
    log_audit_event,
    verify_audit_chain,
)
from app.services.auth_service import create_access_token

ROOT = Path(__file__).resolve().parent.parent
KEY_A = "a" * 48
KEY_B = "b" * 48


def _client(token=None):
    c = TestClient(app)
    c._unauthenticated = token is None
    if token:
        c.headers["Authorization"] = f"Bearer {token}"
    return c


def _chain_db(tmp_path, name="chain.db"):
    engine = create_engine(f"sqlite:///{(tmp_path / name).as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for trig in _AUDIT_TRIGGERS:
            conn.execute(text(trig))
    return engine, sessionmaker(bind=engine, autoflush=False)


def _events(maker, n, start=0):
    db = maker()
    try:
        for i in range(start, start + n):
            log_audit_event(db, action=f"e.{i}", actor_username="tester", details={"i": i})
    finally:
        db.close()


# =============================================================== A. audit key
def test_environment_configures_explicit_independent_audit_key():
    status = audit_key_status()
    assert status["configured"] is True, "AUDIT_HMAC_KEY must be set explicitly in .env"
    assert status["independent_of_jwt_secret"] is True
    assert len(settings.AUDIT_HMAC_KEY) >= 32
    assert settings.AUDIT_HMAC_KEY != settings.JWT_SECRET_KEY


def test_audit_key_status_never_contains_secret_material():
    blob = json.dumps(audit_key_status())
    assert settings.AUDIT_HMAC_KEY not in blob and settings.JWT_SECRET_KEY not in blob


def test_audit_key_equal_to_jwt_secret_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", settings.JWT_SECRET_KEY)
    with pytest.raises(AuditKeyError):
        audit.current_key_id()


def test_production_requires_independent_strong_audit_key(monkeypatch):
    base = dict(APP_ENV="production", DEBUG=False, ALLOW_DEV_LOOPBACK=False, JWT_SECRET_KEY="j" * 40)
    for k, v in base.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", "")
    with pytest.raises(ValueError, match="AUDIT_HMAC_KEY"):
        settings.validate_production_config()
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", "short")
    with pytest.raises(ValueError, match="AUDIT_HMAC_KEY"):
        settings.validate_production_config()
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", "j" * 40)
    with pytest.raises(ValueError, match="different"):
        settings.validate_production_config()
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_A)
    settings.validate_production_config()  # passes


def test_entries_record_key_id_and_secret_never_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_A)
    _, maker = _chain_db(tmp_path)
    with caplog.at_level(logging.DEBUG):
        _events(maker, 3)
    db = maker()
    try:
        ids = {r.key_id for r in db.query(AuditLog)}
        assert ids == {audit.current_key_id()}
        assert verify_audit_chain(db)["valid"] is True
    finally:
        db.close()
    assert KEY_A not in caplog.text and settings.JWT_SECRET_KEY not in caplog.text


def test_key_rotation_keeps_old_entries_verifiable(tmp_path, monkeypatch):
    _, maker = _chain_db(tmp_path)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_A)
    _events(maker, 3)
    # rotate: new key, old key moved to the previous list
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_B)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEYS_PREVIOUS", [KEY_A])
    _events(maker, 3, start=3)
    db = maker()
    try:
        report = verify_audit_chain(db)
        assert report["valid"] is True and report["checked_entries"] == 6
        assert len({r.key_id for r in db.query(AuditLog)}) == 2
    finally:
        db.close()
    # forgetting the old key makes the old segment unverifiable (and says why)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEYS_PREVIOUS", [])
    db = maker()
    try:
        report = verify_audit_chain(db)
        assert report["valid"] is False and "unknown key" in report["problem"]
    finally:
        db.close()


def test_wrong_current_key_fails_verification(tmp_path, monkeypatch):
    _, maker = _chain_db(tmp_path)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_A)
    _events(maker, 2)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_B)
    db = maker()
    try:
        assert verify_audit_chain(db)["valid"] is False
    finally:
        db.close()


def test_legacy_unkeyed_entries_must_precede_keyed_ones(tmp_path, monkeypatch):
    engine, maker = _chain_db(tmp_path)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_A)
    _events(maker, 3)
    with sqlite3.connect(engine.url.database) as raw:
        raw.execute("DROP TRIGGER audit_logs_no_update")
        raw.execute("UPDATE audit_logs SET key_id=NULL WHERE seq=3")  # downgrade attack on a keyed entry
    db = maker()
    try:
        assert verify_audit_chain(db)["valid"] is False
    finally:
        db.close()


# =============================================================== C. JWT migration
def _claims(user_id="test-operator-id", **over):
    now = int(time.time())
    payload = {"sub": user_id, "username": "test_operator", "role": "operator",
               "iat": now, "exp": now + 600, "jti": str(uuid.uuid4()), "ver": 0}
    payload.update(over)
    return {k: v for k, v in payload.items() if v is not None}


def _enc(payload, key=None, alg=None):
    return jwt.encode(payload, key or settings.JWT_SECRET_KEY, algorithm=alg or settings.JWT_ALGORITHM)


def _me(token):
    return _client(token).get("/api/auth/me").status_code


def test_new_tokens_are_accepted():
    assert _me(create_access_token("test-operator-id", "test_operator", UserRole.OPERATOR)) == 200


def test_pre_6b_token_without_version_claim_is_rejected_by_default(monkeypatch):
    old = _enc(_claims(ver=None))
    monkeypatch.setattr(settings, "JWT_REQUIRE_VER_CLAIM", True)
    res = _client(old).get("/api/auth/me")
    assert res.status_code == 401 and "predates" in res.json()["detail"]


def test_pre_6b_token_accepted_only_during_explicit_grace_window(monkeypatch):
    old = _enc(_claims(ver=None))
    monkeypatch.setattr(settings, "JWT_REQUIRE_VER_CLAIM", False)
    assert _me(old) == 200


def test_expired_token_rejected():
    assert _me(_enc(_claims(exp=int(time.time()) - 5, iat=int(time.time()) - 600))) == 401


def test_token_without_expiry_rejected():
    assert _me(_enc(_claims(exp=None))) == 401


def test_token_without_jti_rejected():
    assert _me(_enc(_claims(jti=None))) == 401


def test_alg_none_and_wrong_signature_rejected():
    forged_none = jwt.encode(_claims(), key="", algorithm="none")
    assert _me(forged_none) == 401
    assert _me(_enc(_claims(), key="not-the-real-secret-" * 3)) == 401


def test_revoked_token_rejected_and_other_tokens_unaffected():
    revoked = _claims()
    other = _claims()
    db = SessionLocal()
    try:
        db.add(RevokedToken(jti=revoked["jti"], user_id="test-operator-id",
                            expires_at=datetime.utcnow() + timedelta(minutes=10), reason="test"))
        db.commit()
    finally:
        db.close()
    assert _me(_enc(revoked)) == 401
    assert _me(_enc(other)) == 200


def test_wrong_token_version_rejected():
    assert _me(_enc(_claims(ver=99))) == 401


def test_cli_invalidate_sessions_kills_existing_tokens():
    admin = _client(create_access_token("test-admin-id", "test_admin", UserRole.ADMIN))
    name = "t6f_" + uuid.uuid4().hex[:8]
    pw = "Str0ng-Test-Passw0rd!"
    r = admin.post("/api/auth/users", json={"username": name, "email": f"{name}@test.internal", "password": pw})
    assert r.status_code == 200
    login = _client().post("/api/auth/login", json={"username": name, "password": pw})
    tok = login.json()["access_token"]
    assert _me(tok) == 200
    assert cli.invalidate_sessions_command(username=name) is True
    assert _me(tok) == 401
    assert _client().post("/api/auth/login", json={"username": name, "password": pw}).status_code == 200


# =============================================================== E. backup / restore / head
@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    engine, maker = _chain_db(tmp_path, "live.db")
    live = Path(engine.url.database)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    monkeypatch.setattr(cli, "_db_file", lambda: live)
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_A)
    (tmp_path / "data").mkdir(exist_ok=True)
    return engine, maker, live, tmp_path


def _latest_backup(tmp_path):
    return sorted((tmp_path / "data" / "backups").glob("captcha_tool_backup_*.db"))[-1]


def test_backup_is_consistent_and_records_audit_head(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 4)
    assert cli.backup_db_command() is True
    backup = _latest_backup(tmp)
    side = json.loads(backup.with_suffix(".head.json").read_text())
    assert side["audit_chain_valid"] is True and side["audit_head_seq"] == 4 and len(side["audit_head_hash"]) == 64
    assert cli._chain_report_for_file(backup)["valid"] is True


def test_restore_requires_confirmation_and_preserves_current_db(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 3)
    cli.backup_db_command()
    backup = _latest_backup(tmp)
    _events(maker, 2, start=3)
    assert cli.restore_db_command(str(backup)) is False  # no --yes: refuses
    assert cli._chain_report_for_file(live)["head_seq"] == 5
    engine.dispose()
    assert cli.restore_db_command(str(backup), assume_yes=True) is True
    assert cli._chain_report_for_file(live)["head_seq"] == 3
    assert list((tmp / "data" / "backups").glob("pre_restore_*.db")), "previous DB must be preserved"


def test_restore_refuses_tampered_backup(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 4)
    cli.backup_db_command()
    backup = _latest_backup(tmp)
    with sqlite3.connect(backup) as raw:
        raw.execute("DROP TRIGGER audit_logs_no_update")
        raw.execute("UPDATE audit_logs SET action='forged' WHERE seq=2")
    engine.dispose()
    assert cli.restore_db_command(str(backup), assume_yes=True) is False
    assert cli._chain_report_for_file(live)["valid"] is True  # live DB untouched


def test_restore_refuses_corrupt_file(cli_env):
    engine, maker, live, tmp = cli_env
    bad = tmp / "garbage.db"
    bad.write_bytes(b"this is not a sqlite database" * 50)
    with pytest.raises(Exception):
        cli.restore_db_command(str(bad), assume_yes=True)
    assert cli._chain_report_for_file(live)["valid"] is True


def test_rollback_to_old_backup_detected_with_external_head(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 3)
    cli.backup_db_command()
    old_backup = _latest_backup(tmp)
    _events(maker, 3, start=3)
    head = cli._chain_report_for_file(live)
    assert head["head_seq"] == 6
    # Without the external head the old backup looks perfectly valid (documented limitation)...
    assert cli._chain_report_for_file(old_backup)["valid"] is True
    # ...with the externally recorded head the rollback is caught, and restore refuses.
    report = cli._chain_report_for_file(old_backup, head["head_seq"], head["head_hash"])
    assert report["valid"] is False and "older backup" in report["problem"]
    engine.dispose()
    assert cli.restore_db_command(str(old_backup), head["head_seq"], head["head_hash"], assume_yes=True) is False


def test_truncation_detected_only_with_external_head(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 5)
    head = cli._chain_report_for_file(live)
    with sqlite3.connect(live) as raw:
        raw.execute("DROP TRIGGER audit_logs_no_delete")
        raw.execute("DELETE FROM audit_logs WHERE seq>3")  # attacker removes the newest entries
    assert cli._chain_report_for_file(live)["valid"] is True  # chain alone cannot see this
    caught = cli._chain_report_for_file(live, head["head_seq"], head["head_hash"])
    assert caught["valid"] is False


def test_head_hash_mismatch_at_same_sequence_detected(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 3)
    head = cli._chain_report_for_file(live)
    bad = cli._chain_report_for_file(live, head["head_seq"], "0" * 64)
    assert bad["valid"] is False
    assert cli._chain_report_for_file(live, head["head_seq"], head["head_hash"])["valid"] is True


def test_modified_deleted_and_forged_records_detected(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 6)
    with sqlite3.connect(live) as raw:
        raw.execute("DROP TRIGGER audit_logs_no_update")
        raw.execute("DROP TRIGGER audit_logs_no_delete")
        raw.execute("UPDATE audit_logs SET resource_id='x' WHERE seq=2")
    assert cli._chain_report_for_file(live)["first_invalid_seq"] == 2
    with sqlite3.connect(live) as raw:
        raw.execute("UPDATE audit_logs SET resource_id=NULL WHERE seq=2")  # undo -> valid again
    assert cli._chain_report_for_file(live)["valid"] is True
    with sqlite3.connect(live) as raw:
        raw.execute("DELETE FROM audit_logs WHERE seq=4")
    assert "gap" in cli._chain_report_for_file(live)["problem"]


def test_audit_verify_cli_exit_semantics(cli_env):
    engine, maker, live, tmp = cli_env
    _events(maker, 2)
    assert cli.audit_verify_command() is True
    with sqlite3.connect(live) as raw:
        raw.execute("DROP TRIGGER audit_logs_no_update")
        raw.execute("UPDATE audit_logs SET action='zzz' WHERE seq=1")
    assert cli.audit_verify_command() is False


# =============================================================== B. Alembic migrations
HEAD = "6b01phase6security"
BASELINE = "5eb94b849402"
SCHEMA_SQL = (ROOT / "tests" / "fixtures" / "phase5_schema.sql").read_text(encoding="utf-8")


def _cfg(db_path: Path) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _phase5_db(path: Path, stamp: bool):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_SQL)
    now = "2026-01-01 10:00:00.000000"
    con.executemany(
        "INSERT INTO users (id, username, email, hashed_password, role, is_active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [("u1", "alice", "a@x.test", "$2b$12$hashhashhash", "admin", 1, now, now),
         ("u2", "bob", "b@x.test", "$2b$12$hashhashhash2", "operator", 1, now, now)])
    con.executemany(
        "INSERT INTO audit_logs (id, timestamp, actor_id, actor_username, actor_role, action, details) VALUES (?,?,?,?,?,?,?)",
        [(f"a{i}", now, "u1", "alice", "admin", f"legacy.event_{i}", '{"k": %d}' % i) for i in range(3)])
    con.execute("INSERT INTO human_reviews (id, page_url, captcha_provider, reason_for_review, review_status, created_at) VALUES ('r1','https://example.com/c','hcaptcha','why','pending',?)", (now,))
    con.execute("INSERT INTO url_scans (id, submitted_url, domain, status, created_at) VALUES ('s1','https://example.com','example.com','completed',?)", (now,))
    if stamp:
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (BASELINE,))
    con.commit()
    con.close()


def _dump(path: Path, tables):
    con = sqlite3.connect(path)
    try:
        out = {}
        for t in tables:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            out[t] = (cols, sorted(con.execute(f"SELECT * FROM {t}").fetchall(), key=str))
        return out
    finally:
        con.close()


def _version(path: Path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()


def _preserved(before, after):
    """Every pre-existing column value survived; new columns may exist."""
    for table, (cols, rows) in before.items():
        acols, arows = after[table]
        idx = [acols.index(c) for c in cols]
        projected = sorted((tuple(r[i] for i in idx) for r in arows), key=str)
        assert projected == rows, f"data changed in {table}"


@pytest.mark.parametrize("stamped", [True, False], ids=["stamped-at-old-stub", "never-stamped"])
def test_upgrade_of_existing_phase5_database_preserves_records(tmp_path, stamped):
    db = tmp_path / "p5.db"
    _phase5_db(db, stamped)
    tables = ["users", "audit_logs", "human_reviews", "url_scans"]
    before = _dump(db, tables)

    command.upgrade(_cfg(db), "head")

    assert _version(db) == HEAD
    _preserved(before, _dump(db, tables))
    con = sqlite3.connect(db)
    try:
        assert {r[1] for r in con.execute("PRAGMA table_info(users)")} >= {"token_version"}
        assert con.execute("SELECT token_version FROM users").fetchall() == [(0,), (0,)]
        assert con.execute("SELECT decision_count FROM human_reviews").fetchall() == [(0,)]
        assert con.execute("SELECT count(*) FROM audit_logs WHERE entry_hash IS NULL").fetchone()[0] == 3
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
        assert {"revoked_tokens", "review_decisions", "audit_logs_no_update", "audit_logs_no_delete",
                "review_decisions_no_update", "review_decisions_no_delete", "ix_audit_logs_seq"} <= names
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            con.execute("UPDATE audit_logs SET action='x'")
    finally:
        con.close()


def test_migrated_database_works_with_the_application_audit_chain(tmp_path, monkeypatch):
    db = tmp_path / "p5.db"
    _phase5_db(db, True)
    command.upgrade(_cfg(db), "head")
    monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", KEY_A)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    maker = sessionmaker(bind=engine, autoflush=False)
    _events(maker, 3)
    session = maker()
    try:
        report = verify_audit_chain(session)
        assert report["valid"] is True and report["checked_entries"] == 3 and report["legacy_unchained_entries"] == 3
    finally:
        session.close()
        engine.dispose()


def test_upgrade_is_idempotent_and_safe_on_app_built_database(tmp_path):
    db = tmp_path / "app_built.db"
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    Base.metadata.create_all(engine)  # what init_db() produces
    with engine.begin() as conn:
        for trig in _AUDIT_TRIGGERS:
            conn.execute(text(trig))
    engine.dispose()
    command.upgrade(_cfg(db), "head")
    command.upgrade(_cfg(db), "head")  # second run is a no-op
    assert _version(db) == HEAD


def _schema_signature(path: Path):
    insp = inspect(create_engine(f"sqlite:///{path.as_posix()}"))
    sig = {}
    for t in sorted(insp.get_table_names()):
        if t == "alembic_version":
            continue
        cols = {c["name"]: (str(c["type"]).split("(")[0].upper(), bool(c["nullable"])) for c in insp.get_columns(t)}
        idx = {i["name"] for i in insp.get_indexes(t)}
        sig[t] = (cols, idx)
    return sig


def test_fresh_migration_matches_orm_models(tmp_path):
    """Guards against drift between the ORM models and the migration scripts."""
    migrated = tmp_path / "migrated.db"
    command.upgrade(_cfg(migrated), "head")
    built = tmp_path / "built.db"
    e = create_engine(f"sqlite:///{built.as_posix()}")
    Base.metadata.create_all(e)
    e.dispose()
    assert _schema_signature(migrated) == _schema_signature(built)


def test_downgrades_are_guarded_and_non_destructive_to_core_data(tmp_path, monkeypatch):
    db = tmp_path / "p5.db"
    _phase5_db(db, True)
    command.upgrade(_cfg(db), "head")
    tables = ["users", "audit_logs", "human_reviews", "url_scans"]
    upgraded = _dump(db, tables)

    monkeypatch.delenv("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(Exception, match="ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE"):
        command.downgrade(_cfg(db), BASELINE)
    assert _version(db) == HEAD  # untouched

    monkeypatch.setenv("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE", "1")
    command.downgrade(_cfg(db), BASELINE)
    assert _version(db) == BASELINE
    con = sqlite3.connect(db)
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
        assert "revoked_tokens" not in names and "review_decisions" not in names
        assert "audit_logs_no_update" not in names
        assert "token_version" not in {r[1] for r in con.execute("PRAGMA table_info(users)")}
        assert con.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM audit_logs").fetchone()[0] == 3
    finally:
        con.close()
    # original Phase 5 values preserved through upgrade + downgrade
    after = _dump(db, tables)
    for t in tables:
        original_cols = _dump(db, [t])[t][0]
        up_cols, up_rows = upgraded[t]
        idx = [up_cols.index(c) for c in original_cols]
        assert sorted((tuple(r[i] for i in idx) for r in up_rows), key=str) == after[t][1]
    command.upgrade(_cfg(db), "head")  # and it can be upgraded again
    assert _version(db) == HEAD


def test_baseline_downgrade_to_base_requires_explicit_flag(tmp_path, monkeypatch):
    db = tmp_path / "fresh.db"
    command.upgrade(_cfg(db), "head")
    monkeypatch.delenv("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(Exception, match="ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE"):
        command.downgrade(_cfg(db), "base")
