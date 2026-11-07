"""
Safe loader for `fixture://` references.

Fixtures are local, authored HTML pages used for demos and tests. A fixture reference
is only ever a bare file NAME (e.g. ``google_recaptcha.html``) that must resolve to a
regular file located *directly* inside the approved fixtures directory.

Everything else (path separators, drive letters, ``..``, encoded traversal, NUL bytes,
symlinks that escape the directory, odd extensions) is rejected.
"""
import re
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from app.config import settings

FIXTURE_SCHEME = "fixture://"
FIXTURES_DIR: Path = settings.BASE_DIR / "tests" / "fixtures"

# Strict allow-list: letters, digits, underscore, hyphen + ".html"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,100}\.html$")

MAX_FIXTURE_BYTES = 512 * 1024


class FixtureError(ValueError):
    """Raised when a fixture reference is invalid, unsafe, or disabled."""


def is_fixture_reference(url: str) -> bool:
    return isinstance(url, str) and url.strip().lower().startswith(FIXTURE_SCHEME)


def extract_fixture_name(url: str) -> str:
    """Return the raw (undecoded) text after ``fixture://``."""
    return url.strip()[len(FIXTURE_SCHEME):]


def validate_fixture_name(raw_name: str) -> str:
    """
    Validate a fixture name and return the canonical, safe file name.
    Percent-encoding is fully decoded first (including double-encoding) so that
    ``%2e%2e%2f`` and ``%252e%252e`` style tricks are caught.
    """
    if not isinstance(raw_name, str) or not raw_name:
        raise FixtureError("Fixture name is empty.")

    decoded = raw_name
    for _ in range(5):  # decode nested encodings until stable
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    else:
        raise FixtureError("Fixture name has suspicious nested encoding.")

    if decoded != raw_name:
        # Legitimate fixture names never need percent-encoding.
        raise FixtureError("Percent-encoded fixture names are not permitted.")

    if "\x00" in decoded or any(ord(c) < 32 for c in decoded):
        raise FixtureError("Fixture name contains control characters.")

    if not _SAFE_NAME.fullmatch(decoded):
        raise FixtureError(
            "Fixture name must be a bare file name matching [A-Za-z0-9_-]+.html "
            "(no directories, drive letters, or traversal sequences)."
        )
    return decoded


def resolve_fixture_path(raw_name: str) -> Path:
    """Validate and resolve a fixture name to a file inside FIXTURES_DIR."""
    name = validate_fixture_name(raw_name)
    base = FIXTURES_DIR.resolve()
    candidate = (base / name).resolve()

    # Containment check on the fully resolved path (defeats symlink escapes).
    if candidate.parent != base:
        raise FixtureError("Fixture path escapes the approved fixtures directory.")
    if not candidate.is_file():
        raise FixtureError(f"Fixture file not found: {name}")
    return candidate


def load_fixture_html(url: str, fixtures_enabled: Optional[bool] = None) -> str:
    """
    Load fixture HTML for a ``fixture://name.html`` reference.
    Fixtures are disabled outside development/test environments.
    """
    enabled = settings.fixtures_enabled if fixtures_enabled is None else fixtures_enabled
    if not enabled:
        raise FixtureError(
            "Fixture access is disabled in this environment "
            f"(APP_ENV={settings.APP_ENV})."
        )
    if not is_fixture_reference(url):
        raise FixtureError("Not a fixture reference.")

    path = resolve_fixture_path(extract_fixture_name(url))
    if path.stat().st_size > MAX_FIXTURE_BYTES:
        raise FixtureError("Fixture file exceeds the maximum permitted size.")
    return path.read_text(encoding="utf-8")
