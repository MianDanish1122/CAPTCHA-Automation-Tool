# Backend image: FastAPI + Playwright Chromium + Tesseract (for the OCR fallback).
# The frontend is deployed separately (see docs/LIVE_DEPLOYMENT_STEPS.md).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TESSERACT_CMD=/usr/bin/tesseract

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY datasets ./datasets
COPY scripts ./scripts
COPY docker ./docker

RUN useradd --create-home appuser \
 && mkdir -p data evidence reports uploads \
 && chown -R appuser:appuser /app /ms-playwright
USER appuser

EXPOSE 8000
CMD ["bash", "docker/start.sh"]
