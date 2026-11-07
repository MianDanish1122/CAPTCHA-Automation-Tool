import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file if available
load_dotenv(dotenv_path=BASE_DIR / ".env")


def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


class Settings:
    BASE_DIR: Path = BASE_DIR
    APP_NAME: str = os.getenv("APP_NAME", "CAPTCHA Automation Tool")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = get_bool_env("DEBUG", True)

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Security controls
    ENABLE_LIVE_SCAN: bool = get_bool_env("ENABLE_LIVE_SCAN", False)
    _allowed = os.getenv("ALLOWED_DOMAINS", "example.com,demo.com,localhost")
    ALLOWED_DOMAINS: list[str] = [d.strip().lower() for d in _allowed.split(",") if d.strip()]

    REQUEST_TIMEOUT_MS: int = int(os.getenv("REQUEST_TIMEOUT_MS", "15000"))
    MAX_CONCURRENT_PAGES: int = int(os.getenv("MAX_CONCURRENT_PAGES", "3"))

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'captcha_tool.db'}")

    # OCR and Tesseract
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    # Official Google reCAPTCHA test keys
    RECAPTCHA_TEST_SITE_KEY: str = os.getenv(
        "RECAPTCHA_TEST_SITE_KEY", "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
    )
    RECAPTCHA_TEST_SECRET_KEY: str = os.getenv(
        "RECAPTCHA_TEST_SECRET_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
    )

    # Directories
    REPORTS_DIR: Path = BASE_DIR / "reports"
    UPLOADS_DIR: Path = BASE_DIR / "uploads"
    DATA_DIR: Path = BASE_DIR / "data"
    EVIDENCE_DIR: Path = BASE_DIR / "evidence"
    SCANS_EVIDENCE_DIR: Path = BASE_DIR / "evidence" / "scans"

    # Crawler configuration
    CRAWLER_MAX_PAGES: int = int(os.getenv("CRAWLER_MAX_PAGES", "10"))
    CRAWLER_MAX_DEPTH: int = int(os.getenv("CRAWLER_MAX_DEPTH", "2"))
    CRAWLER_PAGE_TIMEOUT_MS: int = int(os.getenv("CRAWLER_PAGE_TIMEOUT_MS", "10000"))
    CRAWLER_TOTAL_TIMEOUT_SEC: int = int(os.getenv("CRAWLER_TOTAL_TIMEOUT_SEC", "60"))
    CRAWLER_USER_AGENT: str = os.getenv(
        "CRAWLER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 TechnologyBrainz-Crawler/2.0"
    )


settings = Settings()

# Ensure standard runtime directories exist
settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
settings.SCANS_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
