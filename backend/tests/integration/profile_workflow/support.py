"""Shared fixtures and helpers for the Phase 3 profile-workflow exit suite."""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from app.config import Settings, load_settings
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.main import create_app
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.chat_service import ChatService
from app.services.cv_ingestion import CvIngestionService
from app.services.profile_service import ProfileCommitService
from app.services.shopaikey_chat import ShopAIKeyChatAdapter
from app.tools.candidate_context import (
    CandidateContextToolService,
    create_candidate_context_tool,
)
from app.tools.profile_commit import (
    ProfileCommitToolService,
    create_profile_commit_tool,
)
from app.tools.profile_draft import ProfileDraftToolService, create_profile_draft_tools
from app.tools.registry import create_production_registry
from fastapi.testclient import TestClient
from tests.fakes.agent_tools import ScriptedDecision
from tests.fakes.profile_extraction import StructuredFactory
from tests.graph.fakes import FakeDriver

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
APP_SRC = BACKEND_ROOT / "app"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
API_SRC = BACKEND_ROOT / "app" / "api"

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-profile-workflow"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-profile-workflow"
SENTINEL_URI = "bolt://profile-workflow-test.invalid:7687"

CONTACT_EMAIL = "unique-contact-sentinel@example.test"
CONTACT_PHONE = "+1 555 010 0199"
CONTACT_ADDRESS = "Address: 99 Unique Sentinel Street"
CONTACT_SENTINELS = (CONTACT_EMAIL, CONTACT_PHONE, "99 Unique Sentinel Street")

CV_BODY = "\n".join(
    [
        CONTACT_EMAIL,
        CONTACT_PHONE,
        CONTACT_ADDRESS,
        "Backend Engineer 2020-2024",
        "Python 2020-2024",
        "Zig experimental",
        "ObsoleteSkill retired",
    ]
)

PRODUCTION_FORBIDDEN_RE = re.compile(
    r"echo_label|make_echo_label_tool|tests\.fakes\.agent_tools|"
    r"\braw_cv\b|"
    r"save_job\s*\(|query_jobs\s*\(|match_jobs\s*\("
)

AUTHORIZED_APP_PATHS = frozenset(
    {
        "/api/health",
        "/api/attachments/cv",
        "/api/profile",
        "/api/profile/cv",
        "/api/chat/history",
        "/api/chat/turns",
        "/api/chat/runs/{run_id}/resume",
    }
)


def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


