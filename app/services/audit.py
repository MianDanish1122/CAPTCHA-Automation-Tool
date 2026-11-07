"""
Audit trail: redaction, tamper-evident hash chain and verification.

Tamper evidence
---------------
Every entry stores `seq` (strictly increasing), `prev_hash` and
`entry_hash = HMAC-SHA256(key, prev_hash | canonical_json(entry))`.
Editing, deleting, inserting or re-ordering any entry breaks the chain from that point and is
reported by `verify_audit_chain()`. SQLite triggers (see database.py) additionally make
UPDATE/DELETE on `audit_logs` fail at the database layer. Someone with full DB *and* key access
could rebuild a chain, which is why the key is separate from the DB and should be exported/
anchored externally (see docs/PHASE_6B_IMPLEMENTATION.md).

Writers are serialised with a process-wide lock; running several app processes against one
database requires an external lock or a database sequence (documented limitation).
"""
import hashlib
import hmac
import json
import logging
import re
import threading
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog, User, generate_uuid, utc_now

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64
_chain_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
_SENSITIVE_KEY = re.compile(
    r"pass(word|wd|phrase)?|secret|token|authorization|api[_-]?key|cookie|credential|"
    r"session|jwt|bearer|private[_-]?key|signature",
    re.IGNORECASE,
)
_JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_MAX_STRING = 500
REDACTED = "[REDACTED]"

# Keys that are metadata about a token rather than a secret
_SAFE_KEYS = {"token_version"}


def redact_url(url: str) -> str:
    """Strip userinfo, query string and fragment from a URL (they may carry secrets)."""
    match = re.match(r"^(https?://)([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$", url, re.IGNORECASE)
    if not match:
        return url
    scheme, authority, path, query, fragment = match.groups()
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    suffix = "?[REDACTED]" if query else ""
    return f"{scheme}{authority}{path}{suffix}"


def redact_string(value: str) -> str:
    value = _JWT_PATTERN.sub(REDACTED, value)
    value = _URL_PATTERN.sub(lambda m: redact_url(m.group(0)), value)
    if len(value) > _MAX_STRING:
        value = value[:_MAX_STRING] + "…[truncated]"
    return value


def redact(value: Any, key: Optional[str] = None, _depth: int = 0) -> Any:
    """Recursively redact secrets from audit details / log payloads."""
    if _depth > 6:
        return REDACTED
    if key and key not in _SAFE_KEYS and _SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): redact(v, str(k), _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(v, key, _depth + 1) for v in list(value)[:50]]
    if isinstance(value, str):
        return redact_string(value)
    return value


def fingerprint(value: Optional[str]) -> str:
    """Stable, non-reversible identifier for a sensitive value (e.g. an attempted username)."""
    digest = hmac.new(_audit_key(), (value or "").encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:12]


def sanitize_request_id(value: Optional[str]) -> Optional[str]:
    """Request IDs come from clients: accept only a short, safe charset (log-injection defence)."""
    if value and re.fullmatch(r"[A-Za-z0-9._\-]{1,64}", value):
        return value
    return None


# ---------------------------------------------------------------------------
# Hash chain
# ---------------------------------------------------------------------------
class AuditKeyError(RuntimeError):
    pass


def _key_id(key: bytes) -> str:
    return hashlib.sha256(b"audit-key-id:" + key).hexdigest()[:12]


def _legacy_derived_key() -> bytes:
    """Phase 6B original behaviour: key derived from JWT_SECRET_KEY (only for old entries/dev)."""
    return hashlib.sha256(("audit-chain:" + settings.JWT_SECRET_KEY).encode("utf-8")).digest()


def _audit_key() -> bytes:
    """Current signing key. Never derived from the JWT secret when AUDIT_HMAC_KEY is configured."""
    if settings.AUDIT_HMAC_KEY:
        if settings.AUDIT_HMAC_KEY == settings.JWT_SECRET_KEY:
            raise AuditKeyError("AUDIT_HMAC_KEY must be independent of JWT_SECRET_KEY.")
        return settings.AUDIT_HMAC_KEY.encode("utf-8")
    return _legacy_derived_key()


def current_key_id() -> str:
    return _key_id(_audit_key())


def _key_ring() -> dict[Optional[str], bytes]:
    """key_id -> key for verification. None = entries written before key ids existed."""
    ring: dict[Optional[str], bytes] = {}
    current = _audit_key()
    ring[_key_id(current)] = current
    for old in settings.AUDIT_HMAC_KEYS_PREVIOUS:
        raw = old.encode("utf-8")
        ring[_key_id(raw)] = raw
    legacy = _legacy_derived_key()
    ring[_key_id(legacy)] = legacy
    # Entries without a key id were sealed by the legacy derived key (or the current key in dev).
    if settings.AUDIT_ALLOW_LEGACY_DERIVED_KEY:
        ring[None] = legacy
    else:
        ring[None] = current
    return ring


def audit_key_status() -> dict[str, Any]:
    """Non-secret description of the key configuration (safe to log / show to admins)."""
    return {
        "configured": bool(settings.AUDIT_HMAC_KEY),
        "independent_of_jwt_secret": bool(settings.AUDIT_HMAC_KEY) and settings.AUDIT_HMAC_KEY != settings.JWT_SECRET_KEY,
        "key_id": current_key_id(),
        "previous_keys_loaded": len(settings.AUDIT_HMAC_KEYS_PREVIOUS),
        "legacy_derived_key_accepted": settings.AUDIT_ALLOW_LEGACY_DERIVED_KEY,
    }


