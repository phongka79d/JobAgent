from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import load_settings
from app.main import create_app
from fastapi.testclient import TestClient
from tests.services.test_cv_ingestion import pdf_bytes


def settings(tmp_path: Path):
    return load_settings(environ={"APP_ENV": "local", "FRONTEND_ORIGIN": "http://localhost:5173", "VITE_API_BASE_URL": "http://localhost:8000", "SQLITE_PATH": str(tmp_path / "db.sqlite"), "FILES_DIR": str(tmp_path / "files"), "NEO4J_URI": "bolt://invalid:7687", "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": "secret", "SHOPAIKEY_BASE_URL": "https://example.invalid/v1", "SHOPAIKEY_API_KEY": "secret", "LLM_MODEL": "gpt-4o-mini", "LLM_TEMPERATURE": "0", "EMBEDDING_MODEL": "text-embedding-3-small", "EMBEDDING_DIMENSIONS": "1536", "MAX_PDF_SIZE_MB": "10", "MAX_PDF_PAGES": "10", "URL_FETCH_TIMEOUT_SECONDS": "10", "URL_MAX_RESPONSE_MB": "5", "TOOL_LOOP_LIMIT": "6"})


def test_upload_returns_sanitized_metadata_and_stable_errors(tmp_path: Path) -> None:
    configured = settings(tmp_path)
    db = __import__("app.db.session", fromlist=["create_session_manager"]).create_session_manager(configured.sqlite_path)
    asyncio.run(db.create_all())
    app = create_app(settings=configured, session_manager=db, run_schema_setup=False)
    with TestClient(app) as client:
        response = client.post("/api/attachments/cv", files={"file": ("../cv.pdf", pdf_bytes(), "application/pdf")})
        bad = client.post("/api/attachments/cv", files={"file": ("cv.txt", b"no", "text/plain")})
    assert response.status_code == 201
    assert set(response.json()) == {"id", "original_name", "mime_type", "size_bytes", "page_count", "state"}
    assert response.json()["original_name"] == "cv.pdf"
    assert str(tmp_path) not in response.text
    assert bad.status_code == 415
    assert bad.json() == {"detail": {"code": "UNSUPPORTED_MEDIA_TYPE"}}


def test_malformed_pdf_error_is_stable_and_sanitized(tmp_path: Path) -> None:
    configured = settings(tmp_path)
    db = __import__("app.db.session", fromlist=["create_session_manager"]).create_session_manager(configured.sqlite_path)
    asyncio.run(db.create_all())
    app = create_app(settings=configured, session_manager=db, run_schema_setup=False)

    with TestClient(app) as client:
        response = client.post("/api/attachments/cv", files={"file": ("cv.pdf", b"%PDF-malformed", "application/pdf")})

    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "MALFORMED_PDF"}}
    assert str(tmp_path) not in response.text
    assert "%PDF-malformed" not in response.text