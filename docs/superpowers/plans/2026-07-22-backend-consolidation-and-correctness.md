# JobAgent Backend Consolidation and Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace duplicated backend infrastructure with canonical owners, remove import cycles, and bind active-CV evidence to one attachment identity while preserving every public API, transaction, and failure contract.

**Architecture:** Reuse the existing `session_scope`, introduce one schema-level SSE envelope builder and one API-level stream framer, consolidate chunk reads/counts in the chunk repository, and move shared DTO/protocol logic into dependency-neutral modules. Keep business coordinators separate: ingestion, re-extraction, matching, evaluation, CV activation, and Agent execution retain their current policies and side-effect ordering.

**Tech Stack:** Python 3.11+, FastAPI native SSE, Pydantic v2, SQLAlchemy/aiosqlite, LangGraph, Neo4j, Pytest, Ruff, Mypy, PowerShell, Git.

---

## Scope and invariant boundary

- Execute after Plan 16 changes to CV/JD extraction and selected-map owners are accepted and merged.
- Run after `2026-07-22-dead-code-cleanup.md`; that plan must not delete the canonical chunk getter used here.
- Preserve one Agent, one decision node, one ToolNode, seven tools, `TOOL_LOOP_LIMIT=6`, current route count, current SQLite schema, and current matching formula.
- Never hold a SQLite transaction across provider, filesystem, URL, Neo4j, or SSE work.
- Preserve exact JD non-failed dedupe, one repair, same-ID re-extraction CAS, no automatic evaluation, and truthful post-commit graph failures.
- Do not implement full SSRF/DNS/private-address protection, CI, telemetry, backup infrastructure, authentication, or any Master Plan out-of-scope system in this plan.
- The four `docs/superpowers/plans/2026-07-22-*.md` files are planning
  artifacts. They may already be tracked or may remain untracked when execution
  starts; implementation commits must not stage them.

### Task 1: Replace six local transaction wrappers with `session_scope`

**Files:**
- Create: `backend/tests/unit/test_service_transaction_ownership.py`
- Modify: `backend/app/services/chat_turns.py:12,47,88-99,206,283,305,318,345`
- Modify: `backend/app/services/cv_manager.py:13,33,95-105,366,402`
- Modify: `backend/app/services/cv_upload.py:20,35,75-87,383`
- Modify: `backend/app/services/profile_approval.py:28,131-143,500`
- Modify: `backend/app/services/profile_drafts.py:25,109-120,148,374,888`
- Modify: `backend/app/services/tool_execution.py:22,36,135-149,207,260,288`
- Test: `backend/tests/integration/test_database_pragmas.py`
- Test: `backend/tests/integration/test_tool_replay.py`
- Test: `backend/tests/integration/test_profile_approval.py`
- Test: `backend/tests/integration/test_cv_manager_deletion.py`

- [ ] **Step 1: Add a failing ownership test**

Create the complete test file:

```python
from __future__ import annotations

import inspect

import pytest

from app.services import (
    chat_turns,
    cv_manager,
    cv_upload,
    profile_approval,
    profile_drafts,
    tool_execution,
)


@pytest.mark.parametrize(
    "module",
    (
        chat_turns,
        cv_manager,
        cv_upload,
        profile_approval,
        profile_drafts,
        tool_execution,
    ),
)
def test_service_reuses_shared_session_scope(module: object) -> None:
    source = inspect.getsource(module)
    assert "def _short_transaction" not in source
    assert "session_scope" in source
```

- [ ] **Step 2: Run the ownership test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_service_transaction_ownership.py -q
```

Expected: six parametrized failures because every module still defines `_short_transaction`.

- [ ] **Step 3: Replace local wrappers with the existing canonical context manager**

In each service, remove `asynccontextmanager` and the local function, import `session_scope`, and make this exact mechanical replacement at every call site:

```diff
-async with _short_transaction(factory) as session:
+async with session_scope(factory) as session:
```

For `profile_approval.py` and `profile_drafts.py`, the existing argument is `session_factory` rather than `factory`; preserve that argument name. Keep every statement inside each transaction block in its current order.

- [ ] **Step 4: Run focused behavioral and ownership tests**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_service_transaction_ownership.py tests/integration/test_database_pragmas.py tests/integration/test_tool_replay.py tests/integration/test_profile_approval.py tests/integration/test_cv_manager_deletion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: all tests pass; commit-before-publication, rollback, CV activation, and deletion behavior remain unchanged; Ruff and Mypy pass.

- [ ] **Step 5: Commit the transaction-owner refactor**

```powershell
Set-Location ..
git add backend/app/services backend/tests/unit/test_service_transaction_ownership.py
git commit -m "refactor(backend): reuse shared session scope"
```

Expected: one commit with no repository, schema, route, or migration changes.

### Task 2: Consolidate SSE envelope creation and primed route framing

**Files:**
- Create: `backend/app/api/sse.py`
- Create: `backend/tests/unit/test_api_sse.py`
- Modify: `backend/app/schemas/sse.py:12-24,224-231`
- Modify: `backend/app/agent/runner.py:46-49,93-103`
- Modify: `backend/app/services/chat_turns.py:31-32,51,102-111`
- Modify: `backend/app/api/chat.py:12-29,62-105,150,168`
- Modify: `backend/app/api/cvs.py:11-32,76-111,134`
- Test: `backend/tests/unit/test_sse_contract.py`
- Test: `backend/tests/integration/test_chat_api.py`
- Test: `backend/tests/integration/test_cv_manager_api.py`

- [ ] **Step 1: Add the failing shared-helper tests**

Create `backend/tests/unit/test_api_sse.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import HTTPException

from app.api.sse import format_validated_sse, open_sse_response
from app.schemas.sse import SseEvent, build_sse_event
from app.services.chat_turns import ChatTurnError

RUN_ID = "11111111-1111-4111-8111-111111111111"


def _event() -> SseEvent:
    return build_sse_event(
        "assistant_status",
        RUN_ID,
        {"message": "Working"},
    )


def test_format_validated_sse_preserves_event_id_and_compact_json() -> None:
    event = _event()
    framed = format_validated_sse(event).decode("utf-8")
    assert "event: assistant_status" in framed
    assert f"id: {event.event_id}" in framed
    assert '"message":"Working"' in framed


