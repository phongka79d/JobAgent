# JobAgent backend — production-shaped local image.
# Build context: repository root (see infrastructure/docker-compose.yml).
# Does not copy root .env, private evaluation inputs, or host secrets.

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Non-root runtime user (uid/gid 1000 matches common local volume ownership).
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --home-dir /home/app \
       --shell /usr/sbin/nologin app \
    && mkdir -p /data/files \
    && chown -R app:app /data

# Dependency metadata first for layer reuse; then application package sources.
COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/app /app/app
COPY backend/migrations /app/migrations
COPY backend/alembic.ini /app/alembic.ini

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install . \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Listen on all interfaces inside the container network.
# Host publication is restricted to 127.0.0.1 in docker-compose.yml.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
