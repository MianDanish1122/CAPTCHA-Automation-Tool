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
    APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()
    
    # DEBUG defaults to False in production/staging; True only in development
    _default_debug = True if APP_ENV == "development" else False
    DEBUG: bool = get_bool_env("DEBUG", _default_debug)

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Security controls: Server-controlled loopback testing
    # Default is False. ONLY effective when APP_ENV in ("development", "test").
    ALLOW_DEV_LOOPBACK: bool = get_bool_env("ALLOW_DEV_LOOPBACK", False)

    @property
    def can_allow_loopback(self) -> bool:
        """Returns True ONLY if explicitly enabled AND running in dev/test."""
        return self.ALLOW_DEV_LOOPBACK and (self.APP_ENV in ("development", "test"))

    # Local `fixture://` demo pages. Only ever honored in development/test environments;
    # staging/production ignore this flag entirely.
    ALLOW_FIXTURES: bool = get_bool_env("ALLOW_FIXTURES", True)

    @property
    def fixtures_enabled(self) -> bool:
        """Fixtures are available ONLY in development/test, regardless of ALLOW_FIXTURES."""
        return self.ALLOW_FIXTURES and (self.APP_ENV in ("development", "test"))

    # Proxy trust: forwarding headers (X-Forwarded-For) are honored ONLY when the direct
    # TCP peer is one of these IPs/CIDRs. Empty (default) = never trust forwarding headers.
    TRUSTED_PROXIES: list[str] = [
        p.strip() for p in os.getenv("TRUSTED_PROXIES", "").split(",") if p.strip()
    ]

    # TLS: certificate validation is ON by default. Disabling is a development-only opt-in.
    SCAN_ALLOW_INVALID_CERTS: bool = get_bool_env("SCAN_ALLOW_INVALID_CERTS", False)

    # Timeout for calls to CAPTCHA provider siteverify endpoints
    VERIFY_TIMEOUT_SECONDS: float = float(os.getenv("VERIFY_TIMEOUT_SECONDS", "8"))

    # Upper bound for any single proxied response body during guarded browsing.
    GUARD_MAX_RESPONSE_BYTES: int = int(os.getenv("GUARD_MAX_RESPONSE_BYTES", str(10 * 1024 * 1024)))

    # --- Phase 6B ---
    # One-time bootstrap: POST /api/auth/setup-initial-admin is DISABLED unless this secret is
    # configured (>= 24 chars) and presented in the X-Setup-Token header. Prefer the CLI.
    INITIAL_ADMIN_SETUP_TOKEN: str = os.getenv("INITIAL_ADMIN_SETUP_TOKEN", "")
    # HMAC key for the tamper-evident audit chain (defaults to a key derived from JWT_SECRET_KEY).
    AUDIT_HMAC_KEY: str = os.getenv("AUDIT_HMAC_KEY", "")
    # Comma-separated PREVIOUS audit keys, kept only so entries sealed before a rotation still verify.
    AUDIT_HMAC_KEYS_PREVIOUS: list[str] = [
        k.strip() for k in os.getenv("AUDIT_HMAC_KEYS_PREVIOUS", "").split(",") if k.strip()
    ]
    # Verify pre-key-id entries with the legacy JWT-derived key. Disable once no such entries remain.
    AUDIT_ALLOW_LEGACY_DERIVED_KEY: bool = get_bool_env("AUDIT_ALLOW_LEGACY_DERIVED_KEY", True)
    # Tokens issued before Phase 6B carry no `ver` claim. Reject them (forces one re-login after the
    # upgrade). Set false ONLY temporarily to let pre-upgrade sessions expire naturally.
    JWT_REQUIRE_VER_CLAIM: bool = get_bool_env("JWT_REQUIRE_VER_CLAIM", True)

    # Request / input limits
    MAX_JSON_BODY_BYTES: int = int(os.getenv("MAX_JSON_BODY_BYTES", str(2 * 1024 * 1024)))
    MAX_HTML_CHARS: int = int(os.getenv("MAX_HTML_CHARS", "200000"))
    MAX_IMAGE_BYTES: int = int(os.getenv("MAX_IMAGE_BYTES", str(1024 * 1024)))
    MAX_IMAGE_PIXELS: int = int(os.getenv("MAX_IMAGE_PIXELS", str(4_000_000)))

    # Additional rate limits (per minute per client)
    RATE_LIMIT_COMPUTE_PER_MIN: int = int(os.getenv("RATE_LIMIT_COMPUTE_PER_MIN", "30"))
    RATE_LIMIT_ADMIN_PER_MIN: int = int(os.getenv("RATE_LIMIT_ADMIN_PER_MIN", "20"))
    RATE_LIMIT_SETUP_PER_MIN: int = int(os.getenv("RATE_LIMIT_SETUP_PER_MIN", "3"))

    # Background job limits
    MAX_CONCURRENT_CRAWLS: int = int(os.getenv("MAX_CONCURRENT_CRAWLS", "2"))
    MAX_CONCURRENT_BATCH_JOBS: int = int(os.getenv("MAX_CONCURRENT_BATCH_JOBS", "1"))
    MAX_ACTIVE_JOBS_PER_USER: int = int(os.getenv("MAX_ACTIVE_JOBS_PER_USER", "2"))

    ENABLE_LIVE_SCAN: bool = get_bool_env("ENABLE_LIVE_SCAN", False)
    _allowed = os.getenv("ALLOWED_DOMAINS", "example.com,demo.com,localhost")
    ALLOWED_DOMAINS: list[str] = [d.strip().lower() for d in _allowed.split(",") if d.strip()]

    # CORS Settings
    _cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    CORS_ALLOWED_ORIGINS: list[str] = [o.strip() for o in _cors_origins.split(",") if o.strip()]

    # Authentication & JWT
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY", "dev-insecure-secret-key-change-in-production-min32"
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Rate Limiting (Requests per minute per IP / Actor)
    RATE_LIMIT_LOGIN_PER_MIN: int = int(os.getenv("RATE_LIMIT_LOGIN_PER_MIN", "5"))
    RATE_LIMIT_INSPECT_PER_MIN: int = int(os.getenv("RATE_LIMIT_INSPECT_PER_MIN", "10"))
    RATE_LIMIT_BATCH_PER_MIN: int = int(os.getenv("RATE_LIMIT_BATCH_PER_MIN", "10"))
    RATE_LIMIT_BENCHMARK_PER_MIN: int = int(os.getenv("RATE_LIMIT_BENCHMARK_PER_MIN", "5"))
    RATE_LIMIT_REVIEWS_PER_MIN: int = int(os.getenv("RATE_LIMIT_REVIEWS_PER_MIN", "30"))
    RATE_LIMIT_DEFAULT_PER_MIN: int = int(os.getenv("RATE_LIMIT_DEFAULT_PER_MIN", "120"))

    # Resource Protection Limits
    REQUEST_TIMEOUT_MS: int = int(os.getenv("REQUEST_TIMEOUT_MS", "15000"))
    MAX_CONCURRENT_PAGES: int = int(os.getenv("MAX_CONCURRENT_PAGES", "3"))
    # Politeness: minimum seconds between two requests/inspections of the SAME external host (loopback exempt)
    # Fill discovered forms with SYNTHETIC data under a no-transmission lockdown (never submits). Off by default.
    BATCH_PROBE_FORMS: bool = os.getenv("BATCH_PROBE_FORMS", "false").lower() in ("1", "true", "yes")
    BATCH_MIN_HOST_INTERVAL_S: float = float(os.getenv("BATCH_MIN_HOST_INTERVAL_S", "5"))
    # Seconds to wait for JS-rendered CAPTCHA widgets per page (bounded)
    DETECTION_SETTLE_MS: int = int(os.getenv("DETECTION_SETTLE_MS", "6000"))
    DETECTION_EVIDENCE_WAIT_MS: int = int(os.getenv("DETECTION_EVIDENCE_WAIT_MS", "4000"))
    MAX_CSV_ROWS: int = int(os.getenv("MAX_CSV_ROWS", "300"))
    MAX_CSV_SIZE_BYTES: int = int(os.getenv("MAX_CSV_SIZE_BYTES", str(5 * 1024 * 1024)))

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
    CRAWLER_PAGE_TIMEOUT_MS: int = int(os.getenv("CRAWLER_PAGE_TIMEOUT_MS", "30000"))
    CRAWLER_TOTAL_TIMEOUT_SEC: int = int(os.getenv("CRAWLER_TOTAL_TIMEOUT_SEC", "60"))
    CRAWLER_USER_AGENT: str = os.getenv(
        "CRAWLER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 TechnologyBrainz-Crawler/2.0"
    )

    def validate_production_config(self) -> None:
        """Validate critical configuration constraints for production safety."""
        if self.APP_ENV in ("production", "staging"):
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production/staging.")
            if self.ALLOW_DEV_LOOPBACK:
                raise ValueError("ALLOW_DEV_LOOPBACK cannot be enabled in production/staging.")
            if (
                self.JWT_SECRET_KEY.startswith("dev-")
                or len(self.JWT_SECRET_KEY) < 32
            ):
                raise ValueError(
                    "Production requires a cryptographically strong JWT_SECRET_KEY of at least 32 characters."
                )
            if len(self.AUDIT_HMAC_KEY) < 32:
                raise ValueError("Production requires AUDIT_HMAC_KEY of at least 32 characters.")
            if self.AUDIT_HMAC_KEY == self.JWT_SECRET_KEY:
                raise ValueError("AUDIT_HMAC_KEY must be different from JWT_SECRET_KEY.")
            if self.INITIAL_ADMIN_SETUP_TOKEN and len(self.INITIAL_ADMIN_SETUP_TOKEN) < 24:
                raise ValueError("INITIAL_ADMIN_SETUP_TOKEN must be at least 24 characters when set.")
            if self.SCAN_ALLOW_INVALID_CERTS:
                raise ValueError("SCAN_ALLOW_INVALID_CERTS cannot be enabled in production/staging.")
            if "*" in self.CORS_ALLOWED_ORIGINS:
                raise ValueError("Wildcard '*' is prohibited in CORS_ALLOWED_ORIGINS in production/staging.")


settings = Settings()

# Ensure standard runtime directories exist
settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
settings.SCANS_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