@pytest.mark.asyncio
async def test_open_sse_response_maps_pre_yield_error() -> None:
    async def events() -> AsyncIterator[SseEvent]:
        raise ChatTurnError("RUN_NOT_FOUND", "run missing")
        yield _event()

    def mapper(exc: ChatTurnError) -> HTTPException:
        return HTTPException(
            status_code=404,
            detail={"code": exc.code, "summary": exc.message},
        )

    with pytest.raises(HTTPException) as exc_info:
        await open_sse_response(events(), error_mapper=mapper)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_open_sse_response_rejects_empty_stream() -> None:
    async def events() -> AsyncIterator[SseEvent]:
        if False:
            yield _event()

    with pytest.raises(HTTPException) as exc_info:
        await open_sse_response(
            events(),
            error_mapper=lambda exc: HTTPException(status_code=400),
        )
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "EMPTY_STREAM",
        "summary": "Agent stream produced no events",
    }
```

- [ ] **Step 2: Run the new test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_api_sse.py -q
```

Expected: collection fails because `app.api.sse` and `build_sse_event` do not exist.

- [ ] **Step 3: Add the canonical typed envelope builder**

Add these imports and function to `schemas/sse.py`:

```python
from app.core.ids import new_uuid
from app.core.time import utc_now


def build_sse_event(
    event: str,
    run_id: str,
    payload: dict[str, Any],
) -> SseEvent:
    """Build and validate one typed SSE event envelope."""
    return parse_sse_event(
        {
            "event": event,
            "event_id": new_uuid(),
            "run_id": run_id,
            "timestamp": utc_now(),
            "payload": payload,
        }
    )
```

Replace `runner._envelope(event, run_id, payload)` and `chat_turns._sse(event, run_id, payload)` call sites with `build_sse_event(event, run_id, payload)`, then remove the duplicate helpers and their now-unused `new_uuid`, `utc_now`, and `parse_sse_event` imports.

- [ ] **Step 4: Implement one API-level framer and priming owner**

Create `backend/app/api/sse.py`:

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable

from fastapi import HTTPException
from fastapi.sse import EventSourceResponse, format_sse_event

from app.schemas.sse import SseEvent, parse_sse_event, sse_event_to_dict
from app.services.chat_turns import ChatTurnError

ChatErrorMapper = Callable[[ChatTurnError], HTTPException]


def format_validated_sse(event: SseEvent) -> bytes:
    """Revalidate and frame one typed event as SSE wire bytes."""
    validated = parse_sse_event(sse_event_to_dict(event))
    payload = sse_event_to_dict(validated)
    return format_sse_event(
        data_str=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        event=validated.event,
        id=str(validated.event_id),
    )


async def open_sse_response(
    events: AsyncIterator[SseEvent],
    *,
    error_mapper: ChatErrorMapper,
) -> EventSourceResponse:
    """Prime before headers, then stream validated SSE frames."""
    iterator = events.__aiter__()
    try:
        first = await iterator.__anext__()
    except StopAsyncIteration:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "EMPTY_STREAM",
                "summary": "Agent stream produced no events",
            },
        ) from None
    except ChatTurnError as exc:
        raise error_mapper(exc) from exc

    first_bytes = format_validated_sse(first)

    async def produce() -> AsyncIterator[bytes]:
        yield first_bytes
        async for event in iterator:
            yield format_validated_sse(event)

    return EventSourceResponse(produce())
```

Replace route calls with:

```python
return await open_sse_response(events, error_mapper=_http_for_chat_error)
```

and:

```python
return await open_sse_response(events, error_mapper=_http_for_reprocess_error)
```

- [ ] **Step 5: Run SSE unit and route-contract tests**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_api_sse.py tests/unit/test_sse_contract.py tests/integration/test_agent_runner.py tests/integration/test_chat_api.py tests/integration/test_cv_manager_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: event order and bytes remain compatible; chat/CV pre-yield errors keep distinct status maps; empty streams remain JSON 500; all checks pass.

- [ ] **Step 6: Commit the SSE consolidation**

```powershell
Set-Location ..
git add backend/app/api backend/app/schemas/sse.py backend/app/agent/runner.py backend/app/services/chat_turns.py backend/tests/unit/test_api_sse.py
git commit -m "refactor(backend): centralize sse framing"
```

Expected: one transport-only refactor commit.

### Task 3: Establish canonical chunk contracts and repository reads

**Files:**
- Create: `backend/app/services/cv_chunk_contracts.py`
- Modify: `backend/app/services/profile_extraction.py:55-103`
- Modify: `backend/app/services/cv_document_extraction.py:33-37`
- Modify: `backend/app/services/profile_activation.py:25-28`
- Modify: `backend/app/repositories/attachment_text_chunks.py:12-18,86-106`
- Modify: `backend/app/repositories/observability.py:12-18,114-138,192-194`
- Modify: `backend/app/services/observability.py:20-60,371,429,436`
- Test: `backend/tests/unit/test_attachment_text_chunks.py`
- Test: `backend/tests/unit/test_cv_document_extraction.py`
- Test: `backend/tests/integration/test_observability_api.py`

- [ ] **Step 1: Add RED tests for direct SQL count and dependency direction**

Add to `test_attachment_text_chunks.py`:

```python
import inspect

from app.services import cv_document_extraction


def test_chunk_count_uses_sql_count_and_document_extraction_uses_contracts() -> None:
    count_source = inspect.getsource(chunk_repo.count_for_attachment)
    document_source = inspect.getsource(cv_document_extraction)
    assert "func.count" in count_source
    assert "list_for_attachment" not in count_source
    assert "app.services.cv_chunk_contracts" in document_source
    assert "app.services.profile_extraction" not in document_source
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_attachment_text_chunks.py::test_chunk_count_uses_sql_count_and_document_extraction_uses_contracts -q
```

Expected: failure because count materializes rows and document extraction imports profile extraction.

- [ ] **Step 3: Add the dependency-neutral chunk contract**

Create `cv_chunk_contracts.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Final

from app.db.models.attachment_text_chunks import CHUNK_PREVIEW_MAX_CHARS

FAILURE_EMPTY_CHUNKS: Final[str] = "EMPTY_CHUNKS"
CHUNK_JOIN: Final[str] = "\n\n"


