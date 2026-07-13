"""Public HTTP route package. Plan 2 exposes only GET /api/health."""

from app.api.health import router as health_router

__all__ = ["health_router"]
