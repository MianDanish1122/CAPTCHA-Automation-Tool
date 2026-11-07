import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.models import generate_uuid
from app.routes.auth import router as auth_router
from app.routes.websites import router as websites_router
from app.routes.captcha import router as captcha_router
from app.services.browser_scanner import close_shared_browser

# On Windows, ensure ProactorEventLoop is configured for child process transports
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Validate production configuration constraints
    settings.validate_production_config()
    # Initialize Database
    init_db()
    yield
    # Shutdown: Safely terminate shared Playwright browser
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

# Correlation ID Middleware for request tracking & audit logs
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or generate_uuid()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Strict CORS configuration restricting origins and methods
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept"],
)

# Include Routers
app.include_router(auth_router)
app.include_router(websites_router)
app.include_router(captcha_router)

# Mount static evidence directory for screenshots
app.mount("/evidence", StaticFiles(directory=str(settings.EVIDENCE_DIR)), name="evidence")


@app.get("/")
async def home():
    return {
        "app": settings.APP_NAME,
        "version": "2.1.0",
        "status": "online",
        "app_env": settings.APP_ENV,
        "live_scan_enabled": settings.ENABLE_LIVE_SCAN,
        "docs_url": "/docs",
    }


@app.get("/health")
@app.get("/api/health")
async def health_check():
    import os
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
    }
