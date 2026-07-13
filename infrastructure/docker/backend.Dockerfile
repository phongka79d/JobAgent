# JobAgent backend: pinned Python, non-interactive install, migrate then serve.
# Build context: backend/. No source bind mounts at runtime.

FROM python:3.13.7-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Application package only (no tests, no repo-root env files).
COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini

# Use the base image pip as-is (no floating pip upgrade) for reproducible builds.
RUN python -m pip install --no-cache-dir .

# SQLite + FILES_DIR live under /data (Compose application volume).
EXPOSE 8000

# Alembic owns schema; never create_all(). Listen on all interfaces inside the
# container; Compose publishes only 127.0.0.1 on the host.
CMD ["sh", "-c", "mkdir -p /data/files && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