@dataclass(frozen=True, slots=True)
class CanonicalChunk:
    """One nonempty source-ordered text segment."""

    ordinal: int
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def token_estimate(self) -> int:
        return int(ceil(self.char_count / 4))

    @property
    def preview(self) -> str:
        return self.text[:CHUNK_PREVIEW_MAX_CHARS]
```

Import these names into `profile_extraction.py`, `cv_document_extraction.py`, and `profile_activation.py`. Keep chunking, validation errors, source hashing, and persistence orchestration in their existing owners.

- [ ] **Step 4: Make the chunk repository the count/get owner**

Use SQL count in `attachment_text_chunks.py`:

```python
from sqlalchemy import delete, func, select


async def count_for_attachment(
    session: AsyncSession,
    attachment_id: str,
) -> int:
    stmt = (
        select(func.count())
        .select_from(AttachmentTextChunk)
        .where(AttachmentTextChunk.attachment_id == attachment_id)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())
```

Retain `get_by_attachment_ordinal()` in this repository. Remove `count_chunks_for_attachment()` and `get_chunk_by_ordinal()` from `repositories/observability.py`; update `services/observability.py` to call:

```python
total = await chunk_repo.count_for_attachment(session, attachment_id)
row = await chunk_repo.get_by_attachment_ordinal(
    session,
    attachment_id,
    ordinal,
)
```

- [ ] **Step 5: Run chunk, extraction, and observability tests**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_attachment_text_chunks.py tests/unit/test_profile_extraction.py tests/unit/test_cv_document_extraction.py tests/integration/test_profile_approval.py tests/integration/test_observability_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: chunk ordering/hash/preview/token semantics, zero-chunk errors, ordinal lookup, pagination, profile activation, and observability contracts all pass.

- [ ] **Step 6: Verify the backend import cycle is gone**

Run:

```powershell
rg -n "from app.services.profile_extraction import" backend/app/services/cv_document_extraction.py
rg -n "cv_chunk_contracts" backend/app/services/profile_extraction.py backend/app/services/cv_document_extraction.py backend/app/services/profile_activation.py
```

Expected: the first command exits 1; all three modules import the contract module.

- [ ] **Step 7: Commit the chunk consolidation**

```powershell
Set-Location ..
git add backend/app/services/cv_chunk_contracts.py backend/app/services/profile_extraction.py backend/app/services/cv_document_extraction.py backend/app/services/profile_activation.py backend/app/repositories/attachment_text_chunks.py backend/app/repositories/observability.py backend/app/services/observability.py backend/tests
git commit -m "refactor(backend): consolidate cv chunk contracts"
```

Expected: one commit with no response-schema or database migration changes.

### Task 4: Break the JD extraction DTO cycle

**Files:**
- Create: `backend/app/services/jd_extraction_contracts.py`
- Modify: `backend/app/services/jd_extraction.py:20-30,118-158,351-352,419-420`
- Modify: `backend/app/services/jd_extraction_guard.py:8`
- Test: `backend/tests/unit/test_jd_extraction.py`
- Test: `backend/tests/unit/test_jd_extraction_guard.py`

- [ ] **Step 1: Add a failing dependency-boundary assertion**

Add to `test_jd_extraction_guard.py`:

```python
from pathlib import Path


def test_guard_depends_on_contracts_not_extractor_runtime() -> None:
    source = Path("app/services/jd_extraction_guard.py").read_text(
        encoding="utf-8"
    )
    assert "app.services.jd_extraction_contracts" in source
    assert "from app.services.jd_extraction import" not in source
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction_guard.py::test_guard_depends_on_contracts_not_extractor_runtime -q
```

Expected: failure because the guard currently imports DTOs from `jd_extraction.py`.

- [ ] **Step 3: Move only the strict provider DTOs to a contract module**

Create `jd_extraction_contracts.py` with the existing complete models:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedJobSkillItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description=(
            "Concise semantic label for one atomic professional capability, "
            "supported by verbatim evidence; never invent an unsupported skill."
        )
    )
    confidence: float
    evidence: list[str] = Field(
        description=(
            "Short verbatim snippets copied from the retained JD source; "
            "never paraphrase."
        )
    )


class ExtractedJobPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None
    company: str | None
    summary: str
    responsibilities: list[str]
    required_skills: list[ExtractedJobSkillItem]
    preferred_skills: list[ExtractedJobSkillItem]
    seniority: Literal["intern", "junior", "mid", "senior", "lead", "unknown"]
    min_experience_years: float | None
    max_experience_years: float | None
    location: str | None
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"]
    extraction_confidence: float
```

Import both models into `jd_extraction.py` and `jd_extraction_guard.py`. Preserve re-exports from `jd_extraction.py` during this task so existing invokers/tests do not change API unnecessarily. Remove the lazy-import comment; the guard import can become a normal top-level import if its Plan 16 dependencies remain cycle-free.

- [ ] **Step 4: Run JD extraction/guard regressions and import checks**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_jd_extraction.py tests/unit/test_jd_extraction_guard.py tests/integration/test_job_ingestion.py tests/integration/test_job_reextraction.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: schema, one-repair, issue ordering, redaction, ingestion, and re-extraction tests pass; no lazy import is required.

- [ ] **Step 5: Commit the DTO boundary**

```powershell
Set-Location ..
git add backend/app/services/jd_extraction_contracts.py backend/app/services/jd_extraction.py backend/app/services/jd_extraction_guard.py backend/tests/unit/test_jd_extraction_guard.py
git commit -m "refactor(backend): isolate jd extraction contracts"
```

Expected: one contract-only commit with identical provider schema JSON.

### Task 5: Give Job embeddings one dependency-neutral owner

**Files:**
- Create: `backend/app/services/job_projection.py`
- Create: `backend/tests/unit/test_job_projection.py`
- Modify: `backend/app/services/jd_ingestion.py:95-107,402-415,682`
- Modify: `backend/app/services/job_reextraction.py:50-60,205-212`
- Modify imports only: `backend/app/services/job_evaluation.py`
- Modify imports only: `backend/app/services/matching.py`
- Modify imports only: `backend/app/services/saved_jobs.py`
- Modify imports only: `backend/app/tools/jobs.py`
- Modify imports only: `backend/app/tools/matching.py`
- Modify imports only: `backend/app/tools/registry.py`
- Test: `backend/tests/integration/test_job_ingestion.py`
- Test: `backend/tests/integration/test_job_reextraction.py`

