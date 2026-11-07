# Phase 5 Production Deployment & Operations Guide

**Project:** Technology Brainz — CAPTCHA Inspector  
**Classification:** DevOps & Security Operations Manual  
**Phase:** Phase 5 — Security Hardening & Production Readiness  

---

## 1. Production Architecture Overview

In a production environment, the CAPTCHA Inspector must be deployed behind a dedicated reverse proxy (such as Nginx, Caddy, or Cloudflare) with HTTPS termination and restrictive firewall policies:

```
[ Internet / Trusted Users ]
              │ (HTTPS:443)
              ▼
    ┌───────────────────┐
    │   Reverse Proxy   │ (Nginx / Caddy)
    │  SSL Termination  │ - Strict Rate Limiting
    │  Header Filtering │ - WebSocket / Proxy Buffers
    └─────────┬─────────┘
              │
      ┌───────┴───────────────────────┐
      │ (Port 3000)                   │ (Port 8000)
      ▼                               ▼
┌──────────────┐               ┌──────────────┐
│   Next.js    │               │   FastAPI    │
│  Dashboard   │               │   Backend    │
│  (Node.js)   │               │  (Uvicorn)   │
└──────────────┘               └──────┬───────┘
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                  ┌──────────────┐          ┌──────────────┐
                  │ SQLite / RDS │          │  Headless    │
                  │  (Database)  │          │  Playwright  │
                  └──────────────┘          └──────────────┘
```

---

## 2. Environment Configuration Hardening

### 2.1 Production `.env` Requirements

Create `/opt/captcha-tool/.env` with strict permissions (`chmod 600 .env`):

```bash
# Application Environment
APP_NAME="CAPTCHA Inspector Production"
APP_ENV="production"
DEBUG=false

# Server Binding (Bind to internal interface or localhost only)
HOST="127.0.0.1"
PORT=8000

# Security & Scanning Controls
ENABLE_LIVE_SCAN=false
ALLOWED_DOMAINS="client1.com,authorized-partner.org"
REQUEST_TIMEOUT_MS=15000
MAX_CONCURRENT_PAGES=3

# SSRF & Loopback Policy (MANDATORY: Must remain false in production)
ALLOW_DEV_LOOPBACK=false

# JWT Authentication (MANDATORY: Generate a high-entropy secret >= 64 chars)
# openssl rand -hex 32
JWT_SECRET_KEY="c49f8713a0c4987f2e109d9489ef048b61c9e830e2f5d75294a2e5d710bb9930"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=480

# CORS Allowed Origins (Set to exact HTTPS domain of your frontend)
CORS_ALLOWED_ORIGINS="https://inspector.technologybrainz.internal"

# Rate Limiting Controls
RATE_LIMIT_LOGIN_PER_MIN=5
RATE_LIMIT_INSPECT_PER_MIN=10
RATE_LIMIT_BATCH_PER_MIN=10
RATE_LIMIT_REVIEWS_PER_MIN=30
RATE_LIMIT_BENCHMARK_PER_MIN=5

# Resource Protection
MAX_CSV_FILE_SIZE_BYTES=5242880
MAX_CSV_ROWS=300

# Database
DATABASE_URL="sqlite:///./data/captcha_tool.db"

# OCR Binaries
TESSERACT_CMD="/usr/bin/tesseract"
```

> [!CAUTION]
> If `APP_ENV` is set to `production` and `DEBUG=true` or `ALLOW_DEV_LOOPBACK=true` is detected, FastAPI startup validation will immediately abort process execution with a `RuntimeError`.

---

## 3. Database Migration & Initialization Workflow

### Step 1: Run Database Schema Migrations
Always run Alembic migrations prior to starting the application service:
```bash
# Verify current migration status
alembic current

# Apply all pending schema migrations to head
alembic upgrade head
```

### Step 2: Provision the Initial Administrator
Run the administrative CLI tool from the local shell to create the primary administrator:
```bash
python -m app.cli create-admin admin admin@technologybrainz.internal StrongAdminPassword2026!
```

Verify the user exists:
```bash
python -m app.cli list-users
```

---

## 4. Reverse Proxy Configuration (Nginx Reference)

Deploy this configuration in `/etc/nginx/sites-available/captcha_inspector`:

```nginx
upstream fastapi_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

upstream nextjs_frontend {
    server 127.0.0.1:3000;
    keepalive 32;
}

server {
    listen 80;
    server_name inspector.technologybrainz.internal;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name inspector.technologybrainz.internal;

    ssl_certificate /etc/ssl/certs/captcha_inspector.crt;
    ssl_certificate_key /etc/ssl/private/captcha_inspector.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; img-src 'self' data:; style-src 'self' 'unsafe-inline';" always;

    client_max_body_size 6M;

    # Next.js Frontend Application
    location / {
        proxy_pass http://nextjs_frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # FastAPI Backend APIs
    location ~ ^/(api|health|docs|openapi.json) {
        proxy_pass http://fastapi_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Crawler Timeout Buffers
        proxy_read_timeout 60s;
        proxy_connect_timeout 15s;
    }
}
```

---

## 5. Automated Backup & Disaster Recovery Procedures

### 5.1 Routine Automated Backups
Schedule daily backups using the built-in CLI command via cron:
```bash
0 2 * * * cd /opt/captcha-tool && /opt/captcha-tool/venv/bin/python -m app.cli backup-db >> /var/log/captcha_backup.log 2>&1
```

The backup utility:
1. Opens an atomic SQLite connection.
2. Generates a timestamped snapshot: `data/backups/captcha_tool_backup_YYYYMMDD_HHMMSS.db`.
3. Verifies schema integrity.

### 5.2 Database Restoration
To restore from a backup:
```bash
# 1. Stop backend service
systemctl stop captcha-inspector-backend

# 2. Archive corrupted or current database
mv data/captcha_tool.db data/captcha_tool.db.corrupted

# 3. Copy snapshot to active database file
cp data/backups/captcha_tool_backup_20261107_094126.db data/captcha_tool.db

# 4. Verify migration head
alembic current

# 5. Restart backend service
systemctl start captcha-inspector-backend
```
