"""
Authenticated access to scan evidence (screenshots).

Replaces the former unauthenticated `StaticFiles` mount, which exposed the whole `evidence/`
directory (including test artifacts) to anyone who could reach the server. Now:
  * a valid session with operator/admin role is required,
  * only `scans/<scan-id>/<file>.png|jpg` is servable (not the rest of `evidence/`),
  * the requested path is validated against a strict pattern AND must resolve inside the
    scans directory (defence in depth against traversal / symlinks),
  * responses are `private, no-store` and `nosniff`.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.models import User
from app.services.auth_service import require_operator

router = APIRouter(prefix="/api/evidence", tags=["Evidence"])

_ALLOWED = re.compile(r"^scans/[0-9A-Fa-f\-]{36}/[A-Za-z0-9_.\-]{1,120}\.(png|jpg|jpeg)$")
_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


@router.get("/{file_path:path}")
async def get_evidence_file(file_path: str, current_user: User = Depends(require_operator)):
    # Accept a leading "evidence/" so stored relative paths can be appended verbatim.
    if file_path.startswith("evidence/"):
        file_path = file_path[len("evidence/"):]

    if ".." in file_path or "\\" in file_path or not _ALLOWED.fullmatch(file_path):
        raise HTTPException(status_code=404, detail="Evidence not found.")

    base = settings.SCANS_EVIDENCE_DIR.resolve()
    target = (settings.EVIDENCE_DIR / file_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Evidence not found.")

    return FileResponse(
        str(target),
        media_type=_MEDIA[target.suffix.lstrip(".").lower()],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