- [ ] **Step 1: Add RED embedding-owner tests**

Create `backend/tests/unit/test_job_projection.py`:

```python
from __future__ import annotations

import inspect

import pytest

from app.schemas.embeddings import EmbeddingVectorError
from app.schemas.jobs import JobPostExtraction
from app.services import jd_ingestion, job_reextraction
from app.services.job_projection import EmbeddingClient, embed_job_extraction
from tests.fakes.embeddings import FakeEmbeddingClient
from tests.support.graph_rebuild import embedding_vector


def _extraction() -> JobPostExtraction:
    return JobPostExtraction(
        title="Synthetic role",
        company="Synthetic company",
        summary="Synthetic summary",
        responsibilities=[],
        required_skills=[],
        preferred_skills=[],
        seniority="unknown",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="unknown",
        extraction_confidence=0.8,
    )


def test_embed_job_extraction_returns_locked_finite_contract() -> None:
    client: EmbeddingClient = FakeEmbeddingClient(
        vector=embedding_vector(0.25)
    )
    vector, model, dimensions = embed_job_extraction(_extraction(), client)
    assert vector == embedding_vector(0.25)
    assert dimensions == 1536
    assert model


def test_embed_job_extraction_rejects_non_finite_vectors() -> None:
    client = FakeEmbeddingClient(vector=[float("nan")] * 1536)
    with pytest.raises(EmbeddingVectorError):
        embed_job_extraction(_extraction(), client)


@pytest.mark.parametrize("module", (jd_ingestion, job_reextraction))
def test_embedding_protocol_has_one_owner(module: object) -> None:
    assert "class EmbeddingClient" not in inspect.getsource(module)
```

- [ ] **Step 2: Run the new test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_projection.py -q
```

Expected: collection fails because `job_projection.py` does not exist.

- [ ] **Step 3: Create the canonical embedding contract**

Create `backend/app/services/job_projection.py`:

```python
"""Shared low-level Job embedding and post-commit projection mechanics."""

from __future__ import annotations

from typing import Protocol

from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    validate_finite_vector,
)
from app.schemas.jobs import JobPostExtraction
from app.services.embedding_text import build_job_embedding_text_v1


class EmbeddingClient(Protocol):
    """Minimal fake-testable embedding surface."""

    def embed_text(self, text: str) -> list[float]:
        """Return one locked finite embedding vector."""
        ...


def embed_job_extraction(
    extraction: JobPostExtraction,
    embedding_client: EmbeddingClient,
) -> tuple[list[float], str, int]:
    """Build and validate the locked Job embedding contract."""
    text = build_job_embedding_text_v1(extraction)
    vector = embedding_client.embed_text(text)
    validated = validate_finite_vector(vector)
    return validated, LOCKED_EMBEDDING_MODEL, LOCKED_EMBEDDING_DIMENSIONS


__all__ = ["EmbeddingClient", "embed_job_extraction"]
```

- [ ] **Step 4: Route both orchestrators through the shared helper**

In `jd_ingestion.py`, import the owner and retain the caller's quality policy:

```python
from app.services.job_projection import EmbeddingClient, embed_job_extraction


def _embed_if_scorable(
    extraction: JobPostExtraction,
    jd_quality: str,
    embedding_client: EmbeddingClient,
) -> tuple[list[float] | None, str | None, int | None]:
    if jd_quality not in _SCORABLE_QUALITIES:
        return None, None, None
    return embed_job_extraction(extraction, embedding_client)
```

In `job_reextraction.py`, delete `_embed_scorable` and replace its sole call
after the existing unscorable rejection with:

```python
embedding_json, embedding_model, embedding_dimensions = embed_job_extraction(
    extraction,
    embedder,
)
```

Import `EmbeddingClient` from `app.services.job_projection` in each listed
service/tool. Keep ingestion, re-extraction, error mapping, and all graph-sync
code otherwise unchanged in this task. Remove `EmbeddingClient` from
`jd_ingestion.__all__`; no internal caller may import it from the orchestrator.

- [ ] **Step 5: Run embedding consumers and static gates**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_projection.py tests/unit/test_job_evaluation.py tests/integration/test_job_ingestion.py tests/integration/test_job_reextraction.py tests/integration/test_match_jobs.py tests/integration/test_saved_jobs_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: all checks pass; unscorable ingestion still performs no embedding,
re-extraction still rejects unscorable output before CAS, and every internal
consumer imports the one protocol owner.

- [ ] **Step 6: Commit the embedding-owner refactor**

```powershell
Set-Location ..
git add backend/app/services/job_projection.py backend/app/services/jd_ingestion.py backend/app/services/job_reextraction.py backend/app/services/job_evaluation.py backend/app/services/matching.py backend/app/services/saved_jobs.py backend/app/tools backend/tests/unit/test_job_projection.py
git commit -m "refactor(backend): centralize job embedding contract"
```

Expected: one embedding-only refactor commit with no public result change.

### Task 6: Share post-commit Job sync mechanics without changing ingestion policy

**Files:**
- Modify: `backend/app/services/job_projection.py`
- Modify: `backend/tests/unit/test_job_projection.py`
- Modify: `backend/app/services/jd_ingestion.py:90,193-250,515-549,620-654`
- Test: `backend/tests/integration/test_job_ingestion.py`

- [ ] **Step 1: Add RED tests for the neutral sync result and exact projection inputs**

Extend `test_job_projection.py` with these imports and helpers:

```python
from typing import Any, cast

from app.core.time import utc_now
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_PROCESSING_STATUS_PROCESSED,
    JOB_SOURCE_TYPE_TEXT,
    JobPost,
)
from app.graph.sync_job import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
    JobSyncError,
)
from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
)
from app.services import job_projection
from app.services.job_projection import sync_persisted_job
from app.services.skill_normalization import SkillNormalizer
from tests.support.graph_rebuild import skills_fixture

JOB_ID = "11111111-1111-4111-8111-111111111111"


