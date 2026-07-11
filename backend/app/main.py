"""Minimal FastAPI application entrypoint.

Import and startup must not call ShopAIKey or load user credentials from the
real root ``.env``. Settings are loaded by later lifecycle owners when needed.
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the FastAPI application object (framework docs only for 01A)."""
    return FastAPI(
        title="JobAgent",
        version="0.1.0",
        description="JobAgent backend foundation",
    )


app = create_app()


def run() -> None:
    """Production-shaped local server command (localhost only)."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