@contextmanager
def sqlite_path_env(db_path: Path) -> Iterator[None]:
    previous = os.environ.get("SQLITE_PATH")
    os.environ["SQLITE_PATH"] = str(db_path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SQLITE_PATH", None)
        else:
            os.environ["SQLITE_PATH"] = previous


def upgrade_head(db_path: Path) -> None:
    with sqlite_path_env(db_path):
        command.upgrade(alembic_config(), "head")


def make_settings(tmp_path: Path, **overrides: str) -> Settings:
    values: dict[str, str] = {
        "APP_ENV": "local",
        "FRONTEND_ORIGIN": "http://localhost:5173",
        "VITE_API_BASE_URL": "http://localhost:8000",
        "SQLITE_PATH": str(tmp_path / "profile_workflow.db"),
        "FILES_DIR": str(tmp_path / "files"),
        "NEO4J_URI": SENTINEL_URI,
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
        "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
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
    values.update(overrides)
    return load_settings(environ=values)


@asynccontextmanager
async def migrated_db(
    tmp_path: Path,
    **settings_overrides: str,
) -> AsyncIterator[
    tuple[Path, DatabaseSessionManager, Settings, FilesystemAttachmentStorage]
]:
    settings = make_settings(tmp_path, **settings_overrides)
    db_path = Path(settings.sqlite_path)
    upgrade_head(db_path)
    manager = create_session_manager(db_path)
    storage = FilesystemAttachmentStorage(settings.files_dir)
    try:
        yield db_path, manager, settings, storage
    finally:
        await manager.dispose()


def parse_sse_payloads(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in re.split(r"\n\n+", body.strip()):
        if not block.strip():
            continue
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        events.append(json.loads("\n".join(data_lines)))
    return events


def assert_no_contact(*blobs: Any) -> None:
    def walk(obj: Any) -> None:
        if obj is None:
            return
        if isinstance(obj, str):
            for sentinel in CONTACT_SENTINELS:
                assert sentinel not in obj, f"contact sentinel leaked: {sentinel!r}"
            assert SENTINEL_API_KEY not in obj
            assert SENTINEL_NEO4J_PASSWORD not in obj
            return
        if isinstance(obj, (bytes, bytearray)):
            raw = bytes(obj)
            for sentinel in CONTACT_SENTINELS:
                assert sentinel.encode("utf-8") not in raw
            return
        if isinstance(obj, Mapping):
            for key, value in obj.items():
                walk(key)
                walk(value)
            return
        if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            for item in obj:
                walk(item)
            return
        if isinstance(obj, (int, float, bool)):
            return
        walk(str(obj))

    for blob in blobs:
        walk(blob)


def extraction_payload(
    *,
    summary: str = "Backend engineer with Python experience.",
    title: str = "Backend Engineer",
    include_excluded: bool = True,
) -> dict[str, object]:
    skills: list[dict[str, object]] = [
        {
            "skill": {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": [],
                "category": None,
                "status": "provisional",
                "confidence": 0.9,
                "evidence": ["Python 2020-2024"],
            },
            "proficiency": "advanced",
            "years": 4,
            "source": "cv",
            "excluded": False,
            "evidence": ["Python 2020-2024"],
        },
        {
            "skill": {
                "canonical_key": "zig",
                "display_name": "Zig",
                "aliases": [],
                "category": None,
                "status": "provisional",
                "confidence": 0.5,
                "evidence": ["Zig experimental"],
            },
            "proficiency": "beginner",
            "years": None,
            "source": "cv",
            "excluded": False,
            "evidence": ["Zig experimental"],
        },
    ]
    if include_excluded:
        skills.append(
            {
                "skill": {
                    "canonical_key": "obsolete_skill",
                    "display_name": "ObsoleteSkill",
                    "aliases": [],
                    "category": None,
                    "status": "provisional",
                    "confidence": 0.4,
                    "evidence": ["ObsoleteSkill retired"],
                },
                "proficiency": "beginner",
                "years": None,
                "source": "cv",
                "excluded": True,
                "evidence": ["ObsoleteSkill retired"],
            }
        )
    return {
        "summary": summary,
        "current_title": title,
        "total_experience_years": 4,
        "skills": skills,
        "experiences": [
            {
                "title": "Backend Engineer",
                "organization": "Example Co",
                "date_range": "2020-2024",
                "summary": "Built Python services.",
                "evidence": ["Backend Engineer 2020-2024"],
            }
        ],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.9,
    }


def profile_adapter_pair(
    responses: Sequence[object],
) -> tuple[ShopAIKeyChatAdapter, StructuredFactory]:
    factory = StructuredFactory(list(responses))
    adapter = ShopAIKeyChatAdapter(
        base_url="https://provider.invalid/v1",
        api_key="test-extraction-key",
        model="gpt-4o-mini",
        model_factory=factory,
    )
    return adapter, factory


def build_tools(
    manager: DatabaseSessionManager,
    storage: FilesystemAttachmentStorage,
    settings: Settings,
    *,
    extraction_responses: Sequence[object],
) -> tuple[list[Any], StructuredFactory]:
    adapter, factory = profile_adapter_pair(extraction_responses)
    ingestion = CvIngestionService(
        manager,
        storage,
        max_size_bytes=settings.max_pdf_size_mb * 1024 * 1024,
        max_pages=settings.max_pdf_pages,
        profile_adapter=adapter,
    )
    draft_tools = create_profile_draft_tools(
        ProfileDraftToolService(manager, ingestion)
    )
    commit_tool = create_profile_commit_tool(
        ProfileCommitToolService(ProfileCommitService(manager, storage))
    )
    context_tool = create_candidate_context_tool(CandidateContextToolService(manager))
    tools = [context_tool, *draft_tools, commit_tool]
    create_production_registry(tools)
    return tools, factory


def build_app(
    *,
    manager: DatabaseSessionManager,
    settings: Settings,
    db_path: Path,
    storage: FilesystemAttachmentStorage,
    decision: ScriptedDecision | None = None,
    tools: Sequence[Any] | None = None,
) -> Any:
    chat = ChatService(
        manager,
        sqlite_path=db_path,
        decision=decision,
        tools=list(tools) if tools is not None else None,
    )
    return create_app(
        settings=settings,
        session_manager=manager,
        storage=storage,
        neo4j_client=Neo4jClient.from_settings(
            settings,
            driver_factory=FakeDriver,
            health_timeout_seconds=0.2,
        ),
        chat_service=chat,
        run_schema_setup=False,
    )


def upload_cv(client: TestClient, pdf: bytes, name: str = "cv.pdf") -> dict[str, Any]:
    response = client.post(
        "/api/attachments/cv",
        files={"file": (name, pdf, "application/pdf")},
    )
    return {
        "status": response.status_code,
        "body": response.json() if response.content else {},
        "text": response.text,
    }


def oversized_pdf_bytes(*, limit_bytes: int) -> bytes:
    """Valid PDF magic + body that exceeds ``limit_bytes`` during stream intake.

    Size is checked before parse, so the payload need not be a well-formed PDF
    beyond the ``%PDF-`` magic prefix.
    """
    if limit_bytes < 1:
        raise ValueError("limit_bytes must be positive")
    prefix = b"%PDF-1.4\n"
    # Exceed the configured ceiling by at least one byte.
    pad_len = limit_bytes - len(prefix) + 1
    return prefix + (b"0" * pad_len)


__all__ = [
    "API_SRC",
    "APP_SRC",
    "AUTHORIZED_APP_PATHS",
    "CONTACT_SENTINELS",
    "CV_BODY",
    "FRONTEND_SRC",
    "PRODUCTION_FORBIDDEN_RE",
    "REPO_ROOT",
    "SENTINEL_API_KEY",
    "SENTINEL_NEO4J_PASSWORD",
    "assert_no_contact",
    "build_app",
    "build_tools",
    "extraction_payload",
    "make_settings",
    "migrated_db",
    "oversized_pdf_bytes",
    "parse_sse_payloads",
    "profile_adapter_pair",
    "upload_cv",
    "upgrade_head",
]