def _persisted_row() -> JobPost:
    now = utc_now()
    extraction = _extraction()
    return JobPost(
        id=JOB_ID,
        source_type=JOB_SOURCE_TYPE_TEXT,
        source_url=None,
        raw_content="Synthetic retained JD",
        raw_content_hash="synthetic-hash",
        extraction_json=extraction.model_dump(mode="json"),
        processing_status=JOB_PROCESSING_STATUS_PROCESSED,
        jd_quality=JOB_JD_QUALITY_FULL,
        failure_code=None,
        embedding_json=embedding_vector(0.35),
        embedding_model=LOCKED_EMBEDDING_MODEL,
        embedding_dimensions=LOCKED_EMBEDDING_DIMENSIONS,
        created_at=now,
        updated_at=now,
    )
```

Append the tests:

```python
@pytest.mark.asyncio
async def test_sync_persisted_job_skips_when_no_graph_seam_exists() -> None:
    result = await sync_persisted_job(
        _persisted_row(),
        normalizer=SkillNormalizer.from_path(skills_fixture()),
        graph_driver=None,
        job_sync_fn=None,
        log_context="test",
    )
    assert result.attempted is False
    assert result.ok is True
    assert result.code is None


@pytest.mark.asyncio
async def test_sync_persisted_job_passes_committed_row_to_sync_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def fake_sync(driver: Any, **kwargs: Any) -> None:
        seen["driver"] = driver
        seen.update(kwargs)

    monkeypatch.setattr(job_projection, "sync_job", fake_sync)
    driver = cast(AsyncGraphDriver, object())
    row = _persisted_row()
    result = await sync_persisted_job(
        row,
        normalizer=SkillNormalizer.from_path(skills_fixture()),
        graph_driver=driver,
        job_sync_fn=None,
        log_context="test",
    )
    assert result.attempted is True
    assert result.ok is True
    assert seen["driver"] is driver
    assert seen["job_id"] == JOB_ID
    assert seen["jd_quality"] == JOB_JD_QUALITY_FULL
    assert seen["embedding"] == row.embedding_json
    assert seen["source_updated_at"] == row.updated_at


@pytest.mark.asyncio
async def test_sync_persisted_job_maps_job_sync_error() -> None:
    async def fail_sync() -> None:
        raise JobSyncError("synthetic graph failure")

    result = await sync_persisted_job(
        _persisted_row(),
        normalizer=SkillNormalizer.from_path(skills_fixture()),
        graph_driver=None,
        job_sync_fn=fail_sync,
        log_context="test",
    )
    assert result.attempted is True
    assert result.ok is False
    assert result.code == NEO4J_SYNC_FAILED
    assert result.rebuild_instruction == NEO4J_REBUILD_INSTRUCTION
```

- [ ] **Step 2: Run the sync-helper tests to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_projection.py -q
```

Expected: collection fails because `sync_persisted_job` does not exist.

- [ ] **Step 3: Add the neutral post-commit sync helper**

Expand the module import header to this exact shape, retain the existing
embedding imports and helper below it, and replace the Task 5 `__all__` with
the final block shown at the end:

```python
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.db.models.jobs import JobPost
from app.graph.sync_job import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
    JobSyncError,
    sync_job,
)
from app.schemas.jobs import JobPostExtraction, parse_job_post_extraction
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)
JobSyncFn = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class JobProjectionSyncResult:
    attempted: bool
    ok: bool
    code: str | None
    rebuild_instruction: str | None


async def sync_persisted_job(
    row: JobPost,
    *,
    normalizer: SkillNormalizer,
    graph_driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
    log_context: str,
) -> JobProjectionSyncResult:
    if job_sync_fn is None and graph_driver is None:
        return JobProjectionSyncResult(False, True, None, None)
    if row.extraction_json is None or row.embedding_json is None:
        return JobProjectionSyncResult(
            True,
            False,
            NEO4J_SYNC_FAILED,
            NEO4J_REBUILD_INSTRUCTION,
        )

    extraction = parse_job_post_extraction(row.extraction_json)
    embedding = list(row.embedding_json)

    async def default_sync() -> None:
        if graph_driver is None:
            raise JobSyncError("Neo4j driver not configured for Job sync")
        await sync_job(
            graph_driver,
            job_id=row.id,
            extraction=extraction,
            jd_quality=str(row.jd_quality),
            embedding=embedding,
            source_updated_at=row.updated_at,
            normalizer=normalizer,
        )

    do_sync = job_sync_fn if job_sync_fn is not None else default_sync
    try:
        await do_sync()
    except JobSyncError as exc:
        logger.info(
            "%s neo4j sync failed job_id=%s code=%s",
            log_context,
            row.id,
            exc.code,
        )
        return JobProjectionSyncResult(
            True,
            False,
            exc.code,
            exc.rebuild_instruction,
        )
    except Exception:
        logger.info("%s neo4j sync failed job_id=%s", log_context, row.id)
        return JobProjectionSyncResult(
            True,
            False,
            NEO4J_SYNC_FAILED,
            NEO4J_REBUILD_INSTRUCTION,
        )
    return JobProjectionSyncResult(True, True, None, None)


__all__ = [
    "EmbeddingClient",
    "JobProjectionSyncResult",
    "JobSyncFn",
    "embed_job_extraction",
    "sync_persisted_job",
]
```

- [ ] **Step 4: Delegate only ingestion's low-level sync mechanics**

Keep `_is_scorable_processed` and replace `_maybe_sync_scorable_job` with this
policy-preserving adapter:

```python
async def _maybe_sync_scorable_job(
    row: JobPost,
    *,
    normalizer: SkillNormalizer,
    graph_driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
) -> tuple[bool | None, str | None, str | None]:
    if not _is_scorable_processed(row):
        return None, None, None
    projection = await sync_persisted_job(
        row,
        normalizer=normalizer,
        graph_driver=graph_driver,
        job_sync_fn=job_sync_fn,
        log_context="jd ingestion",
    )
    if not projection.attempted:
        return None, None, None
    return (
        projection.ok,
        projection.code,
        projection.rebuild_instruction,
    )
```

Import `JobSyncFn` and `sync_persisted_job` from `job_projection`; delete only
the duplicate parse/sync/error-handling body and local `JobSyncFn` alias. Keep
the existing public `JdIngestResult` mapping and exact duplicate/unscorable
call gates unchanged.

- [ ] **Step 5: Run ingestion policy and helper regressions**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_projection.py tests/integration/test_job_ingestion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: scorable commits sync after SQLite commit; no graph seam maps to
`sync_ok=None`; unscorable and exact-duplicate paths make zero graph calls;
graph failure preserves the processed row and rebuild guidance.

