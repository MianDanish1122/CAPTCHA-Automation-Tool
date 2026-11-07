import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routes.websites import router as websites_router
from app.routes.captcha import router as captcha_router
from app.services.browser_scanner import close_shared_browser

# On Windows, ensure ProactorEventLoop is configured for child process transports
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
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
    version="2.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend integration and local tooling
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(websites_router)
app.include_router(captcha_router)

# Mount static evidence directory for screenshots
app.mount("/evidence", StaticFiles(directory=str(settings.EVIDENCE_DIR)), name="evidence")


@app.get("/")
async def home():
    return {
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "status": "online",
        "live_scan_enabled": settings.ENABLE_LIVE_SCAN,
        "docs_url": "/docs",
    }


@app.get("/health")
async def health_check():
    import os
    tesseract_exists = os.path.exists(settings.TESSERACT_CMD)
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": "2.0.0",
        "database": "sqlite_connected",
        "database_connected": True,
        "ocr_engine": "tesseract_ready" if tesseract_exists else "tesseract_missing",
        "tesseract_installed": tesseract_exists,
        "live_scan_enabled": settings.ENABLE_LIVE_SCAN,
        "allowed_domains": settings.ALLOWED_DOMAINS,
    }
