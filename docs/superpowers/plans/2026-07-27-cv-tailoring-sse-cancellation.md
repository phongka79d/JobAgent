# CV Tailoring SSE Cancellation Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure an SSE disconnect durably terminates the active CV-tailoring session/run so later “Tạo CV theo JD” requests are not blocked by orphaned `generating` state.

**Architecture:** Keep the existing API, coordinator, activity gate, and frontend contracts unchanged. Reproduce cancellation at the ASGI response boundary, then shield only the coordinator's terminal persistence and exact checkpoint cleanup by reusing the established chat-runner `CancelScope(shield=True)` pattern.

**Tech Stack:** Python 3.13, FastAPI SSE, AnyIO cancellation scopes, SQLAlchemy async sessions, LangGraph SQLite checkpoints, Pytest.

---

## File Map

- Modify `backend/tests/integration/test_cv_tailoring_coordinator.py`: own the real ASGI-disconnect regression and durable session/run assertions.
- Modify `backend/app/services/cv_tailoring.py`: own shielded cancellation finalization for tailoring generations.
- Read-only reference `backend/app/agent/runner.py`: existing cancellation-shield pattern; do not modify.
- Read-only reference `backend/app/api/sse.py`: existing response/iterator closing owner; do not modify.

### Task 1: Reproduce ASGI disconnect leaving tailoring state active

**Files:**
- Modify: `backend/tests/integration/test_cv_tailoring_coordinator.py:1-35`
- Modify: `backend/tests/integration/test_cv_tailoring_coordinator.py:463-503`
- Test: `backend/tests/integration/test_cv_tailoring_coordinator.py`

- [ ] **Step 1: Add the disconnect-boundary test imports**

Add these imports alongside the existing third-party and application imports:

```python
import anyio
import pytest
from app.api.sse import open_sse_response
from app.services.activity_gate import assert_profile_idle
from fastapi import HTTPException
```

Keep the existing imports and let Ruff order the application/third-party groups.

- [ ] **Step 2: Write the failing ASGI disconnect regression**

Add this test immediately after
`test_closing_after_primed_run_started_fails_durable_generation`:

```python
def test_asgi_disconnect_durably_fails_active_tailoring_generation(
    db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _body() -> None:
        from app.services.cv_tailoring import TailoringCoordinator

        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            profile_id, document, profile_model = await _seed_ready_source(factory)
            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=TailoringArtifactStorage(tmp_path / "files"),
                settings=_Settings(),
                invoker=_Invoker(_patch_for_summary(document, profile_model)),
                sqlite_path=db_path,
                compiler=_fake_compile,
            )
            launch = await coordinator.prepare_session(
                profile_id=profile_id,
                job_id=None,
                instruction="Tailor the summary",
                parent_run_id=None,
            )
            generation_started = anyio.Event()
            delete_observations: list[tuple[str, str]] = []

            async def block_generation(_prepared: Any):
                generation_started.set()
                await anyio.sleep_forever()

            original_delete = coordinator._delete_checkpoint

            async def observe_delete(run_id: str) -> None:
                async with factory() as session:
                    owner = await session.get(CVTailoringSession, launch.session_id)
                    run = await session.get(AgentRun, launch.run_id)
                    assert owner is not None and run is not None
                    delete_observations.append((owner.state, run.state))
                await original_delete(run_id)

            monkeypatch.setattr(coordinator, "_generation_context", block_generation)
            monkeypatch.setattr(coordinator, "_delete_checkpoint", observe_delete)
            response = await open_sse_response(
                coordinator.stream_initial_version(launch),
                error_mapper=lambda _exc: HTTPException(status_code=400),
            )

            async def send(_message: dict[str, object]) -> None:
                return

            async def receive() -> dict[str, str]:
                await generation_started.wait()
                return {"type": "http.disconnect"}

            await response(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.3"},
                },
                receive,
                send,
            )

            async with factory() as session:
                owner = await session.get(CVTailoringSession, launch.session_id)
                run = await session.get(AgentRun, launch.run_id)
                assert owner is not None and owner.state == "failed"
                assert owner.error_code == "TAILORING_GROUNDING_FAILED"
                assert run is not None and run.state == "failed"
                assert run.error_code == "TAILORING_GROUNDING_FAILED"
                await assert_profile_idle(session, profile_id=profile_id)
            assert delete_observations == [("failed", "failed")]
        finally:
            await engine.dispose()

    run_async(_body())
```

- [ ] **Step 3: Run the new test and verify RED**

Run from `backend/`:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_cv_tailoring_coordinator.py::test_asgi_disconnect_durably_fails_active_tailoring_generation -q
```

Expected: FAIL because the session remains `generating` or the run remains
`running`; `delete_observations` must not falsely report terminal persistence.

- [ ] **Step 4: Commit the regression test**

```powershell
git add tests/integration/test_cv_tailoring_coordinator.py
git commit -m "test(cv-tailoring): reproduce cancelled SSE orphan"
```

### Task 2: Shield tailoring cancellation finalization

**Files:**
- Modify: `backend/app/services/cv_tailoring.py:5-12`
- Modify: `backend/app/services/cv_tailoring.py:334-339`
- Test: `backend/tests/integration/test_cv_tailoring_coordinator.py`

- [ ] **Step 1: Import the established cancellation primitive**

Add this import before the SQLAlchemy imports:

```python
from anyio import CancelScope
```

- [ ] **Step 2: Implement the minimal shielded cleanup**

Replace only the cancellation handler in `stream_initial_version` with:

```python
        except (asyncio.CancelledError, GeneratorExit):
            with CancelScope(shield=True):
                if await self._fail_generation(
                    prepared, TAILORING_GROUNDING_FAILED
                ):
                    await self._delete_checkpoint(launch.run_id)
            raise
