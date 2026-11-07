import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole, RevokedToken, generate_uuid, utc_now
from app.services.audit import log_audit_event  # noqa: F401  (re-exported for routes)

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(plain_password: str) -> str:
    """Securely hash a password using bcrypt with random salt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception as e:
        logger.error(f"Error during password verification: {e}")
        return False


# Valid bcrypt hash of a random value: lets login do equal work for unknown usernames
# (prevents username enumeration through response timing).
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalisation-placeholder", bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password_or_dummy(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Constant-work password check; `hashed_password=None` burns the same time as a real check."""
    if hashed_password is None:
        verify_password(plain_password, _DUMMY_HASH)
        return False
    return verify_password(plain_password, hashed_password)


def create_access_token(
    user_id: str,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    token_version: int = 0,
) -> str:
    """Create a signed JWT access token with role and expiration."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": generate_uuid(),
        "ver": int(token_version or 0),
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],  # fixed allow-list: "alg":"none" / algorithm confusion rejected
            options={"require": ["exp", "iat", "sub", "jti"]},  # tokens without an expiry are never accepted
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or corrupted authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def revoke_token(db: Session, payload: dict, reason: str = "logout") -> None:
    """Add a token's jti to the denylist until it would have expired anyway."""
    jti = payload.get("jti")
    if not jti:
        return
    exp = datetime.fromtimestamp(int(payload.get("exp", 0)), tz=timezone.utc).replace(tzinfo=None)
    now = utc_now().replace(tzinfo=None)
    # Opportunistic cleanup of denylist rows that can no longer matter
    db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete(synchronize_session=False)
    if not db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
        db.add(RevokedToken(jti=jti, user_id=payload.get("sub", ""), expires_at=exp, reason=reason))
    db.commit()


def revoke_all_user_sessions(db: Session, user: User) -> int:
    """Invalidate every token ever issued to `user` (bumps token_version). Returns the new version."""
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return user.token_version


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Dependency to retrieve and validate the authenticated user from JWT."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access this resource.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Session invalidation: individually revoked token, or token issued before a global revoke.
    jti = payload.get("jti")
    if jti and db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    ver_claim = payload.get("ver")
    if ver_claim is None:
        # Issued before Phase 6B (no version claim): cannot be bulk-invalidated, so by default
        # they are rejected once (controlled migration -> one re-login after the upgrade).
        if settings.JWT_REQUIRE_VER_CLAIM:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session predates a security upgrade. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        ver_claim = 0
    if int(ver_claim) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been invalidated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.token_payload = payload
    return user


def require_role(allowed_roles: list[str]):
    """Factory dependency to enforce role-based authorization."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {', '.join(allowed_roles)} (current: {current_user.role})."
            )
        return current_user
    return role_checker


# Convenient role dependencies
require_admin = require_role([UserRole.ADMIN])
require_operator = require_role([UserRole.ADMIN, UserRole.OPERATOR])