def _canonical(entry: AuditLog) -> str:
    ts = entry.timestamp.replace(tzinfo=None).isoformat() if entry.timestamp else None
    return json.dumps(
        {
            "seq": entry.seq,
            "id": entry.id,
            "ts": ts,
            "actor_id": entry.actor_id,
            "actor_username": entry.actor_username,
            "actor_role": entry.actor_role,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "ip": entry.ip_address,
            "request_id": entry.request_id,
            "details": entry.details,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_entry_hash(prev_hash: str, entry: AuditLog, key: Optional[bytes] = None) -> str:
    message = (prev_hash + "|" + _canonical(entry)).encode("utf-8")
    return hmac.new(key or _audit_key(), message, hashlib.sha256).hexdigest()


def log_audit_event(
    db: Session,
    action: str,
    actor: Optional[User] = None,
    actor_id: Optional[str] = None,
    actor_username: Optional[str] = None,
    actor_role: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    request_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Append a redacted, hash-chained audit entry. Never raises into the request path."""
    try:
        details_json = json.dumps(redact(details), default=str) if details else None
        with _chain_lock:
            last = (
                db.query(AuditLog)
                .filter(AuditLog.entry_hash.isnot(None))
                .order_by(AuditLog.seq.desc())
                .first()
            )
            prev_hash = last.entry_hash if last else GENESIS_HASH
            next_seq = (last.seq or 0) + 1 if last else 1

            entry = AuditLog(
                id=generate_uuid(),
                seq=next_seq,
                timestamp=utc_now().replace(tzinfo=None),
                actor_id=actor.id if actor else actor_id,
                actor_username=actor.username if actor else actor_username,
                actor_role=actor.role if actor else actor_role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                request_id=sanitize_request_id(request_id),
                details=details_json,
                prev_hash=prev_hash,
            )
            entry.key_id = current_key_id()
            entry.entry_hash = compute_entry_hash(prev_hash, entry)
            db.add(entry)
            db.commit()
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to record audit log event '%s': %s", action, type(e).__name__)
        try:
            db.rollback()
        except Exception:
            pass


def verify_audit_chain(
    db: Session,
    expected_head_seq: Optional[int] = None,
    expected_head_hash: Optional[str] = None,
) -> dict[str, Any]:
    """
    Recompute the whole chain and report the first inconsistency, if any.

    The chain alone cannot detect TRUNCATION (removal of the newest entries) or a rollback to an
    older backup, because every remaining prefix is still internally consistent. Pass the
    externally recorded head (`expected_head_seq` / `expected_head_hash`) to detect that too.
    """
    ring = _key_ring()
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entry_hash.isnot(None))
        .order_by(AuditLog.seq.asc())
        .all()
    )
    legacy = db.query(AuditLog).filter(AuditLog.entry_hash.is_(None)).count()

    expected_prev = GENESIS_HASH
    expected_seq = 1
    seen_keyed = False
    for row in rows:
        problem = None
        if row.key_id is not None:
            seen_keyed = True
        if row.seq != expected_seq:
            problem = f"sequence gap or reorder: expected {expected_seq}, found {row.seq}"
        elif row.prev_hash != expected_prev:
            problem = "previous-hash link does not match the preceding entry"
        elif row.key_id is None and seen_keyed:
            problem = "unkeyed (legacy) entry appears after keyed entries"
        elif row.key_id not in ring and row.key_id is not None:
            problem = "entry sealed with an unknown key (rotated without AUDIT_HMAC_KEYS_PREVIOUS?)"
        elif not hmac.compare_digest(
            row.entry_hash or "", compute_entry_hash(row.prev_hash, row, ring[row.key_id])
        ):
            problem = "entry content does not match its recorded hash"
        if problem:
            return {
                "valid": False,
                "checked_entries": expected_seq - 1,
                "legacy_unchained_entries": legacy,
                "first_invalid_seq": row.seq,
                "first_invalid_id": row.id,
                "problem": problem,
            }
        expected_prev = row.entry_hash
        expected_seq += 1

    head_seq = expected_seq - 1
    report: dict[str, Any] = {
        "valid": True,
        "checked_entries": len(rows),
        "legacy_unchained_entries": legacy,
        "head_hash": expected_prev,
        "head_seq": head_seq,
    }
    if expected_head_seq is not None or expected_head_hash is not None:
        problems = []
        if expected_head_seq is not None and head_seq < expected_head_seq:
            problems.append(
                f"chain ends at seq {head_seq} but the recorded head is seq {expected_head_seq}: "
                "entries were removed or an older backup was restored"
            )
        elif expected_head_seq is not None and head_seq >= expected_head_seq and expected_head_hash:
            anchor = next((r for r in rows if r.seq == expected_head_seq), None)
            if anchor is None or anchor.entry_hash != expected_head_hash:
                problems.append("entry at the recorded head sequence does not match the recorded head hash")
        elif expected_head_hash and expected_head_seq is None and expected_head_hash != expected_prev:
            problems.append("current head hash differs from the recorded head hash")
        if problems:
            report["valid"] = False
            report["problem"] = "; ".join(problems)
            report["head_check"] = "failed"
        else:
            report["head_check"] = "ok"
    return report
