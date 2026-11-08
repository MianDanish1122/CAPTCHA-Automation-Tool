#!/usr/bin/env bash
# Container entrypoint: migrate the database, optionally create the reviewer login from env vars, start the API.
set -euo pipefail

python -m alembic upgrade head

# Reviewer account for the people who will test the deployment (credentials come from the environment, never from the repo).
if [ -n "${REVIEW_USER:-}" ] && [ -n "${REVIEW_PASSWORD:-}" ]; then
  python scripts/seed_review_user.py
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
