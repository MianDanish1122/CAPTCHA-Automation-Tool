from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole, AuditLog
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin,
    log_audit_event,
)
from app.services.rate_limiter import rate_limit
from app.services.client_ip import get_client_ip
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, description="Username")
    password: str = Field(min_length=6, max_length=128, description="Password")


class SetupAdminRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


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
    Rate-limited to prevent brute-force credential stuffing.
    """
    client_ip = get_client_ip(req)
    request_id = req.headers.get("X-Request-ID")

    user = db.query(User).filter(User.username == request_data.username).first()

    if not user or not verify_password(request_data.password, user.hashed_password):
        log_audit_event(
            db=db,
            action="auth.login_failed",
            actor_username=request_data.username,
            ip_address=client_ip,
            request_id=request_id,
            details={"reason": "Invalid credentials", "attempted_username": request_data.username}
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
        role=user.role
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
    """Log out authenticated user session and record audit trail."""
    client_ip = get_client_ip(req)
    log_audit_event(
        db=db,
        action="auth.logout",
        actor=current_user,
        ip_address=client_ip,
        request_id=req.headers.get("X-Request-ID")
    )
    return {"message": "Logged out successfully."}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return currently authenticated user profile and assigned role."""
    return {
        "success": True,
        "user": current_user.to_dict()
    }


@router.post("/setup-initial-admin")
async def setup_initial_admin(
    setup: SetupAdminRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Initial bootstrap endpoint: allows creating the primary administrator
    ONLY when the database contains zero user accounts.
    """
    existing_users_count = db.query(User).count()
    if existing_users_count > 0:
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
        ip_address=get_client_ip(req),
        details={"username": admin_user.username, "email": admin_user.email}
    )

    return {
        "success": True,
        "message": "Initial administrator account created successfully.",
        "user": admin_user.to_dict()
    }


@router.post("/users", dependencies=[Depends(require_admin)])
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
        details={"new_username": new_user.username, "assigned_role": new_user.role}
    )

    return {
        "success": True,
        "message": f"User '{new_user.username}' created successfully.",
        "user": new_user.to_dict()
    }


@router.get("/audit-logs", dependencies=[Depends(require_admin)])
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Administrator-only endpoint to inspect security audit trail."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)

    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [log.to_dict() for log in logs]
    }
