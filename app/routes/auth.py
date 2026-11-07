import hmac
import threading
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole, AuditLog
from app.services.auth_service import (
    hash_password,
    verify_password_or_dummy,
    create_access_token,
    get_current_user,
    require_admin,
    log_audit_event,
    revoke_token,
    revoke_all_user_sessions,
)
from app.services.audit import fingerprint, verify_audit_chain
from app.services.rate_limiter import rate_limit
from app.services.client_ip import get_client_ip
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])

_bootstrap_lock = threading.Lock()


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, description="Username")
    password: str = Field(min_length=6, max_length=128, description="Password")


class SetupAdminRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default=UserRole.OPERATOR)


@router.post(
    "/login",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_LOGIN_PER_MIN, window_seconds=60, scope="login"))]
)
async def login(
    request_data: LoginRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Authenticate user credentials and issue signed JWT access token.
    Rate-limited to prevent brute-force credential stuffing. Work done is equal for known and
    unknown usernames, and the attempted username is never written to the audit trail
    (people sometimes type a password there): only a keyed fingerprint is stored.
    """
    client_ip = get_client_ip(req)
    request_id = req.headers.get("X-Request-ID")

    user = db.query(User).filter(User.username == request_data.username).first()
    password_ok = verify_password_or_dummy(
        request_data.password, user.hashed_password if user else None
    )

    if not user or not password_ok:
        log_audit_event(
            db=db,
            action="auth.login_failed",
            actor_id=user.id if user else None,
            ip_address=client_ip,
            request_id=request_id,
            details={
                "reason": "Invalid credentials",
                "username_fingerprint": fingerprint(request_data.username),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        log_audit_event(
            db=db,
            action="auth.login_blocked",
            actor=user,
            ip_address=client_ip,
            request_id=request_id,
            details={"reason": "User account inactive"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled. Contact system administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        token_version=user.token_version or 0,
    )

    log_audit_event(
        db=db,
        action="auth.login_success",
        actor=user,
        ip_address=client_ip,
        request_id=request_id,
        details={"role": user.role}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "user": user.to_dict(),
    }


@router.post("/logout")
async def logout(
    req: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke the presented access token (server-side) and record the audit trail."""
    revoke_token(db, getattr(req.state, "token_payload", {}), reason="logout")
    log_audit_event(
        db=db,
        action="auth.logout",
        actor=current_user,
        ip_address=get_client_ip(req),
        request_id=req.headers.get("X-Request-ID")
    )
    return {"message": "Logged out successfully."}


@router.post("/logout-all")
async def logout_all(
    req: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Invalidate every session (token) the current user has ever been issued."""
    new_version = revoke_all_user_sessions(db, current_user)
    log_audit_event(
        db=db,
        action="auth.logout_all",
        actor=current_user,
        ip_address=get_client_ip(req),
        request_id=req.headers.get("X-Request-ID"),
        details={"token_version": new_version},
    )
    return {"message": "All sessions have been invalidated."}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return currently authenticated user profile and assigned role."""
    return {
        "success": True,
        "user": current_user.to_dict()
    }


@router.post(
    "/setup-initial-admin",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_SETUP_PER_MIN, window_seconds=60, scope="setup_admin"))],
)
async def setup_initial_admin(
    setup: SetupAdminRequest,
    req: Request,
    x_setup_token: Optional[str] = Header(default=None, alias="X-Setup-Token"),
    db: Session = Depends(get_db)
):
    """
    One-time bootstrap of the first administrator.

    Hardened: the endpoint does not exist (404) unless the operator has configured
    INITIAL_ADMIN_SETUP_TOKEN (>= 24 chars) and the caller presents it in `X-Setup-Token`.
    It works only while the user table is empty, the check-and-insert is serialised, and the
    attempt (success or failure) is audited. The CLI (`python -m app.cli create-admin`) is the
    preferred provisioning path and needs no network endpoint at all.
    """
    expected = settings.INITIAL_ADMIN_SETUP_TOKEN
    client_ip = get_client_ip(req)

    if not expected or len(expected) < 24:
        raise HTTPException(status_code=404, detail="Not found.")

    if not x_setup_token or not hmac.compare_digest(
        x_setup_token.encode("utf-8"), expected.encode("utf-8")
    ):
        log_audit_event(
            db=db,
            action="auth.initial_admin_setup_denied",
            ip_address=client_ip,
            request_id=req.headers.get("X-Request-ID"),
            details={"reason": "invalid setup token"},
        )
        raise HTTPException(status_code=403, detail="Invalid setup token.")

    with _bootstrap_lock:
        if db.query(User).count() > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Initial administrator setup is disabled. User accounts already exist."
            )
        admin_user = User(
            username=setup.username,
            email=setup.email,
            hashed_password=hash_password(setup.password),
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

    log_audit_event(
        db=db,
        action="auth.initial_admin_setup",
        actor=admin_user,
        ip_address=client_ip,
        request_id=req.headers.get("X-Request-ID"),
        details={"username": admin_user.username},
    )

    return {
        "success": True,
        "message": "Initial administrator account created successfully. "
                   "Remove INITIAL_ADMIN_SETUP_TOKEN from the environment now.",
        "user": admin_user.to_dict()
    }


@router.post(
    "/users",
    dependencies=[Depends(require_admin), Depends(rate_limit(max_requests=settings.RATE_LIMIT_ADMIN_PER_MIN, window_seconds=60, scope="admin_ops"))],
)
async def create_user(
    user_data: CreateUserRequest,
    req: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Administrator-only endpoint to create new system users/operators."""
    if user_data.role not in (UserRole.ADMIN, UserRole.OPERATOR):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{user_data.role}'. Permitted roles: {UserRole.ADMIN}, {UserRole.OPERATOR}"
        )

    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username is already registered.")

    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email is already registered.")

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        role=user_data.role,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_audit_event(
        db=db,
        action="admin.create_user",
        actor=current_admin,
        resource_type="user",
        resource_id=new_user.id,
        ip_address=get_client_ip(req),
        request_id=req.headers.get("X-Request-ID"),
        details={"new_username": new_user.username, "assigned_role": new_user.role}
    )

    return {
        "success": True,
        "message": f"User '{new_user.username}' created successfully.",
        "user": new_user.to_dict()
    }


@router.post(
    "/users/{user_id}/revoke-sessions",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_ADMIN_PER_MIN, window_seconds=60, scope="admin_ops"))],
)
async def admin_revoke_sessions(
    user_id: str,
    req: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Administrator-only: invalidate every outstanding token of a user (e.g. suspected leak)."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    new_version = revoke_all_user_sessions(db, target)
    log_audit_event(
        db=db, action="admin.revoke_sessions", actor=current_admin,
        resource_type="user", resource_id=target.id,
        ip_address=get_client_ip(req), request_id=req.headers.get("X-Request-ID"),
        details={"target_username": target.username, "token_version": new_version},
    )
    return {"success": True, "message": f"All sessions for '{target.username}' invalidated."}


@router.post(
    "/users/{user_id}/deactivate",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_ADMIN_PER_MIN, window_seconds=60, scope="admin_ops"))],
)
async def admin_deactivate_user(
    user_id: str,
    req: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Administrator-only: disable an account and invalidate its sessions immediately."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Administrators cannot deactivate their own account.")
    target.is_active = False
    revoke_all_user_sessions(db, target)
    log_audit_event(
        db=db, action="admin.deactivate_user", actor=current_admin,
        resource_type="user", resource_id=target.id,
        ip_address=get_client_ip(req), request_id=req.headers.get("X-Request-ID"),
        details={"target_username": target.username},
    )
    return {"success": True, "message": f"User '{target.username}' deactivated."}


@router.get("/audit-logs", dependencies=[Depends(require_admin)])
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None, max_length=64),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Administrator-only endpoint to inspect security audit trail."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)

    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc(), AuditLog.seq.desc()).offset(offset).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [log.to_dict() for log in logs]
    }


@router.get(
    "/audit-logs/verify",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, scope="audit_verify"))],
)
async def verify_audit_logs(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Administrator-only: recompute the audit hash chain and report tampering, if any."""
    return {"success": True, **verify_audit_chain(db)}
