import logging
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.models import User, generate_uuid
from app.routes.auth import router as auth_router
from app.routes.websites import router as websites_router
from app.routes.captcha import router as captcha_router
from app.routes.evidence import router as evidence_router
from app.routes.stats import router as stats_router
from app.services.audit import sanitize_request_id
from app.services.auth_service import require_operator
from app.services.browser_scanner import close_shared_browser
from app.services.input_limits import BodySizeLimitMiddleware
from app.services.job_manager import job_manager

# On Windows, ensure ProactorEventLoop is configured for child process transports
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Validate production configuration constraints
    settings.validate_production_config()
    if not settings.AUDIT_HMAC_KEY:
        logging.getLogger(__name__).warning(
            "AUDIT_HMAC_KEY is not set: the audit chain key is derived from JWT_SECRET_KEY. "
            "Set an independent AUDIT_HMAC_KEY (python -m app.cli generate-audit-key)."
        )
    # Initialize Database
    init_db()
    yield
    # Shutdown: stop background jobs, then safely terminate shared Playwright browser
    await job_manager.shutdown()
    await close_shared_browser()


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Enterprise-grade CAPTCHA inspection, website verification, SSRF-safe scanning, "
        "synthetic OCR benchmarking, and CSV compliance reporting tool."
    ),
    version="2.1.0",
    lifespan=lifespan,
)

@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """Database failures never leak SQL, paths or stack traces to the client."""
    logging.getLogger(__name__).error("Database error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable. Please retry."},
                        headers={"Retry-After": "5"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Last-resort handler: generic message, details only in the server log."""
    logging.getLogger(__name__).exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# Request body size limits (JSON and multipart, including chunked uploads)
app.add_middleware(BodySizeLimitMiddleware)


# Correlation ID + baseline security headers
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    # Client-supplied IDs are accepted only if short and boring (log-injection defence)
    request_id = sanitize_request_id(request.headers.get("X-Request-ID")) or generate_uuid()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# Strict CORS configuration restricting origins and methods
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept", "X-Setup-Token"],
)

# Include Routers
app.include_router(auth_router)
app.include_router(websites_router)
app.include_router(captcha_router)
app.include_router(stats_router)
app.include_router(evidence_router)  # authenticated; replaces the former public /evidence mount


@app.get("/")
async def home():
    return {
        "app": settings.APP_NAME,
        "version": "2.1.0",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Public liveness probe: deliberately reveals nothing about configuration."""
    return {"status": "healthy"}


@app.get("/api/health/details")
async def health_details(current_user: User = Depends(require_operator)):
    """Authenticated diagnostics (configuration-dependent details live here, not on /health)."""
    tesseract_exists = os.path.exists(settings.TESSERACT_CMD)
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": "2.1.0",
        "app_env": settings.APP_ENV,
        "database": "sqlite_connected",
        "database_connected": True,
        "ocr_engine": "tesseract_ready" if tesseract_exists else "tesseract_missing",
        "tesseract_installed": tesseract_exists,
        "live_scan_enabled": settings.ENABLE_LIVE_SCAN,
        "allowed_domains": settings.ALLOWED_DOMAINS,
        "active_background_jobs": job_manager.active(),
    }