```

Do not shield normal generation, change `_fail_generation`, swallow the
original cancellation, or alter error/status mapping.

- [ ] **Step 3: Run the new test and verify GREEN**

Run from `backend/`:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_cv_tailoring_coordinator.py::test_asgi_disconnect_durably_fails_active_tailoring_generation -q
```

Expected: PASS; the session/run are both `failed`, the gate is idle, and
checkpoint deletion observes terminal rows.

- [ ] **Step 4: Run the focused cancellation and tailoring suites**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_api_sse.py tests/integration/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/services/cv_tailoring.py tests/integration/test_cv_tailoring_coordinator.py --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: all commands exit 0 with no failures or diagnostics.

- [ ] **Step 5: Commit the production fix**

```powershell
git add app/services/cv_tailoring.py
git commit -m "fix(cv-tailoring): finalize cancelled SSE generation"
```

### Task 3: Validate broadly and repair the current orphan safely

**Files:**
- No tracked file changes expected.
- Runtime scope: the single observed `generating` initial tailoring session and
  its `running` tailoring run only.

- [ ] **Step 1: Run the full backend verification gates**

Run from `backend/`:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git diff --check
git status --short --branch
```

Expected: Pytest, Ruff, Mypy, and `git diff --check` exit 0. Status contains no
uncommitted implementation files.

- [ ] **Step 2: Rebuild only the backend container**

Run from the repository root:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build backend
docker compose --env-file .env -f infrastructure/docker-compose.yml ps backend
```

Expected: the backend container is `Up` and healthy; the frontend and named
data volume are preserved.

- [ ] **Step 3: Repair exactly one observed orphan through repository transitions**

Run this bounded application script from the repository root. It aborts without
mutation unless exactly one initial tailoring session/run pair is still active,
uses repository state transitions in one transaction, and deletes only that
run's checkpoint after commit:

```powershell
@'
import asyncio

from sqlalchemy import select

from app.agent.checkpoint import delete_run_checkpoint, open_checkpointer
from app.core.settings import get_settings
from app.db.models.chat import AgentRun
from app.db.models.cv_tailoring import CVTailoringSession
from app.db.session import get_session_factory, session_scope
from app.repositories import agent_runs as runs_repo
from app.repositories import cv_tailoring as tailoring_repo

ERROR_CODE = "TAILORING_GROUNDING_FAILED"


async def main() -> None:
    factory = get_session_factory()
    statement = (
        select(CVTailoringSession, AgentRun)
        .join(AgentRun, AgentRun.tailoring_session_id == CVTailoringSession.id)
        .where(
            CVTailoringSession.state == "generating",
            CVTailoringSession.latest_version_number == 0,
            AgentRun.run_kind == "cv_tailoring",
            AgentRun.state == "running",
        )
    )
    async with factory() as session:
        rows = list((await session.execute(statement)).all())
    if len(rows) != 1:
        raise SystemExit(f"expected exactly one orphaned pair; found {len(rows)}")
    session_id = rows[0][0].id
    run_id = rows[0][1].id
    async with session_scope(factory) as session:
        await tailoring_repo.mark_session_failed(
            session, session_id, error_code=ERROR_CODE
        )
        await runs_repo.fail_run(session, run_id, error_code=ERROR_CODE)
    async with open_checkpointer(settings=get_settings()) as saver:
        await delete_run_checkpoint(saver, run_id)
    print("repaired exactly one orphaned tailoring generation")


asyncio.run(main())
'@ | docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -
```

Expected: prints `repaired exactly one orphaned tailoring generation`. If the
count is not exactly one, stop and inspect state; do not broaden the query or
edit SQLite directly.

- [ ] **Step 4: Verify the activity gate and browser workflow**

First query only safe session state fields and confirm there is no
`generating` session. Then use Chrome at `http://localhost:5173`, select a
processed full/partial JD, click **Tạo CV theo JD** once, and verify:

- the POST no longer returns `TAILORING_START_BLOCKED`;
- the button remains locked while the stream is active;
- terminal success opens the tailored-CV editor, or a truthful terminal failure
  leaves no `generating`/`running` orphan;
- a second create is not blocked after the first request reaches terminal state;
- no console error, raw CV/JD, path, or secret is exposed.

- [ ] **Step 5: Record final repository evidence**

```powershell
git log -3 --oneline --decorate
git status --short --branch
git diff --check HEAD~2..HEAD
```

Expected: the regression-test and production-fix commits are present, the
working tree is clean, and diff checking reports no whitespace errors.
