"""API tests for sanitized GET /api/profile and GET /api/profile/cv."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.config import Settings, load_settings
from app.db.enums import AttachmentState
from app.db.models.attachments import Attachment
from app.db.models.profile import CandidateProfile as CandidateProfileRow
from app.db.session import create_session_manager
from app.main import create_app
from app.repositories.attachments import AttachmentRepository, StagedAttachmentInput
from app.repositories.preferences import PreferencesRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences
from app.services.attachment_storage import FilesystemAttachmentStorage
from fastapi.testclient import TestClient
from sqlalchemy import text

PROHIBITED_SUBSTRINGS = (
    "storage_path",
    "file_hash",
    "embedding_model",
    "pdf_text",
    "pdf_body",
    "cv_text",
    "raw_text",
    "provider_payload",
    "draft_json",
    "draft_id",
    "SHOPAIKEY",
    "NEO4J_PASSWORD",
    "Traceback",
)


def _settings(tmp_path: Path) -> Settings:
    return load_settings(
        environ={
            "APP_ENV": "local",
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "VITE_API_BASE_URL": "http://localhost:8000",
            "SQLITE_PATH": str(tmp_path / "db.sqlite"),
            "FILES_DIR": str(tmp_path / "files"),
            "NEO4J_URI": "bolt://invalid:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "secret-profile-test",
            "SHOPAIKEY_BASE_URL": "https://example.invalid/v1",
            "SHOPAIKEY_API_KEY": "secret-profile-test",
            "LLM_MODEL": "gpt-4o-mini",
            "LLM_TEMPERATURE": "0",
            "EMBEDDING_MODEL": "text-embedding-3-small",
            "EMBEDDING_DIMENSIONS": "1536",
            "MAX_PDF_SIZE_MB": "10",
            "MAX_PDF_PAGES": "10",
            "URL_FETCH_TIMEOUT_SECONDS": "10",
            "URL_MAX_RESPONSE_MB": "5",
            "TOOL_LOOP_LIMIT": "6",
        }
    )


def _profile(summary: str = "Backend engineer") -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "summary": summary,
            "current_title": "Engineer",
            "total_experience_years": None,
            "skills": [],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.8,
        }
    )


def _preferences(role: str = "Backend") -> JobPreferences:
    return JobPreferences.model_validate(
        {
            "target_roles": [role],
            "preferred_locations": ["Remote"],
            "acceptable_work_modes": ["remote"],
            "target_seniority": ["mid"],
        }
    )


def _client(tmp_path: Path) -> tuple[TestClient, Settings, Any, FilesystemAttachmentStorage]:
    configured = _settings(tmp_path)
    db = create_session_manager(configured.sqlite_path)
    asyncio.run(db.create_all())
    storage = FilesystemAttachmentStorage(configured.files_dir)
    app = create_app(
        settings=configured,
        session_manager=db,
        storage=storage,
        run_schema_setup=False,
    )
    return TestClient(app), configured, db, storage


async def _seed_active_cv(
    db: Any,
    storage: FilesystemAttachmentStorage,
    *,
    content: bytes,
    original_name: str = "resume.pdf",
    page_count: int = 1,
) -> UUID:
    attachment_id = uuid4()
    stored = await storage.stage(
        attachment_id,
        _chunks(content),
    )
    active_path = await storage.promote(stored.storage_path)
    async with db.session_scope() as session:
        await AttachmentRepository(session).add_staged(
            StagedAttachmentInput(
                id=attachment_id,
                file_hash=attachment_id.hex,
                original_name=original_name,
                mime_type="application/pdf",
                size_bytes=len(content),
                storage_path=f"staged/{attachment_id}",
                page_count=page_count,
            )
        )
        # Stage path was promoted; rewrite mark after promote path exists.
        # add_staged expects staged path; mark_active sets active path.
        await AttachmentRepository(session).mark_active(
            attachment_id,
            storage_path=active_path,
        )
    return attachment_id


async def _chunks(payload: bytes):
    for offset in range(0, len(payload), 5):
        yield payload[offset : offset + 5]


def test_get_profile_no_profile_is_deterministic(tmp_path: Path) -> None:
    client, configured, db, _storage = _client(tmp_path)
    with client:
        response = client.get("/api/profile")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "state": "none",
        "profile": None,
        "preferences": None,
        "active_attachment": None,
    }
    text_body = response.text
    for token in PROHIBITED_SUBSTRINGS:
        assert token not in text_body
    assert str(tmp_path) not in text_body
    assert str(configured.files_dir) not in text_body
    asyncio.run(db.dispose())


def test_get_profile_active_without_preferences(tmp_path: Path) -> None:
    client, configured, db, storage = _client(tmp_path)
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=b"%PDF-1.4 active-no-prefs")
    )

    async def seed() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("No prefs profile"),
                active_attachment_id=attachment_id,
            )

    asyncio.run(seed())
    with client:
        response = client.get("/api/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "active"
    assert body["profile"]["summary"] == "No prefs profile"
    assert body["preferences"] is None
    assert body["active_attachment"] is not None
    meta = body["active_attachment"]
    assert set(meta.keys()) == {
        "id",
        "original_name",
        "mime_type",
        "size_bytes",
        "page_count",
        "state",
    }
    assert meta["id"] == str(attachment_id)
    assert meta["original_name"] == "resume.pdf"
    assert meta["mime_type"] == "application/pdf"
    assert meta["state"] == AttachmentState.ACTIVE.value
    assert "file_hash" not in meta
    assert "storage_path" not in meta
    assert "embedding_model" not in body
    assert str(tmp_path) not in response.text
    asyncio.run(db.dispose())


def test_get_profile_active_with_preferences_and_safe_metadata(tmp_path: Path) -> None:
    client, configured, db, storage = _client(tmp_path)
    payload = b"%PDF-1.4 with-prefs-content"
    attachment_id = asyncio.run(
        _seed_active_cv(
            db,
            storage,
            content=payload,
            original_name="../evil\\path/My CV.pdf",
        )
    )

    async def seed() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("With prefs"),
                active_attachment_id=attachment_id,
                embedding_model="text-embedding-3-small",
            )
            await PreferencesRepository(session).replace(_preferences("Platform"))

    asyncio.run(seed())
    with client:
        response = client.get("/api/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "active"
    assert body["profile"]["summary"] == "With prefs"
    assert body["preferences"]["target_roles"] == ["Platform"]
    assert body["active_attachment"]["original_name"] == "My CV.pdf" or body[
        "active_attachment"
    ]["original_name"].endswith("My CV.pdf")
    # Path traversal leaves must not appear as stored authority in response paths.
    assert "storage_path" not in response.text
    assert "embedding_model" not in response.text
    assert "file_hash" not in response.text
    assert "text-embedding-3-small" not in response.text
    assert str(configured.files_dir) not in response.text
    asyncio.run(db.dispose())


def test_get_profile_invalid_stored_json(tmp_path: Path) -> None:
    from app.db.base import SINGLETON_PK

    client, _configured, db, _storage = _client(tmp_path)

    async def seed_bad() -> None:
        async with db.session_scope() as session:
            session.add(
                CandidateProfileRow(
                    id=SINGLETON_PK,
                    profile_json={"not": "a valid profile"},
                    active_attachment_id=None,
                    embedding_model=None,
                )
            )

    asyncio.run(seed_bad())
    with client:
        response = client.get("/api/profile")
    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "PROFILE_INVALID"}}
    assert "not" not in response.text or "valid profile" not in response.text
    assert "profile_json" not in response.text
    asyncio.run(db.dispose())


def test_get_profile_cv_streams_active_bytes_with_safe_headers(tmp_path: Path) -> None:
    client, configured, db, storage = _client(tmp_path)
    # Multi-chunk payload exercises streaming reassembly.
    content = b"%PDF-1.4 " + (b"chunked-pdf-body-" * 40)
    attachment_id = asyncio.run(
        _seed_active_cv(
            db,
            storage,
            content=content,
            original_name='../quote"name.pdf',
        )
    )

    async def seed() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Download me"),
                active_attachment_id=attachment_id,
            )

    asyncio.run(seed())
    with client:
        response = client.get("/api/profile/cv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    disposition = response.headers["content-disposition"]
    assert "inline" in disposition.lower()
    assert "filename=" in disposition.lower()
    assert ".." not in disposition
    assert "\\" not in disposition
    assert str(tmp_path) not in disposition
    assert str(configured.files_dir) not in response.text
    assert response.content == content
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("x-content-type-options") == "nosniff"
    asyncio.run(db.dispose())


def test_get_profile_cv_no_active_is_not_found(tmp_path: Path) -> None:
    client, _configured, db, _storage = _client(tmp_path)
    with client:
        empty = client.get("/api/profile/cv")
    assert empty.status_code == 404
    assert empty.json() == {"detail": {"code": "NO_ACTIVE_CV"}}

    async def seed_profile_only() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(_profile("No CV link"))

    asyncio.run(seed_profile_only())
    with client:
        response = client.get("/api/profile/cv")
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "NO_ACTIVE_CV"}}
    asyncio.run(db.dispose())


def test_get_profile_cv_missing_bytes_is_integrity_failure(tmp_path: Path) -> None:
    client, configured, db, storage = _client(tmp_path)
    content = b"%PDF-1.4 will-delete"
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=content)
    )

    async def seed() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Missing bytes"),
                active_attachment_id=attachment_id,
            )

    asyncio.run(seed())
    # Remove bytes while leaving the singleton reference intact.
    active_file = Path(configured.files_dir) / "active" / str(attachment_id)
    assert active_file.is_file()
    active_file.unlink()

    with client:
        response = client.get("/api/profile/cv")
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "BLOCKED_BY_DATA_INTEGRITY"}}
    assert str(tmp_path) not in response.text
    assert str(attachment_id) not in response.text or "BLOCKED" in response.text
    asyncio.run(db.dispose())


def test_get_profile_cv_mismatched_path_is_integrity_failure(tmp_path: Path) -> None:
    client, _configured, db, storage = _client(tmp_path)
    content = b"%PDF-1.4 mismatch"
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=content)
    )

    async def seed_and_corrupt() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Mismatch"),
                active_attachment_id=attachment_id,
            )
            row = await session.get(Attachment, attachment_id)
            assert row is not None
            # Path leaf no longer matches attachment id / area authority.
            row.storage_path = f"active/{uuid4()}"

    asyncio.run(seed_and_corrupt())
    with client:
        response = client.get("/api/profile/cv")
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "BLOCKED_BY_DATA_INTEGRITY"}}
    asyncio.run(db.dispose())


def test_stale_unreferenced_active_row_is_not_downloadable(tmp_path: Path) -> None:
    client, _configured, db, storage = _client(tmp_path)
    stale_bytes = b"%PDF-1.4 stale-unreferenced"
    current_bytes = b"%PDF-1.4 current-active"
    stale_id = asyncio.run(_seed_active_cv(db, storage, content=stale_bytes))
    current_id = asyncio.run(
        _seed_active_cv(db, storage, content=current_bytes, original_name="current.pdf")
    )

    async def seed() -> None:
        async with db.session_scope() as session:
            # Only current is referenced by the singleton.
            await ProfileRepository(session).replace(
                _profile("Current only"),
                active_attachment_id=current_id,
            )

    asyncio.run(seed())
    with client:
        ok = client.get("/api/profile/cv")
        profile = client.get("/api/profile")
    assert ok.status_code == 200
    assert ok.content == current_bytes
    assert ok.content != stale_bytes
    assert profile.json()["active_attachment"]["id"] == str(current_id)
    assert profile.json()["active_attachment"]["id"] != str(stale_id)
    # There is no public path that accepts an attachment id for download.
    with client:
        methods = client.app.openapi()["paths"]["/api/profile/cv"]  # type: ignore[attr-defined]
        assert list(methods.keys()) == ["get"]
    asyncio.run(db.dispose())


def test_no_public_profile_mutation_routes(tmp_path: Path) -> None:
    client, _configured, db, _storage = _client(tmp_path)
    with client:
        openapi = client.app.openapi()  # type: ignore[attr-defined]
        paths = openapi["paths"]
        assert set(paths["/api/profile"].keys()) == {"get"}
        assert set(paths["/api/profile/cv"].keys()) == {"get"}
        for method in ("put", "patch", "delete", "post"):
            assert client.request(method.upper(), "/api/profile").status_code in {
                405,
                404,
            }
            assert client.request(method.upper(), "/api/profile/cv").status_code in {
                405,
                404,
            }
            assert client.request(
                method.upper(), f"/api/profile/{uuid4()}"
            ).status_code in {405, 404}
            assert client.request(
                method.upper(), "/api/profile/commit"
            ).status_code in {405, 404}
    asyncio.run(db.dispose())


def test_profile_response_omits_prohibited_sentinels(tmp_path: Path) -> None:
    client, configured, db, storage = _client(tmp_path)
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=b"%PDF-1.4 sentinel")
    )

    async def seed() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Sentinel check"),
                active_attachment_id=attachment_id,
                embedding_model="must-not-leak",
            )
            await PreferencesRepository(session).replace(_preferences())

    asyncio.run(seed())
    with client:
        profile = client.get("/api/profile")
        cv = client.get("/api/profile/cv")
    combined = profile.text + cv.text + str(profile.headers) + str(cv.headers)
    for token in PROHIBITED_SUBSTRINGS:
        assert token not in combined
    assert "must-not-leak" not in combined
    assert str(configured.files_dir) not in combined
    assert "active/" not in profile.text
    assert "staged/" not in profile.text
    asyncio.run(db.dispose())


def test_non_active_referenced_attachment_is_integrity_failure(tmp_path: Path) -> None:
    """Singleton must not stream a referenced row that is no longer active."""
    client, _configured, db, storage = _client(tmp_path)
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=b"%PDF-1.4 wrong-state")
    )

    async def seed_wrong_state() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Wrong state"),
                active_attachment_id=attachment_id,
            )
            row = await session.get(Attachment, attachment_id)
            assert row is not None
            # Corrupt durable state: still referenced, no longer ACTIVE.
            row.state = AttachmentState.STAGED.value
            row.storage_path = f"staged/{attachment_id}"

    asyncio.run(seed_wrong_state())
    with client:
        response = client.get("/api/profile/cv")
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "BLOCKED_BY_DATA_INTEGRITY"}}
    assert str(tmp_path) not in response.text
    asyncio.run(db.dispose())


def _assert_profile_integrity_409(response: Any, *, tmp_path: Path) -> None:
    """GET /api/profile integrity failures are sanitized 409 only."""
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "BLOCKED_BY_DATA_INTEGRITY"}}
    text_body = response.text
    for token in PROHIBITED_SUBSTRINGS:
        assert token not in text_body
    assert str(tmp_path) not in text_body
    assert "active/" not in text_body
    assert "staged/" not in text_body
    assert "storage_path" not in text_body
    assert "file_hash" not in text_body


def test_get_profile_missing_referenced_row_is_integrity_failure(
    tmp_path: Path,
) -> None:
    """Singleton-referenced missing attachment must not soft-null metadata.

    Schema FK is ON DELETE SET NULL; production code never leaves a dangling id.
    Integrity regression requires a deliberate dangling reference: delete the
    attachment row with foreign_keys OFF so the singleton still points at the
    missing id (no cascade null, no fallback row).
    """
    client, _configured, db, storage = _client(tmp_path)
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=b"%PDF-1.4 missing-row")
    )

    async def seed_dangling_reference() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Missing attachment row"),
                active_attachment_id=attachment_id,
            )
        # One connection: disable FK, delete attachment, leave dangling pointer.
        # SQLite UUID columns store 32-char hex (no dashes), matching attachment_id.hex.
        async with db.engine.begin() as conn:
            await conn.execute(text("PRAGMA foreign_keys=OFF"))
            result = await conn.execute(
                text("DELETE FROM attachments WHERE id = :id"),
                {"id": attachment_id.hex},
            )
            assert result.rowcount == 1
            dangling = await conn.execute(
                text("SELECT active_attachment_id FROM candidate_profile WHERE id = 1")
            )
            assert str(dangling.scalar_one()).replace("-", "") == attachment_id.hex

    asyncio.run(seed_dangling_reference())
    with client:
        response = client.get("/api/profile")
    _assert_profile_integrity_409(response, tmp_path=tmp_path)
    assert response.json() == {"detail": {"code": "BLOCKED_BY_DATA_INTEGRITY"}}
    assert "active_attachment" not in response.json()
    asyncio.run(db.dispose())


def test_get_profile_wrong_attachment_state_is_integrity_failure(
    tmp_path: Path,
) -> None:
    """Referenced non-active attachment must 409, not return active_attachment=null."""
    client, _configured, db, storage = _client(tmp_path)
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=b"%PDF-1.4 profile-wrong-state")
    )

    async def seed_wrong_state() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Profile wrong state"),
                active_attachment_id=attachment_id,
            )
            row = await session.get(Attachment, attachment_id)
            assert row is not None
            row.state = AttachmentState.STAGED.value
            row.storage_path = f"staged/{attachment_id}"

    asyncio.run(seed_wrong_state())
    with client:
        response = client.get("/api/profile")
    _assert_profile_integrity_409(response, tmp_path=tmp_path)
    body = response.json()
    assert body == {"detail": {"code": "BLOCKED_BY_DATA_INTEGRITY"}}
    assert "profile" not in body
    assert "active_attachment" not in body
    asyncio.run(db.dispose())


def test_get_profile_mismatched_noncanonical_path_is_integrity_failure(
    tmp_path: Path,
) -> None:
    """Non-canonical or id-mismatched storage path must 409 on GET /api/profile."""
    client, _configured, db, storage = _client(tmp_path)
    content = b"%PDF-1.4 profile-path-mismatch"
    attachment_id = asyncio.run(
        _seed_active_cv(db, storage, content=content)
    )

    async def seed_and_corrupt() -> None:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Profile path mismatch"),
                active_attachment_id=attachment_id,
            )
            row = await session.get(Attachment, attachment_id)
            assert row is not None
            # Leaf no longer matches attachment id / active path authority.
            row.storage_path = f"active/{uuid4()}"

    asyncio.run(seed_and_corrupt())
    with client:
        response = client.get("/api/profile")
    _assert_profile_integrity_409(response, tmp_path=tmp_path)
    assert response.json() == {"detail": {"code": "BLOCKED_BY_DATA_INTEGRITY"}}
    asyncio.run(db.dispose())