- [ ] **Step 6: Commit the ingestion sync delegation**

```powershell
Set-Location ..
git add backend/app/services/job_projection.py backend/app/services/jd_ingestion.py backend/tests/unit/test_job_projection.py
git commit -m "refactor(backend): share job sync mechanics"
```

Expected: one helper/ingestion commit with unchanged ingestion vocabulary.

### Task 7: Delegate re-extraction sync and finish protocol import migration

**Files:**
- Modify: `backend/tests/unit/test_job_projection.py`
- Modify: `backend/app/services/job_reextraction.py:50-82,280-325,430-455`
- Modify imports only: `backend/app/services/saved_jobs.py`
- Modify imports only: `backend/app/tools/jobs.py`
- Modify imports only: `backend/app/tools/registry.py`
- Test: `backend/tests/integration/test_job_reextraction.py`
- Test: `backend/tests/integration/test_saved_jobs_api.py`

- [ ] **Step 1: Add a failing single-sync-owner assertion**

Append to `test_job_projection.py`:

```python
@pytest.mark.parametrize("module", (jd_ingestion, job_reextraction))
def test_orchestrators_delegate_post_commit_sync(module: object) -> None:
    source = inspect.getsource(module)
    assert "sync_persisted_job" in source
    assert "await sync_job(" not in source
    assert "JobSyncFn = Callable" not in source
```

- [ ] **Step 2: Run the ownership test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_projection.py::test_orchestrators_delegate_post_commit_sync -q
```

Expected: the `job_reextraction` case fails because it still owns graph-sync
mechanics and a second `JobSyncFn` alias.

- [ ] **Step 3: Replace re-extraction's sync body with caller-specific mapping**

Import `EmbeddingClient`, `JobSyncFn`, and `sync_persisted_job` from
`job_projection`. Replace `_sync_committed` with:

```python
async def _sync_committed(
    row: JobPost,
    *,
    normalizer: SkillNormalizer,
    graph_driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
) -> tuple[bool, str | None, str | None]:
    projection = await sync_persisted_job(
        row,
        normalizer=normalizer,
        graph_driver=graph_driver,
        job_sync_fn=job_sync_fn,
        log_context="job reextraction",
    )
    return (
        projection.ok,
        projection.code,
        projection.rebuild_instruction,
    )
```

This intentionally maps a non-attempted SQLite-only projection to
`(True, None, None)`, preserving the existing re-extraction result contract.
Remove the local sync implementation, local `JobSyncFn` alias, and now-unused
graph parsing/error imports.

- [ ] **Step 4: Move remaining protocol imports to the neutral owner**

Apply these import shapes without changing call signatures:

```python
# saved_jobs.py
from app.services.job_projection import EmbeddingClient, JobSyncFn

# tools/jobs.py and tools/registry.py
from app.services.job_projection import EmbeddingClient, JobSyncFn
```

In `saved_jobs.py`, replace `ReextractJobSyncFn` with `JobSyncFn` and remove the
second alias import from `job_reextraction`. Keep `UrlFetcher`, ingestion
functions/errors, and re-extraction functions/errors in their existing owners.
Remove `JobSyncFn` from the two orchestrator `__all__` lists after the repository
search confirms every internal type import uses `job_projection`.

- [ ] **Step 5: Run re-extraction, saved-JD, and full projection regressions**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_job_projection.py tests/integration/test_job_ingestion.py tests/integration/test_job_reextraction.py tests/integration/test_saved_jobs_api.py tests/integration/test_job_tools.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: re-extraction remains same-ID and revision-CAS; no graph seam remains
SQLite-only success; graph failure is post-commit partial truth; evaluations
become stale but are never automatically recomputed.

- [ ] **Step 6: Commit the re-extraction sync delegation**

```powershell
Set-Location ..
git add backend/app/services/job_reextraction.py backend/app/services/saved_jobs.py backend/app/tools/jobs.py backend/app/tools/registry.py backend/tests/unit/test_job_projection.py
git commit -m "refactor(backend): delegate job reextraction sync"
```

Expected: one re-extraction/import commit with no route or response-schema diff.

### Task 8: Bind active-CV evidence to one attachment revision

**Files:**
- Modify: `backend/app/services/active_cv_reader.py:38-55,194-219,551-708`
- Modify: `backend/app/tools/active_cv.py:20-29,62-73,144-181`
- Test: `backend/tests/unit/test_active_cv_reader.py`
- Test: `backend/tests/integration/test_active_cv_tool.py`

- [ ] **Step 1: Add RED reader and tool race tests**

Add this unit test to `test_active_cv_reader.py`:

```python
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import active_cv_reader as reader


@pytest.mark.asyncio
async def test_initial_page_rejects_an_unexpected_active_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve_target(_: AsyncSession) -> Any:
        return reader._ActiveTarget(
            attachment_id="22222222-2222-4222-8222-222222222222",
            extraction_version="cv-document-v1",
            source_hash="new-source-hash",
            reprocess_required=False,
            document_json={"sections": []},
        )

    monkeypatch.setattr(reader, "_resolve_active_target", resolve_target)
    result = await reader.read_active_cv(
        cast(AsyncSession, object()),
        mode="chunk",
        chunk_ordinal=0,
        expected_identity=reader.ActiveCvIdentity(
            attachment_id="11111111-1111-4111-8111-111111111111",
            source_hash="old-source-hash",
        ),
    )
    assert result.ok is False
    assert result.code == reader.ERROR_ACTIVE_CV_CHANGED
    assert result.data is None
```

Add this behavioral race test to `test_active_cv_tool.py`:

```python
from app.services import active_cv_reader as active_cv_reader_service
from app.tools import active_cv as active_cv_tool_module


def test_no_active_snapshot_cannot_rebind_to_a_newly_active_cv(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_factory: Any,
) -> None:
    async def _body() -> None:
        async def direct_execute(**kwargs: Any) -> ToolResult:
            assert kwargs["source_attachment_id"] is None
            async with sqlite_factory() as session:
                await _seed_active(session)
            return await kwargs["invoke"]()

        monkeypatch.setattr(
            active_cv_tool_module,
            "execute_tool",
            direct_execute,
        )
        tool_fn = build_read_active_cv_tool(session_factory=sqlite_factory)
        result = await _ainvoke_read(
            tool_fn,
            run_id="11111111-1111-4111-8111-111111111111",
            tool_call_id="none-to-active-race",
            mode="chunk",
            chunk_ordinal=0,
        )
        assert result.ok is False
        assert result.code == ERROR_NO_ACTIVE_CV
        assert result.data is None

    run_async(_body())
```

The test intentionally activates a CV after tool preflight but before
`invoke`; current code incorrectly reads that new CV.

- [ ] **Step 2: Run the focused tests to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_active_cv_reader.py::test_initial_page_rejects_an_unexpected_active_revision tests/integration/test_active_cv_tool.py::test_no_active_snapshot_cannot_rebind_to_a_newly_active_cv -q
```

Expected: the unit test cannot import `ActiveCvIdentity`, and the race test
returns successful evidence from the newly activated CV.

- [ ] **Step 3: Define the internal attachment-plus-source-hash identity**

Add one public internal-service identity and one stable summary:

```python
ACTIVE_CV_CHANGED_SUMMARY: str = (
    "Active CV selection or revision changed; request a new page"
)


@dataclass(frozen=True, slots=True)
class ActiveCvIdentity:
    attachment_id: str
    source_hash: str


async def resolve_active_cv_identity(
    session: AsyncSession,
) -> ActiveCvIdentity | ToolResult:
    resolved = await _resolve_active_target(session)
    if isinstance(resolved, ToolResult):
        return resolved
    return ActiveCvIdentity(
        attachment_id=resolved.attachment_id,
        source_hash=resolved.source_hash,
    )
```

Use `ACTIVE_CV_CHANGED_SUMMARY` in `_bind_cursor`. Export the constant,
dataclass, and resolver in `__all__`; they remain Python-internal and do not
enter the LangChain tool schema.

- [ ] **Step 4: Guard the reader with the full expected revision**

Add the internal parameter and comparison with this exact diff; leave every
unshown validation, candidate, budget, and response line byte-for-byte intact:

```diff
 async def read_active_cv(
     session: AsyncSession,
     *,
     mode: str,
     section_id: str | None = None,
     query: str | None = None,
     chunk_ordinal: int | None = None,
     cursor: str | None = None,
     max_results: int = DEFAULT_MAX_RESULTS,
     max_chars: int = DEFAULT_MAX_CHARS,
+    expected_identity: ActiveCvIdentity | None = None,
 ) -> ToolResult:
@@
     resolved = await _resolve_active_target(session)
     if isinstance(resolved, ToolResult):
         return resolved
     target = resolved
+    actual_identity = ActiveCvIdentity(
+        attachment_id=target.attachment_id,
+        source_hash=target.source_hash,
+    )
+    if expected_identity is not None and actual_identity != expected_identity:
+        return _fail(ERROR_ACTIVE_CV_CHANGED, ACTIVE_CV_CHANGED_SUMMARY)
```

Do not expose either identity field as a caller argument and do not loosen the
existing cursor, result-count, or character bounds.

- [ ] **Step 5: Freeze no-active preflight and recheck a successful revision**

Remove `_resolve_active_attachment_id` and its direct profile-repository import
from the tool. Resolve once before `execute_tool`, capture a no-active failure,
and use a fresh session for the post-read check:

```python
async with factory() as session:
    identity_or_error = (
        await active_cv_reader_service.resolve_active_cv_identity(session)
    )

if isinstance(identity_or_error, ToolResult):
    identity = None
    preflight_error = identity_or_error
else:
    identity = identity_or_error
    preflight_error = None

owner = identity.attachment_id if identity is not None else None

async def _invoke() -> ToolResult:
    if preflight_error is not None:
        return preflight_error
    assert identity is not None
    try:
        async with factory() as session:
            result = await active_cv_reader_service.read_active_cv(
                session,
                mode=effective_mode,
                section_id=section_id,
                query=query,
                chunk_ordinal=chunk_ordinal,
                cursor=cursor,
                max_results=max_results,
                max_chars=max_chars,
                expected_identity=identity,
            )
        if not result.ok:
            return result
        async with factory() as session:
            current = (
                await active_cv_reader_service.resolve_active_cv_identity(
                    session
                )
            )
        if isinstance(current, ToolResult) or current != identity:
            return ToolResult(
                ok=False,
                code=active_cv_reader_service.ERROR_ACTIVE_CV_CHANGED,
                summary=(
                    active_cv_reader_service.ACTIVE_CV_CHANGED_SUMMARY
                ),
                data=None,
            )
        return result
    except Exception as exc:
        logger.info(
            "read_active_cv unexpected failure type=%s",
            type(exc).__name__,
        )
        return ToolResult(
            ok=False,
            code=ERROR_READ_ACTIVE_CV_FAILED,
            summary=(
                "Active CV read failed unexpectedly; retry later "
                "or reprocess the active document."
            ),
            data=None,
        )
```

Keep `source_attachment_id=owner` in `execute_tool`. A no-active snapshot can
now produce only its captured `NO_ACTIVE_CV` failure, while successful evidence
must match both the preflight and post-read `(attachment_id, source_hash)`.

- [ ] **Step 6: Add a post-read revision mismatch regression**

Add to `test_active_cv_tool.py` a fake-backed post-check test using the new
resolver twice:

```python
def test_success_is_rejected_when_revision_changes_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_factory: Any,
) -> None:
    async def _body() -> None:
        original = active_cv_reader_service.ActiveCvIdentity(
            attachment_id=_ATTACHMENT,
            source_hash=_SOURCE_HASH,
        )
        revised = active_cv_reader_service.ActiveCvIdentity(
            attachment_id=_ATTACHMENT,
            source_hash="revised-source-hash",
        )
        identities = iter((original, revised))

        async def resolve_identity(_: Any) -> Any:
            return next(identities)

        async def successful_read(_: Any, **kwargs: Any) -> ToolResult:
            assert kwargs["expected_identity"] == original
            return ToolResult(
                ok=True,
                code=None,
                summary="synthetic evidence",
                data={"attachment_id": _ATTACHMENT, "records": []},
            )

        async def direct_execute(**kwargs: Any) -> ToolResult:
            assert kwargs["source_attachment_id"] == _ATTACHMENT
            return await kwargs["invoke"]()

        monkeypatch.setattr(
            active_cv_reader_service,
            "resolve_active_cv_identity",
            resolve_identity,
        )
        monkeypatch.setattr(
            active_cv_reader_service,
            "read_active_cv",
            successful_read,
        )
        monkeypatch.setattr(
            active_cv_tool_module,
            "execute_tool",
            direct_execute,
        )
        tool_fn = build_read_active_cv_tool(session_factory=sqlite_factory)
        result = await _ainvoke_read(
            tool_fn,
            run_id="11111111-1111-4111-8111-111111111111",
            tool_call_id="revision-race",
            mode="chunk",
            chunk_ordinal=0,
        )
        assert result.ok is False
        assert result.code == active_cv_reader_service.ERROR_ACTIVE_CV_CHANGED
        assert result.data is None

    run_async(_body())
```

- [ ] **Step 7: Run active-CV and approval regressions**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_active_cv_reader.py tests/integration/test_active_cv_tool.py tests/integration/test_profile_approval.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: no-active-to-active, attachment switch, and same-attachment revision
change all fail closed; archived CVs remain inaccessible; bounds, pagination,
approval, and durable source ownership pass.

- [ ] **Step 8: Commit the revision-identity correction**

```powershell
Set-Location ..
git add backend/app/services/active_cv_reader.py backend/app/tools/active_cv.py backend/tests/unit/test_active_cv_reader.py backend/tests/integration/test_active_cv_tool.py
git commit -m "fix(backend): bind active cv evidence revision"
```

Expected: one focused correctness commit with no route/schema/migration change.

### Task 9: Reject embedded URL credentials at the existing URL boundary

**Files:**
- Modify: `backend/app/services/url_fetch.py:140-151`
- Test: `backend/tests/unit/test_url_fetch.py:92-113`
- Test: `backend/tests/integration/test_job_ingestion.py`

- [ ] **Step 1: Add credential-bearing URLs to the existing no-auth test matrix**

Extend the `test_unsupported_scheme_returns_paste_fallback` parameter list with these exact values:

```python
"https://user:secret@example.com/jd",
"http://user@example.com/jd",
```

The existing handler already raises if a request is attempted, so this test fails if validation lets either URL reach the transport.

- [ ] **Step 2: Run the URL test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_url_fetch.py::test_unsupported_scheme_returns_paste_fallback -q
```

Expected: the two new cases fail because scheme/netloc validation currently accepts embedded userinfo.

- [ ] **Step 3: Reject userinfo without adding network policy**

Update `validate_url_scheme` immediately after the `netloc` check:

```python
if not parsed.netloc:
    return URL_UNSUPPORTED_SCHEME
if parsed.username is not None or parsed.password is not None:
    return URL_UNSUPPORTED_SCHEME
```

Do not resolve DNS, inspect private IP ranges, follow redirects, add auth headers, or change the paste fallback. Those are separate out-of-scope security requirements.

- [ ] **Step 4: Run URL and ingestion regressions**

Run:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_url_fetch.py tests/integration/test_job_ingestion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: userinfo is never fetched; redirect refusal, no-cookie/no-auth behavior, response limits, MIME checks, URL fallback, and JD ingestion remain unchanged.

- [ ] **Step 5: Commit the URL boundary correction**

```powershell
Set-Location ..
git add backend/app/services/url_fetch.py backend/tests/unit/test_url_fetch.py backend/tests/integration/test_job_ingestion.py
git commit -m "fix(backend): reject url userinfo"
```

Expected: one narrow URL-validation commit.

### Task 10: Run the integrated backend gate and scope audit

**Files:**
- Validate: all files changed in Tasks 1-9

- [ ] **Step 1: Run full backend verification**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q
```

Expected: all commands exit 0 with candidate-specific counts.

- [ ] **Step 2: Verify removed duplication and cycles**

Run:

```powershell
rg -n "def _short_transaction|def _format_validated_sse|def _open_sse_response" app/services app/api -g '*.py'
rg -n "from app.services.profile_extraction import" app/services/cv_document_extraction.py
rg -n "from app.services.jd_extraction import" app/services/jd_extraction_guard.py
rg -n "def count_chunks_for_attachment|def get_chunk_by_ordinal" app/repositories/observability.py
rg -n "class EmbeddingClient|JobSyncFn = Callable|await sync_job\(" app/services/jd_ingestion.py app/services/job_reextraction.py
```

Expected: no matches. Canonical definitions exist only as `session_scope`,
`app.api.sse`, `cv_chunk_contracts`, `jd_extraction_contracts`,
`attachment_text_chunks`, and `job_projection` owners.

- [ ] **Step 3: Verify repository and product scope**

Run:

```powershell
Set-Location ..
git diff --check
git status --short
git diff --name-only HEAD~9..HEAD
git diff HEAD~9..HEAD -- backend/pyproject.toml backend/app/db/models backend/migrations frontend docs/plans docs/tasks
```

Expected: whitespace passes; exactly nine planned commits are present; manifests,
database models/migrations, frontend, Master/Plan/Task files are unchanged; the
pre-existing user edit in `Master_plan.md` is untouched. Status may additionally
show the four authorized plan artifacts when they were not committed before
execution; no other unplanned path may appear.

## Deferred findings requiring separate authorization

- Full private/loopback/link-local/DNS-rebinding SSRF protection changes the explicitly documented local URL-fetch boundary and requires a Master Plan amendment plus a dedicated threat model.
- CI workflows are explicitly out of scope in Master Plan Section 2.2.
- Backup/restore automation, request correlation, metrics, tracing, and public deployment hardening are separate operational features, not cleanup refactors.

## Deferred low-risk duplication register

These findings are real but intentionally not included in this batch because they are presentation/mapping cleanups with no demonstrated ownership bug:

- `_attachment_public` in `api/profile.py` and `services/cv_upload.py`; introduce a neutral DTO mapper only when a profile/upload contract changes.
- The retained-PDF iterator and headers in `api/profile.py` and `api/observability.py`; share only after an authorization-preserving stream helper has its own route tests.
- `record_from_row` wrappers in `repositories/job_evaluations.py`, `services/job_evaluation.py`, and `services/saved_jobs.py`; remove wrappers only after the service return types are stable.
- Repeated UTC coercion and graph scalar helpers; a common utility would touch schema/service boundaries for little current benefit.
