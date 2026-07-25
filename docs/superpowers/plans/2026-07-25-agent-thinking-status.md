# Agent Thinking Status Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the streaming assistant `…` placeholder with a durable, backend-driven, expandable Agent activity timeline rendered with Astryx.

**Architecture:** Real runner and tool boundaries write a safe `AgentActivity` projection before publishing the existing `assistant_status` and `tool_status` SSE events. Conversation history hydrates the same projection, the frontend reducer stores it on `ClientRun`, and one Astryx component renders running, interrupted, completed, failed, and disconnected states without workflow mappings in React.

**Tech Stack:** Python 3.11, FastAPI SSE, Pydantic 2, SQLAlchemy 2, Alembic, SQLite, LangGraph, React 19, TypeScript, Vite, Vitest, Testing Library, Astryx 0.1.4, Docker Compose, Chrome browser runtime.

---

## Scope and file map

This is one vertical feature, not independent products: persistence, transport,
history, reducer, and presentation must use one activity identity. Implement in
the order below so each commit has a testable contract.

**Create:**

- `backend/migrations/versions/0006_add_agent_activities.py` — structural table and indexes only.
- `backend/app/schemas/agent_activity.py` — canonical safe activity contract.
- `backend/app/repositories/agent_activities.py` — sequence allocation, upsert, transition, and ordered reads.
- `backend/app/services/agent_activity.py` — transaction boundary and legacy tool projection.
- `backend/tests/unit/test_agent_activity.py` — schema, transition, privacy, and label tests.
- `backend/tests/integration/test_agent_activities.py` — repository/service persistence tests.
- `frontend/src/features/chat/components/AgentActivityTimeline.tsx` — sole activity presentation owner.
- `frontend/src/features/chat/components/agent-activity.css` — token-based shimmer only.
- `frontend/src/test/agent-activity-timeline.test.tsx` — Astryx, disclosure, state, and accessibility tests.

**Modify:**

- `backend/app/db/models/chat.py`
- `backend/app/db/models/__init__.py`
- `backend/app/schemas/sse.py`
- `backend/app/schemas/chat.py`
- `backend/app/agent/runner.py`
- `backend/app/services/tool_execution.py`
- `backend/app/services/chat_turns.py`
- `backend/app/services/chat_history.py`
- `backend/app/api/dependencies.py`
- `backend/app/tools/active_cv.py`
- `backend/app/tools/jobs.py`
- `backend/app/tools/matching.py`
- `backend/app/tools/profile.py`
- `backend/tests/unit/test_chat_models.py`
- `backend/tests/unit/test_sse_contract.py`
- `backend/tests/integration/test_migrations.py`
- `backend/tests/integration/test_tool_replay.py`
- `backend/tests/integration/test_agent_runner.py`
- `backend/tests/integration/test_chat_history.py`
- `frontend/src/features/chat/types.ts`
- `frontend/src/features/chat/model.ts`
- `frontend/src/features/chat/history.ts`
- `frontend/src/features/chat/reducer.ts`
- `frontend/src/features/chat/ChatPage.tsx`
- `frontend/src/features/chat/components/ChatMessageRow.tsx`
- `frontend/src/features/chat/components/ChatMessages.tsx`
- `frontend/src/test/sse-reducer.test.ts`
- `frontend/src/test/chat-page.test.tsx`
- `frontend/src/test/match-card.test.tsx`
- `frontend/src/test/saved-job-card.test.tsx`

**Delete after callers move:**

- `frontend/src/features/chat/components/ChatToolActivity.tsx` — its visible tool list would duplicate the new timeline; result/card ownership remains on `ClientRun.tools`.

## Task 1: Reconfirm the clean baseline and Astryx public API

**Files:**

- Read: `frontend/AGENTS.md`
- Read: `frontend/package-lock.json`
- Read: `docs/superpowers/specs/2026-07-25-agent-thinking-status-design.md`
- No tracked files change.

- [x] **Step 1: Confirm branch and worktree scope**

Run from the repository root:

```powershell
git status --short --branch
git log -3 --oneline --decorate
```

Expected: the implementation branch/worktree is clean and contains spec commit
`c0b4888` or its descendant. Stop if unrelated tracked changes overlap the
files in this plan.

- [x] **Step 2: Restore exact frontend dependencies**

Run:

```powershell
Set-Location frontend
npm ci --no-audit --no-fund
```

Expected: exit `0`; Astryx core, CLI, and neutral theme resolve to `0.1.4`.

- [x] **Step 3: Read the exact Astryx contracts before UI edits**

Run:

```powershell
npx astryx build "streaming assistant status with expandable activity timeline" --detail compact
npx astryx search "chat message status collapsible tool activity motion" --detail compact
npx astryx component ChatMessage --detail compact
npx astryx component ChatToolCalls --detail compact
npx astryx component Collapsible --detail compact
npx astryx component StatusDot --detail compact
npx astryx docs motion --detail compact
npx astryx docs tokens --detail compact
```

Expected facts:

- `ChatMessage` accepts free-form assistant children.
- `Collapsible` accepts a ReactNode trigger and defaults open unless `defaultIsOpen={false}`.
- `StatusDot` requires `variant` and `label`; `isPulsing` respects reduced motion.
- continuous motion uses `--duration-slow*`; semantic colors and spacing use Astryx tokens.
- `ChatToolCalls` makes a single call inline but groups multiple calls. Because this feature requires the same disclosure for one or many mixed assistant/tool activities, use `Collapsible` plus Astryx stack/text/status primitives instead of nesting two disclosures.

- [x] **Step 4: Run focused baseline tests**

Run:

```powershell
Set-Location ..\backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_sse_contract.py tests/integration/test_agent_runner.py tests/integration/test_chat_history.py -q
Set-Location ..\frontend
npm run test -- --run src/test/sse-reducer.test.ts src/test/chat-page.test.tsx
```

Expected: both commands pass before feature changes. Record any pre-existing
failure instead of changing unrelated code.

## Task 2: Add the durable AgentActivity model and migration

**Files:**

- Create: `backend/migrations/versions/0006_add_agent_activities.py`
- Modify: `backend/app/db/models/chat.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/tests/unit/test_chat_models.py`
- Modify: `backend/tests/integration/test_migrations.py`

- [x] **Step 1: Write failing ORM contract tests**

Append focused assertions to `backend/tests/unit/test_chat_models.py`:

```python
from app.db.models.chat import AgentActivity


def test_agent_activity_table_contract() -> None:
    table = AgentActivity.__table__
    assert table.name == "agent_activities"
    assert set(table.columns) == {
        "id",
        "run_id",
        "sequence",
        "kind",
        "label",
        "technical_name",
        "status",
        "duration_ms",
        "error_code",
        "started_at",
        "updated_at",
        "completed_at",
    }
    assert table.c.run_id.foreign_keys
    fk = next(iter(table.c.run_id.foreign_keys))
    assert fk.target_fullname == "agent_runs.id"
    assert fk.ondelete == "CASCADE"


def test_agent_activity_has_run_sequence_uniqueness() -> None:
    names = {constraint.name for constraint in AgentActivity.__table__.constraints}
    assert "uq_agent_activities__run_sequence" in names
```

- [x] **Step 2: Write the failing migration test**

Add to `backend/tests/integration/test_migrations.py`:

```python
def test_migration_0006_adds_only_agent_activity_projection(
    isolated_sqlite: Path,
) -> None:
    command.upgrade(alembic_config(isolated_sqlite), "head")

    async def _body() -> None:
        engine = build_async_engine(isolated_sqlite)
        try:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text("PRAGMA foreign_key_list('agent_activities')")
                    )
                ).fetchall()
                assert any(
                    str(row[2]) == "agent_runs"
                    and str(row[3]) == "run_id"
                    and str(row[6] or "").upper() == "CASCADE"
                    for row in rows
                )
                version = (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                ).scalar_one()
                assert version == "0006_add_agent_activities"
        finally:
            await engine.dispose()

    run_async(_body())
```

- [x] **Step 3: Run tests to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_chat_models.py tests/integration/test_migrations.py -q
```

Expected: collection/import fails because `AgentActivity` and migration `0006`
do not exist.

- [x] **Step 4: Add the ORM model**

In `backend/app/db/models/chat.py`, add exact status/kind constants and the
model after `AgentRun` and before `ToolExecution`:

```python
AGENT_ACTIVITY_KIND_ASSISTANT = "assistant"
AGENT_ACTIVITY_KIND_TOOL = "tool"
AGENT_ACTIVITY_KINDS = frozenset(
    {AGENT_ACTIVITY_KIND_ASSISTANT, AGENT_ACTIVITY_KIND_TOOL}
)


class AgentActivity(Base):
    """Durable safe user-facing timeline projection for one Agent run."""

    __tablename__ = "agent_activities"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    technical_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id", "sequence", name="uq_agent_activities__run_sequence"
        ),
        CheckConstraint("sequence >= 0", name="sequence_non_negative"),
        CheckConstraint("label != ''", name="label_non_empty"),
        CheckConstraint(
            "technical_name IS NULL OR technical_name != ''",
            name="technical_name_non_empty",
        ),
        CheckConstraint(
            "kind IN ('assistant', 'tool')", name="kind"
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="status",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_non_negative",
        ),
        CheckConstraint(
            "status IN ('completed', 'failed') AND completed_at IS NOT NULL "
            "OR status NOT IN ('completed', 'failed') AND completed_at IS NULL",
            name="completed_at_coupling",
        ),
        CheckConstraint(
            "status = 'failed' AND error_code IS NOT NULL "
            "OR status != 'failed' AND error_code IS NULL",
            name="error_coupling",
        ),
        Index("ix_agent_activities__run_sequence", "run_id", "sequence"),
        Index("ix_agent_activities__run_status", "run_id", "status"),
    )
```

Update `backend/app/db/models/__init__.py` to import and export
`AgentActivity` beside the other chat models.

- [x] **Step 5: Create structural migration 0006**

Create `backend/migrations/versions/0006_add_agent_activities.py` with an
explicit `op.create_table` matching the ORM model, the two indexes above,
`down_revision = "0005_cv_profiles_multi_conversation"`, and:

```python
def downgrade() -> None:
    op.drop_index(
        "ix_agent_activities__run_status", table_name="agent_activities"
    )
    op.drop_index(
        "ix_agent_activities__run_sequence", table_name="agent_activities"
    )
    op.drop_table("agent_activities")
```

Do not import services, write backfill rows, touch checkpoint tables, or require
a destructive data reset. Existing runs legitimately begin with no assistant
activity history.

- [x] **Step 6: Run model and migration tests to verify GREEN**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_chat_models.py tests/integration/test_migrations.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/db/models migrations tests/unit/test_chat_models.py tests/integration/test_migrations.py --no-cache
```

Expected: both commands pass.

- [x] **Step 7: Commit the structural slice**

```powershell
git add backend/migrations/versions/0006_add_agent_activities.py backend/app/db/models/chat.py backend/app/db/models/__init__.py backend/tests/unit/test_chat_models.py backend/tests/integration/test_migrations.py
git commit -m "feat(backend): add durable agent activities"
```

## Task 3: Implement the canonical activity schema, repository, and service

**Files:**

- Create: `backend/app/schemas/agent_activity.py`
- Create: `backend/app/repositories/agent_activities.py`
- Create: `backend/app/services/agent_activity.py`
- Create: `backend/tests/unit/test_agent_activity.py`
- Create: `backend/tests/integration/test_agent_activities.py`

- [x] **Step 1: Write failing canonical-schema tests**

Create `backend/tests/unit/test_agent_activity.py` with tests that construct a
running assistant activity and reject unsafe terminal coupling:

```python
from datetime import UTC, datetime

import pytest
from app.core.ids import new_uuid
from app.schemas.agent_activity import AgentActivityPayload, humanize_activity_name
from pydantic import ValidationError

NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def _running_payload() -> dict[str, object]:
    return {
        "activity_id": new_uuid(),
        "run_id": new_uuid(),
        "sequence": 0,
        "kind": "assistant",
        "label": "Generating reply",
        "technical_name": "response_generation",
        "state": "running",
        "started_at": NOW,
        "updated_at": NOW,
        "completed_at": None,
        "duration_ms": None,
        "error_code": None,
    }


def test_activity_payload_accepts_safe_running_projection() -> None:
    activity = AgentActivityPayload.model_validate(_running_payload())
    assert activity.label == "Generating reply"
    assert activity.state == "running"


def test_activity_payload_rejects_failed_without_safe_code() -> None:
    payload = _running_payload() | {
        "state": "failed",
        "completed_at": NOW,
    }
    with pytest.raises(ValidationError, match="error_code"):
        AgentActivityPayload.model_validate(payload)


def test_activity_payload_forbids_unknown_or_raw_fields() -> None:
    with pytest.raises(ValidationError):
        AgentActivityPayload.model_validate(
            _running_payload() | {"arguments": {"cv_text": "forbidden"}}
        )


def test_humanize_activity_name_is_generic() -> None:
    assert humanize_activity_name("future_tool-name") == "Future Tool Name"
    assert humanize_activity_name("   ") == "Agent activity"
```

- [x] **Step 2: Write failing repository/service tests**

Create `backend/tests/integration/test_agent_activities.py`. Seed a conversation,
user message, and run with existing repository helpers, then assert:

```python
async def _exercise(factory: async_sessionmaker[AsyncSession], run_id: str) -> None:
    service = AgentActivityService(factory)
    assistant = await service.start_assistant(
        run_id=run_id,
        label="Generating reply",
        technical_name="response_generation",
    )
    tool = await service.record_tool(
        run_id=run_id,
        activity_id=new_uuid(),
        label="Search jobs",
        technical_name="query_jobs",
        state="running",
        duration_ms=None,
        error_code=None,
    )
    terminal = await service.finish(
        activity_id=assistant.activity_id,
        state="completed",
        duration_ms=25,
        error_code=None,
    )

    assert assistant.sequence == 0
    assert tool.sequence == 1
    assert terminal.activity_id == assistant.activity_id
    assert terminal.sequence == 0
    assert terminal.state == "completed"

    async with factory() as session:
        rows = await activity_repo.list_for_run_ids(session, [run_id])
    assert [row.id for row in rows] == [assistant.activity_id, tool.activity_id]
```

Add a second test that writes the same tool `activity_id` as `running` and then
`completed`, asserting one row remains and its sequence is unchanged. Add a
third test that deleting the owning run cascades all activity rows.

- [x] **Step 3: Run tests to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_activity.py tests/integration/test_agent_activities.py -q
```

Expected: import failure for the new schema/repository/service modules.

- [x] **Step 4: Create the canonical Pydantic contract**

Create `backend/app/schemas/agent_activity.py` with:

```python
from __future__ import annotations

import re
from typing import Any, Literal

from app.schemas.common import AwareUtcDatetime, StrictModelConfig, ToolStatus, UuidStr
from pydantic import BaseModel, Field, field_validator, model_validator

ActivityKind = Literal["assistant", "tool"]


def humanize_activity_name(value: str) -> str:
    words = re.sub(r"[_-]+", " ", value).strip()
    return words.title() if words else "Agent activity"


class AgentActivityPayload(BaseModel):
    model_config = StrictModelConfig

    activity_id: UuidStr
    run_id: UuidStr
    sequence: int = Field(ge=0)
    kind: ActivityKind
    label: str = Field(min_length=1, max_length=160)
    technical_name: str | None = Field(default=None, max_length=120)
    state: ToolStatus
    started_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    completed_at: AwareUtcDatetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=120)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("activity label must be non-empty")
        return cleaned

    @field_validator("technical_name")
    @classmethod
    def clean_technical_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("technical_name must be non-empty when provided")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def reject_sensitive_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden = {
                "arguments",
                "result",
                "prompt",
                "stack",
                "traceback",
                "cv_text",
                "raw_content",
                "provider_payload",
            }
            if forbidden.intersection(str(key).lower() for key in data):
                raise ValueError("activity payload contains forbidden fields")
        return data

    @model_validator(mode="after")
    def terminal_coupling(self) -> AgentActivityPayload:
        terminal = self.state in ("completed", "failed")
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal activity requires completed_at")
        if not terminal and self.duration_ms is not None:
            raise ValueError("non-terminal activity must not include duration_ms")
        if self.state == "failed":
            if self.error_code is None or not self.error_code.strip():
                raise ValueError("failed activity requires error_code")
        elif self.error_code is not None:
            raise ValueError("non-failed activity must not include error_code")
        return self
```

- [x] **Step 5: Implement repository transition ownership**

Create `backend/app/repositories/agent_activities.py` with public functions:

```python
async def get_by_id(session: AsyncSession, activity_id: str) -> AgentActivity | None:
    return await session.get(AgentActivity, activity_id)


async def list_for_run_ids(
    session: AsyncSession, run_ids: Sequence[str]
) -> list[AgentActivity]:
    if not run_ids:
        return []
    result = await session.scalars(
        select(AgentActivity)
        .where(AgentActivity.run_id.in_(list(dict.fromkeys(run_ids))))
        .order_by(AgentActivity.run_id, AgentActivity.sequence)
    )
    return list(result)


async def next_sequence(session: AsyncSession, run_id: str) -> int:
    value = await session.scalar(
        select(func.coalesce(func.max(AgentActivity.sequence), -1) + 1).where(
            AgentActivity.run_id == run_id
        )
    )
    return int(value or 0)
```

Add `create_activity(...)` that allocates `next_sequence`, inserts one row, and
flushes. Add `transition_activity(...)` that allows same-state replay,
`pending -> running|completed|failed`, and `running -> completed|failed`, but
rejects terminal regression. Terminal transitions set `completed_at=utc_now()`;
non-terminal rows keep it null. Never accept raw result or argument data.

Use these transition functions:

```python
_TERMINAL = frozenset({"completed", "failed"})
_ALLOWED = {
    "pending": frozenset({"running", "completed", "failed"}),
    "running": frozenset({"completed", "failed"}),
}


async def require_by_id(session: AsyncSession, activity_id: str) -> AgentActivity:
    row = await get_by_id(session, activity_id)
    if row is None:
        raise AgentActivityRepositoryError(
            f"agent activity {activity_id!r} not found"
        )
    return row


async def create_activity(
    session: AsyncSession,
    *,
    activity_id: str,
    run_id: str,
    kind: str,
    label: str,
    technical_name: str | None,
    state: str,
    duration_ms: int | None = None,
    error_code: str | None = None,
) -> AgentActivity:
    now = utc_now()
    row = AgentActivity(
        id=activity_id,
        run_id=run_id,
        sequence=await next_sequence(session, run_id),
        kind=kind,
        label=label.strip(),
        technical_name=(
            technical_name.strip() if technical_name is not None else None
        ),
        status=state,
        duration_ms=duration_ms,
        error_code=error_code,
        started_at=now,
        updated_at=now,
        completed_at=now if state in _TERMINAL else None,
    )
    session.add(row)
    await session.flush()
    return row


async def transition_activity(
    session: AsyncSession,
    row: AgentActivity,
    *,
    state: str,
    duration_ms: int | None,
    error_code: str | None,
) -> AgentActivity:
    if row.status == state:
        return row
    if row.status in _TERMINAL or state not in _ALLOWED.get(row.status, frozenset()):
        raise AgentActivityRepositoryError(
            f"invalid agent activity transition {row.status!r} -> {state!r}"
        )
    now = utc_now()
    row.status = state
    row.duration_ms = duration_ms
    row.error_code = error_code
    row.updated_at = now
    row.completed_at = now if state in _TERMINAL else None
    await session.flush()
    return row
```

- [x] **Step 6: Implement the transaction service**

Create `backend/app/services/agent_activity.py` with one
`AgentActivityService` class. Its constructor accepts an
`async_sessionmaker[AsyncSession]`. Implement:

```python
class AgentActivityService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def start_assistant(
        self, *, run_id: str, label: str, technical_name: str
    ) -> AgentActivityPayload:
        async with session_scope(self._factory) as session:
            row = await activity_repo.create_activity(
                session,
                activity_id=new_uuid(),
                run_id=run_id,
                kind="assistant",
                label=label,
                technical_name=technical_name,
                state="running",
            )
        return activity_payload(row)

    async def record_tool(
        self,
        *,
        run_id: str,
        activity_id: str,
        label: str,
        technical_name: str,
        state: ToolStatus,
        duration_ms: int | None,
        error_code: str | None,
    ) -> AgentActivityPayload:
        async with session_scope(self._factory) as session:
            row = await activity_repo.get_by_id(session, activity_id)
            if row is None:
                row = await activity_repo.create_activity(
                    session,
                    activity_id=activity_id,
                    run_id=run_id,
                    kind="tool",
                    label=label,
                    technical_name=technical_name,
                    state=state,
                    duration_ms=duration_ms,
                    error_code=error_code,
                )
            else:
                row = await activity_repo.transition_activity(
                    session,
                    row,
                    state=state,
                    duration_ms=duration_ms,
                    error_code=error_code,
                )
        return activity_payload(row)

    async def finish(
        self,
        *,
        activity_id: str,
        state: Literal["completed", "failed"],
        duration_ms: int,
        error_code: str | None,
    ) -> AgentActivityPayload:
        async with session_scope(self._factory) as session:
            row = await activity_repo.require_by_id(session, activity_id)
            row = await activity_repo.transition_activity(
                session,
                row,
                state=state,
                duration_ms=duration_ms,
                error_code=error_code,
            )
        return activity_payload(row)
```

Wrap SQLAlchemy/repository failures in `AgentActivityServiceError` with safe
messages. Add pure `activity_payload(row)` and `legacy_tool_activity_view(tool,
sequence)` helpers; the legacy helper uses `humanize_activity_name(tool.tool_name)`
and never exposes arguments or `ToolResult.data`.

The row serializer is the single field-name adapter:

```python
def activity_payload(row: AgentActivity) -> AgentActivityPayload:
    return AgentActivityPayload(
        activity_id=row.id,
        run_id=row.run_id,
        sequence=row.sequence,
        kind=row.kind,
        label=row.label,
        technical_name=row.technical_name,
        state=row.status,
        started_at=_as_aware_utc(row.started_at),
        updated_at=_as_aware_utc(row.updated_at),
        completed_at=_as_aware_utc(row.completed_at),
        duration_ms=row.duration_ms,
        error_code=row.error_code,
    )
```

- [x] **Step 7: Run focused tests and static checks**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_activity.py tests/integration/test_agent_activities.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/schemas/agent_activity.py app/repositories/agent_activities.py app/services/agent_activity.py tests/unit/test_agent_activity.py tests/integration/test_agent_activities.py --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: all pass.

- [x] **Step 8: Commit the activity service slice**

```powershell
git add backend/app/schemas/agent_activity.py backend/app/repositories/agent_activities.py backend/app/services/agent_activity.py backend/tests/unit/test_agent_activity.py backend/tests/integration/test_agent_activities.py
git commit -m "feat(backend): persist agent activity timeline"
```

## Task 4: Publish canonical activity through existing SSE events

**Files:**

- Modify: `backend/app/schemas/sse.py`
- Modify: `backend/app/services/tool_execution.py`
- Modify: `backend/app/agent/runner.py`
- Modify: `backend/app/services/chat_turns.py`
- Modify: `backend/app/api/dependencies.py`
- Modify: seven production tool call sites under `backend/app/tools/`
- Modify: `backend/tests/unit/test_sse_contract.py`
- Modify: `backend/tests/integration/test_tool_replay.py`
- Modify: `backend/tests/integration/test_agent_runner.py`

- [x] **Step 1: Write failing nested-activity SSE tests**

Add a helper in `backend/tests/unit/test_sse_contract.py` that returns a valid
activity dict. Update assistant/tool tests to require compatibility fields and
the nested projection:

```python
def _activity(run_id: str, *, state: str = "running") -> dict[str, Any]:
    terminal = state in {"completed", "failed"}
    return {
        "activity_id": new_uuid(),
        "run_id": run_id,
        "sequence": 0,
        "kind": "assistant",
        "label": "Generating reply",
        "technical_name": "response_generation",
        "state": state,
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "completed_at": utc_now() if terminal else None,
        "duration_ms": 1 if terminal else None,
        "error_code": "AGENT_FAILED" if state == "failed" else None,
    }


def test_assistant_status_preserves_message_and_nested_activity() -> None:
    run_id = new_uuid()
    event = parse_sse_event(
        {
            **_envelope(run_id=run_id),
            "event": "assistant_status",
            "payload": {
                "message": "Generating reply",
                "activity": _activity(run_id),
            },
        }
    )
    assert event.payload.message == event.payload.activity.label
```

Add a test that `activity` may be null for a degraded legacy-compatible event,
and a test that mismatched nested `run_id` is rejected.

- [x] **Step 2: Write failing runner publication tests**

In `backend/tests/integration/test_agent_runner.py`, inject a fake activity
service with `start_assistant`, `record_tool`, and `finish` methods. Assert the
direct-answer event order is:

```python
assert names == [
    "run_started",
    "assistant_status",
    "text_delta",
    "assistant_status",
    "run_completed",
]
assert events[1].payload.activity.state == "running"
assert events[-2].payload.activity.state == "completed"
```

For a tool call, assert every `tool_status` has a nested activity with the same
tool execution ID, technical name, exact status, and producer label. Add a
degraded fake that raises `AgentActivityServiceError`; the run must still emit
text and a terminal run event, with a safe warning captured by `caplog`.

- [x] **Step 3: Run tests to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_sse_contract.py tests/integration/test_agent_runner.py tests/integration/test_tool_replay.py -q
```

Expected: missing nested activity and missing producer label assertions fail.

- [x] **Step 4: Extend the SSE payloads compatibly**

In `backend/app/schemas/sse.py`, import `AgentActivityPayload`, add
`activity: AgentActivityPayload | None = None` to both
`AssistantStatusPayload` and `ToolStatusPayload`, and add validators requiring
`activity.run_id` to equal the envelope run ID. Perform the cross-field checks
in `AssistantStatusEvent` and `ToolStatusEvent` model validators so the envelope
run ID is available. An assistant activity must have `kind="assistant"` and
`payload.message == activity.label`. A tool activity must have `kind="tool"`,
`activity.activity_id == payload.tool_execution_id`,
`activity.technical_name == payload.tool_name`, and
`activity.state == payload.status`. Preserve all seven event names and every
existing field.

- [x] **Step 5: Give tool publications a backend-owned label**

In `backend/app/services/tool_execution.py`, add `display_label: str` to
`ToolStatusPublication`. Add optional `display_label: str | None = None` to
`execute_tool`; resolve it once with:

```python
resolved_display_label = (
    display_label.strip()
    if isinstance(display_label, str) and display_label.strip()
    else humanize_activity_name(tool_name)
)
```

Every `_publication(...)` call must carry `resolved_display_label`. Update the
seven production tool producers with explicit friendly labels:

```text
read_active_cv            -> Read active CV
save_job                  -> Save job
query_jobs                -> Search jobs
match_jobs                -> Rank matching jobs
propose_profile_from_cv   -> Analyze CV profile
propose_profile_update    -> Update CV profile
commit_profile_draft      -> Save CV profile
```

The technical name remains the exact registered tool name. Tests and synthetic
tools may omit the optional label and receive the generic backend fallback.

- [x] **Step 6: Record activity inside the runner before publication**

Add optional `activity_service: AgentActivityService | None = None` through
`stream_agent_run` and `_stream_agent_run_impl`. Implement a safe wrapper that
catches only `AgentActivityServiceError`, logs run/activity identity without
payload data, and returns null.

At run start, when `include_assistant_status` is true:

```python
assistant_activity = await _safe_start_assistant_activity(
    activity_service,
    run_id=run_id,
    label=assistant_status_message.strip(),
    technical_name="response_generation",
)
yield build_sse_event(
    "assistant_status",
    run_id,
    {
        "message": assistant_status_message.strip(),
        "activity": (
            assistant_activity.model_dump(mode="json")
            if assistant_activity is not None
            else None
        ),
    },
)
```

When consuming `ToolStatusPublication`, await `activity_service.record_tool`
before building `_tool_status_envelope`; include the returned nested activity
or null on the safe degraded path.

After durable terminal persistence succeeds, finish the assistant activity and
emit one last `assistant_status` update before `run_completed`, `run_failed`, or
the interrupted return. Use `completed` for completed/interrupted outcomes and
`failed` with the stable run error code for failures. Measure assistant duration
with `perf_counter()` from start; do not infer tool duration.

- [x] **Step 7: Inject the service in chat turns and enable production status**

In `stream_chat_turn` and `stream_resume`, construct
`AgentActivityService(factory)` and pass it to `stream_agent_run`. Keep direct
runner tests able to omit the service. In `backend/app/api/dependencies.py`, set
the production `ChatAgentDeps.include_assistant_status` value to `True` so the
waiting row always receives a real run-start activity.

- [x] **Step 8: Run focused backend tests**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_sse_contract.py tests/integration/test_agent_runner.py tests/integration/test_tool_replay.py tests/integration/test_chat_persistence.py tests/integration/test_interrupt_resume.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests/unit/test_sse_contract.py tests/integration/test_agent_runner.py tests/integration/test_tool_replay.py --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: all pass; no existing run/tool status alias changes.

- [x] **Step 9: Commit the SSE publication slice**

```powershell
git add backend/app/schemas/sse.py backend/app/services/tool_execution.py backend/app/agent/runner.py backend/app/services/chat_turns.py backend/app/api/dependencies.py backend/app/tools/active_cv.py backend/app/tools/jobs.py backend/app/tools/matching.py backend/app/tools/profile.py backend/tests/unit/test_sse_contract.py backend/tests/integration/test_tool_replay.py backend/tests/integration/test_agent_runner.py
git commit -m "feat(backend): stream real agent activity"
```

## Task 5: Hydrate ordered activity through conversation history

**Files:**

- Modify: `backend/app/schemas/chat.py`
- Modify: `backend/app/services/chat_history.py`
- Modify: `backend/tests/integration/test_chat_history.py`

- [x] **Step 1: Write failing history persistence tests**

In `backend/tests/integration/test_chat_history.py`, create a completed run with
one persisted assistant activity and one persisted tool activity. Assert:

```python
page = await get_history_page(
    session,
    conversation_id=CONVERSATION_ID,
    limit=50,
)
run = next(item.run for item in page.items if item.run is not None)
assert [activity.sequence for activity in run.activities] == [0, 1]
assert [activity.label for activity in run.activities] == [
    "Generating reply",
    "Search jobs",
]
assert run.activities[1].technical_name == "query_jobs"
```

Add a legacy test with a durable `ToolExecution` but no `AgentActivity`; history
must synthesize exactly one safe tool activity whose `activity_id` is the tool
execution ID, whose label is backend-humanized, and whose projection contains
no arguments or result data.

- [x] **Step 2: Run the history test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_chat_history.py -q
```

Expected: `AgentRunView` has no `activities` field.

- [x] **Step 3: Add activity to the public history schema**

In `backend/app/schemas/chat.py`, import `AgentActivityPayload` and add:

```python
class AgentRunView(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    user_message_id: UuidStr
    state: RunState
    pending_approval: JSONObject | None = None
    error_code: str | None = None
    completed_at: AwareUtcDatetime | None = None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    tool_executions: list[ToolExecutionView] = Field(default_factory=list)
    activities: list[AgentActivityPayload] = Field(default_factory=list)
```

Export the canonical activity type from the schema module only if existing
callers need it; do not duplicate its validation.

- [x] **Step 4: Hydrate stored and legacy activities**

In `_hydrate_items`, load all activity rows once with
`activity_repo.list_for_run_ids(session, run_ids)`. Group by run. In `_run_view`,
convert stored rows, then append fallback projections only for durable tools
whose execution IDs are absent from the stored activity IDs. Allocate fallback
sequence values after the highest stored sequence, sort fallback tools by
`(created_at, id)`, and return one ordered list.

Do not write fallback rows during a GET. Do not expose `arguments_summary_json`
or `result_json` in the activity projection.

- [x] **Step 5: Run history and API regression tests**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_chat_history.py tests/integration/test_chat_api.py tests/integration/test_conversations_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app/services/chat_history.py app/schemas/chat.py tests/integration/test_chat_history.py --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
```

Expected: all pass.

- [x] **Step 6: Commit the history slice**

```powershell
git add backend/app/schemas/chat.py backend/app/services/chat_history.py backend/tests/integration/test_chat_history.py
git commit -m "feat(backend): hydrate agent activity history"
```

## Task 6: Normalize SSE and history activity in the frontend reducer

**Files:**

- Modify: `frontend/src/features/chat/types.ts`
- Modify: `frontend/src/features/chat/model.ts`
- Modify: `frontend/src/features/chat/history.ts`
- Modify: `frontend/src/features/chat/reducer.ts`
- Modify: `frontend/src/test/sse-reducer.test.ts`

- [x] **Step 1: Write failing parser and reducer tests**

In `frontend/src/test/sse-reducer.test.ts`, define a canonical activity helper:

```typescript
function activity(
  overrides: Partial<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    activity_id: EVENT_F,
    run_id: RUN_ID,
    sequence: 0,
    kind: 'assistant',
    label: 'Generating reply',
    technical_name: 'response_generation',
    state: 'running',
    started_at: TS,
    updated_at: TS,
    completed_at: null,
    duration_ms: null,
    error_code: null,
    ...overrides,
  };
}
```

Add tests for:

- parsing nested assistant/tool activity and rejecting mismatched run IDs;
- `assistant_status` attaching activity to the streaming assistant run;
- duplicate event IDs being ignored;
- a newer `updated_at` replacing the same activity while an older update cannot;
- equal-time conflicting content keeping the existing record;
- `run_completed`, `run_failed`, and `approval_required` preserving activities;
- history hydration restoring activities and replacing stream-shaped terminal truth; and
- a legacy assistant status without nested activity creating a stream-only activity whose label is the backend `message`, not a frontend mapping.

- [x] **Step 2: Run frontend reducer tests to verify RED**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/test/sse-reducer.test.ts
```

Expected: missing activity types and `ClientRun.activities` failures.

- [x] **Step 3: Add wire types and strict parsing**

In `frontend/src/features/chat/types.ts`, add:

```typescript
export type AgentActivityKind = 'assistant' | 'tool';

export interface AgentActivityPayload {
  activity_id: string;
  run_id: string;
  sequence: number;
  kind: AgentActivityKind;
  label: string;
  technical_name: string | null;
  state: ToolStatus;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  error_code: string | null;
}
```

Add `activity: AgentActivityPayload | null` to both SSE payload interfaces and
`activities: AgentActivityPayload[]` to `AgentRunView`. Implement
`parseAgentActivity(raw, expectedRunId)` with UUID, integer, enum, non-empty,
UTC timestamp, terminal duration/error coupling, exact-key validation, and
run-ID matching. Reuse it in `parseSseEventData` and `parseHistoryPage`.

- [x] **Step 4: Add one client activity model**

In `frontend/src/features/chat/model.ts`, add:

```typescript
export interface ClientAgentActivity {
  activityId: string;
  runId: string;
  sequence: number;
  kind: 'assistant' | 'tool';
  label: string;
  technicalName: string | null;
  state: ToolStatus;
  startedAt: string;
  updatedAt: string;
  completedAt: string | null;
  durationMs: number | null;
  errorCode: string | null;
  source: 'stream' | 'history';
}
```

Add `activities: ClientAgentActivity[]` to `ClientRun` and every run
constructor in `reducer.ts`. Remove `assistantStatus` from `ChatState`, initial
state, and reset paths. Re-export `ClientAgentActivity` from `reducer.ts`
beside the other model types so presentation code has one import boundary.

- [x] **Step 5: Normalize history and SSE into the same model**

In `history.ts`, add `activityViewToClient` and map `run.activities`. In
`reducer.ts`, add:

```typescript
function upsertActivity(
  current: readonly ClientAgentActivity[],
  next: ClientAgentActivity,
): ClientAgentActivity[] {
  const index = current.findIndex(
    (activity) => activity.activityId === next.activityId,
  );
  if (index === -1) {
    return [...current, next].sort(
      (left, right) => left.sequence - right.sequence,
    );
  }
  const existing = current[index];
  if (existing.updatedAt >= next.updatedAt) {
    return [...current];
  }
  const copy = [...current];
  copy[index] = next;
  return copy.sort((left, right) => left.sequence - right.sequence);
}
```

For canonical nested activity, map and upsert it. For legacy
`assistant_status` with null activity, create a stream-only assistant activity
using `event_id`, the backend message, `technicalName: null`, and the event
timestamp. Do not humanize or map tool names in React. A legacy `tool_status`
without nested activity still updates `run.tools` but does not fabricate a
friendly timeline row.

Update durable rehydration to replace terminal `activities` together with
terminal `tools`.

- [x] **Step 6: Run reducer/history tests and typecheck**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/test/sse-reducer.test.ts
npm run typecheck
npm run lint
```

Expected: all pass.

- [x] **Step 7: Commit the frontend state slice**

```powershell
git add frontend/src/features/chat/types.ts frontend/src/features/chat/model.ts frontend/src/features/chat/history.ts frontend/src/features/chat/reducer.ts frontend/src/test/sse-reducer.test.ts
git commit -m "feat(frontend): normalize agent activities"
```

## Task 7: Build the Astryx activity timeline and replace the ellipsis

**Files:**

- Create: `frontend/src/features/chat/components/AgentActivityTimeline.tsx`
- Create: `frontend/src/features/chat/components/agent-activity.css`
- Create: `frontend/src/test/agent-activity-timeline.test.tsx`
- Modify: `frontend/src/features/chat/components/ChatMessageRow.tsx`
- Modify: `frontend/src/features/chat/components/ChatMessages.tsx`
- Modify: `frontend/src/features/chat/ChatPage.tsx`
- Delete: `frontend/src/features/chat/components/ChatToolActivity.tsx`
- Modify: `frontend/src/test/chat-page.test.tsx`
- Modify: `frontend/src/test/match-card.test.tsx`
- Modify: `frontend/src/test/saved-job-card.test.tsx`

- [x] **Step 1: Write failing component tests**

Create `frontend/src/test/agent-activity-timeline.test.tsx`, render through the
existing neutral Astryx `Theme`, and assert:

```typescript
it('shows backend label and expands friendly plus technical activity', async () => {
  const user = userEvent.setup();
  renderTimeline(runningRun());

  expect(screen.getByText('Rank matching jobs')).toBeInTheDocument();
  expect(screen.queryByText('match_jobs · running')).not.toBeInTheDocument();

  await user.click(screen.getByRole('button', {name: /Rank matching jobs/i}));

  expect(screen.getByText('Read active CV')).toBeInTheDocument();
  expect(screen.getByText('read_active_cv · completed')).toBeInTheDocument();
  expect(screen.getByText('match_jobs · running')).toBeInTheDocument();
});


it('renders completed, interrupted, failed, and disconnected summaries', () => {
  const {rerender} = renderTimeline(completedRun());
  expect(screen.getByText('Completed · 3 steps')).toBeInTheDocument();

  rerenderTimeline(rerender, interruptedRun(), 'idle');
  expect(screen.getByText('Waiting for your confirmation · 3 steps')).toBeInTheDocument();

  rerenderTimeline(rerender, failedRun(), 'failed');
  expect(screen.getByText('Unable to complete · 3 steps')).toBeInTheDocument();

  rerenderTimeline(rerender, runningRun(), 'disconnected');
  expect(
    screen.getByText('Connection lost — Agent may still be running'),
  ).toBeInTheDocument();
});
```

Also assert the running `StatusDot` has an accessible label, the current label
uses `aria-live="polite"`, the disclosure defaults closed, and no tool
arguments/results appear.

- [x] **Step 2: Run component tests to verify RED**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/test/agent-activity-timeline.test.tsx
```

Expected: module not found.

- [x] **Step 3: Implement the Astryx component**

Create `AgentActivityTimeline.tsx` using only documented public Astryx imports:

```typescript
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {HStack} from '@astryxdesign/core/HStack';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {ClientAgentActivity, ClientRun, StreamPhase} from '../reducer';
import './agent-activity.css';

const ACTIVITY_VARIANT = {
  pending: 'neutral',
  running: 'accent',
  completed: 'success',
  failed: 'error',
} as const;

function countLabel(count: number): string {
  return `${count} ${count === 1 ? 'step' : 'steps'}`;
}

function latestActivity(
  activities: readonly ClientAgentActivity[],
): ClientAgentActivity | null {
  const running = [...activities].reverse().find((item) => item.state === 'running');
  return running ?? activities.at(-1) ?? null;
}

function runSummary(run: ClientRun, streamPhase: StreamPhase): string {
  const count = countLabel(run.activities.length);
  if (streamPhase === 'disconnected' && run.state === 'running') {
    return 'Connection lost — Agent may still be running';
  }
  if (run.state === 'interrupted') {
    return `Waiting for your confirmation · ${count}`;
  }
  if (run.state === 'completed') {
    return `Completed · ${count}`;
  }
  if (run.state === 'failed') {
    return `Unable to complete · ${count}`;
  }
  return latestActivity(run.activities)?.label ?? 'Connecting…';
}

export function AgentActivityTimeline({
  run,
  streamPhase,
}: {
  run: ClientRun;
  streamPhase: StreamPhase;
}) {
  const summary = runSummary(run, streamPhase);
  const isRunning = run.state === 'running' && streamPhase !== 'disconnected';
  const trigger = (
    <VStack gap={0} width="100%">
      <HStack gap={1} align="center">
        <StatusDot
          variant={
            streamPhase === 'disconnected'
              ? 'warning'
              : run.state === 'failed'
                ? 'error'
                : run.state === 'completed'
                  ? 'success'
                  : run.state === 'interrupted'
                    ? 'warning'
                    : 'accent'
          }
          label={summary}
          isPulsing={isRunning}
        />
        <Text
          type="label"
          as="span"
          aria-live="polite"
          aria-atomic="true"
          className="jobagent-agent-activity-label"
          data-running={isRunning ? 'true' : 'false'}
        >
          {summary}
        </Text>
      </HStack>
      {run.activities.length > 0 ? (
        <Text type="supporting" color="secondary" as="span">
          {run.state === 'running'
            ? `View activity · ${countLabel(run.activities.length)}`
            : 'View activity'}
        </Text>
      ) : null}
    </VStack>
  );

  if (run.activities.length === 0) {
    return trigger;
  }

  return (
    <Collapsible trigger={trigger} defaultIsOpen={false}>
      <VStack gap={1} width="100%" data-testid="jobagent-agent-activity-list">
        {run.activities.map((activity) => (
          <HStack key={activity.activityId} gap={2} vAlign="start">
            <StatusDot
              variant={ACTIVITY_VARIANT[activity.state]}
              label={activity.state}
              isPulsing={activity.state === 'running' && isRunning}
            />
            <VStack gap={0} width="100%">
              <Text type="body">{activity.label}</Text>
              <Text type="supporting" color="secondary">
                {[activity.technicalName, activity.state]
                  .filter((value): value is string => Boolean(value))
                  .join(' · ')}
              </Text>
            </VStack>
          </HStack>
        ))}
      </VStack>
    </Collapsible>
  );
}
```

The `align` and `vAlign` props above are already proven in repository call
sites. Do not introduce raw layout elements.

- [x] **Step 4: Add token-only shimmer styling**

Create `agent-activity.css`:

```css
.jobagent-agent-activity-label[data-running='true'] {
  color: transparent;
  background-image: linear-gradient(
    90deg,
    var(--color-text-secondary),
    var(--color-text-primary),
    var(--color-text-secondary)
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  animation: jobagent-agent-thinking-shimmer var(--duration-slow-max) linear infinite;
}

@keyframes jobagent-agent-thinking-shimmer {
  to {
    background-position: -200% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .jobagent-agent-activity-label[data-running='true'] {
    color: var(--color-text-primary);
    background-image: none;
    animation: none;
  }
}
```

No raw color, spacing, radius, font, or duration values are allowed.

- [x] **Step 5: Project the durable run onto the assistant row**

In `ChatMessageRow.tsx`, add `activityRunForAssistantDisplay(messages, index)`.
It returns the assistant's own run during streaming, otherwise the immediately
preceding user run, and returns null if another assistant already owns that run
ID. Pass this run into `ChatMessageRow` as `activityRun`.

Use this exact projection boundary:

```typescript
export function activityRunForAssistantDisplay(
  messages: readonly ClientMessage[],
  index: number,
): ClientRun | null {
  const message = messages[index];
  if (!message || message.role !== 'assistant') {
    return null;
  }
  if (message.run) {
    return message.run;
  }
  let projected: ClientRun | null = null;
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const previous = messages[cursor];
    if (previous.role === 'assistant') {
      return null;
    }
    if (previous.role === 'user') {
      projected = previous.run;
      break;
    }
  }
  if (!projected) {
    return null;
  }
  const ownedElsewhere = messages.some(
    (candidate, candidateIndex) =>
      candidateIndex !== index &&
      candidate.role === 'assistant' &&
      candidate.run?.id === projected?.id,
  );
  return ownedElsewhere ? null : projected;
}
```

For assistant messages, render one ghost `ChatMessageBubble` containing a
`VStack` with `AgentActivityTimeline` first and `AssistantResponse` second when
content exists. For user messages, preserve the current filled bubble. Remove
the literal `…` branch and the separate `ChatToolActivity` rendering. Keep
`toolsForAssistantDisplay` unchanged for saved-job, match-card, approval, and
evidence ownership.

The assistant bubble body is:

```tsx
<ChatMessageBubble variant="ghost">
  <VStack gap={1} width="100%">
    {activityRun ? (
      <AgentActivityTimeline run={activityRun} streamPhase={streamPhase} />
    ) : message.isStreaming ? (
      <Text type="label" as="span" aria-live="polite">
        Connecting…
      </Text>
    ) : null}
    {message.content !== '' ? (
      <AssistantResponse
        content={message.content}
        isStreaming={message.isStreaming}
        evidence={activeCvEvidence}
      />
    ) : null}
  </VStack>
</ChatMessageBubble>
```

Render it when an assistant has content, is streaming, or has an activity run.
Remove the old standalone failed-run supporting text because the timeline owns
the safe failed summary. Preserve the generic malformed-interrupt notice only
when no validated approval card exists.

- [x] **Step 6: Remove the global assistant-status notice owner**

In `ChatMessages.tsx`, remove the `assistantStatus` prop and its system notice.
Pass `streamPhase` and the projected activity run into each row. Keep safe
pre-run HTTP/transport notices only when no run-backed assistant row exists.

In `ChatPage.tsx`, remove `state.assistantStatus` from `hasListContent` and the
`ChatMessages` props. Keep composer warnings and mutation locking unchanged.

Delete `ChatToolActivity.tsx` after `rg` confirms no production caller remains.
Move any still-needed generic duration/status helpers into
`AgentActivityTimeline.tsx`; remove workflow-specific `FRIENDLY_TOOL_LABELS`.
Update chat-page, match-card, and saved-job-card tests so they no longer import
or assert frontend tool-name mappings.

- [x] **Step 7: Run UI tests and static checks**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/test/agent-activity-timeline.test.tsx src/test/chat-page.test.tsx src/test/match-card.test.tsx src/test/saved-job-card.test.tsx
npm run typecheck
npm run lint
rg -n "FRIENDLY_TOOL_LABELS|assistantStatus|'…'|>…<" src/features/chat src/test
```

Expected: tests/typecheck/lint pass; `rg` finds no production ellipsis
placeholder, global assistant status owner, or workflow-specific label table.
Unrelated prose ellipses are acceptable only outside the replaced placeholder.

- [x] **Step 8: Commit the Astryx UI slice**

```powershell
git add frontend/src/features/chat/components/AgentActivityTimeline.tsx frontend/src/features/chat/components/agent-activity.css frontend/src/features/chat/components/ChatMessageRow.tsx frontend/src/features/chat/components/ChatMessages.tsx frontend/src/features/chat/ChatPage.tsx frontend/src/features/chat/components/ChatToolActivity.tsx frontend/src/test/agent-activity-timeline.test.tsx frontend/src/test/chat-page.test.tsx frontend/src/test/match-card.test.tsx frontend/src/test/saved-job-card.test.tsx
git commit -m "feat(frontend): show expandable agent activity"
```

## Task 8: Prove reload, interruption, disconnect, and privacy behavior

**Files:**

- Modify: `backend/tests/integration/test_chat_history.py`
- Modify: `backend/tests/integration/test_agent_runner.py`
- Modify: `frontend/src/test/sse-reducer.test.ts`
- Modify: `frontend/src/test/chat-page.test.tsx`

- [x] **Step 1: Add backend end-to-end contract assertions**

Extend the runner/history integration tests so one real fake-model turn with a
tool call proves:

```python
assert [event.event for event in events].count("assistant_status") == 2
assert all(
    event.payload.activity is not None
    for event in events
    if event.event in {"assistant_status", "tool_status"}
)

history = await get_history_page(
    session,
    conversation_id=CONVERSATION_ID,
    limit=50,
)
run = next(item.run for item in history.items if item.run is not None)
assert run.activities
assert all(activity.label for activity in run.activities)
assert_forbidden_keys_absent(
    history_page_as_dict(history),
    {"arguments", "provider_payload", "prompt", "traceback", "cv_text"},
)
```

Define `assert_forbidden_keys_absent` as a recursive dict/list key walker. It
must inspect keys only, not stringify or print user content.

- [x] **Step 2: Add frontend reload and conversation-switch assertions**

In `sse-reducer.test.ts`, stream running/completed activities, hydrate a
terminal history page, reset to another conversation, then reset back to the
original page. Assert the completed ordered activities return from history and
no stale activity from the other conversation survives.

In `chat-page.test.tsx`, assert a streamed activity replaces the ellipsis,
completion displays `Completed · N steps`, and remounting from history preserves
the disclosure and technical labels.

- [x] **Step 3: Add interruption/resume and disconnect assertions**

Test that `approval_required` renders `Waiting for your confirmation · N steps`
without pulsing, resume adds later activity to the same run, and
`stream/disconnected` renders `Connection lost — Agent may still be running`
without changing `run.state` from `running`.

- [x] **Step 4: Run the complete focused regression set**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_activity.py tests/unit/test_sse_contract.py tests/integration/test_agent_activities.py tests/integration/test_agent_runner.py tests/integration/test_tool_replay.py tests/integration/test_chat_history.py tests/integration/test_chat_persistence.py tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py -q
Set-Location ..\frontend
npm run test -- --run src/test/sse-reducer.test.ts src/test/agent-activity-timeline.test.tsx src/test/chat-page.test.tsx src/test/approval-card.test.tsx src/test/job-save-confirmation.test.tsx src/test/match-card.test.tsx src/test/saved-job-card.test.tsx src/test/active-cv-source.test.tsx
```

Expected: all pass.

- [x] **Step 5: Commit the cross-layer regressions**

```powershell
git add backend/tests/integration/test_chat_history.py backend/tests/integration/test_agent_runner.py frontend/src/test/sse-reducer.test.ts frontend/src/test/chat-page.test.tsx
git commit -m "test: cover durable agent activity states"
```

## Task 9: Run full gates, rebuild Docker, and test with the default browser

**Files:**

- No planned source changes. Fix only failures caused by this feature and commit
  each focused repair separately.

- [x] **Step 1: Run all backend gates**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m ruff check app migrations tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q
```

Expected: all pass. Existing dependency deprecation warnings may remain; no new
activity, migration, or SSE failures are allowed.

- [x] **Step 2: Run all frontend gates**

Run:

```powershell
Set-Location ..\frontend
npm run test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: all pass. The existing Vite chunk-size advisory may remain.

- [x] **Step 3: Verify repository hygiene**

Run from the repository root:

```powershell
Set-Location ..
git diff --check
git status --short
rg -n "FRIENDLY_TOOL_LABELS|assistantStatus|message\.content === '' && message\.isStreaming" frontend/src
```

Expected: no whitespace errors, no unexpected tracked changes, and no old
placeholder/status owner.

- [x] **Step 4: Rebuild the existing disposable Compose project without deleting volumes**

Run:

```powershell
$project = 'jobagent-cv-profile-reset-smoke'
if ($project -ne 'jobagent-cv-profile-reset-smoke') { throw 'Unexpected Compose project' }
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project up -d --build
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project ps
```

Expected: frontend, backend, and Neo4j become healthy. Do not run `down -v`;
migration `0006` is additive and must preserve current application data.

- [x] **Step 5: Test the real waiting experience in the default browser**

Use `browser:control-in-app-browser` with the runtime default browser, or the
current Chrome binding when it is the selected default. Open
`http://localhost:5173/` and use an existing ready profile. If no ready profile
exists, upload only a synthetic fixture from
`backend/tests/fixtures/cv/digital_cv_01.pdf` through the app.

Send a prompt that invokes real tools, then verify visible DOM and screenshots:

1. The assistant waiting row never renders the literal `…`.
2. The running row shows a backend label and pulsing Astryx status.
3. Opening the disclosure shows friendly labels, technical names, and exact states.
4. Completion stops animation and shows `Completed · N steps` above the answer.
5. Reloading preserves the completed timeline and its ordering.
6. Switching to another conversation and back restores the same timeline.
7. Reloading during a long run reports disconnect/running truth and never false completion.

Do not inspect cookies, local storage, credentials, raw CV text, provider
payloads, or database paths. Keep the final app tab as a browser handoff.

- [x] **Step 6: Inspect container logs only for feature errors**

Run bounded log reads:

```powershell
$project = 'jobagent-cv-profile-reset-smoke'
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project logs --tail 200 backend
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project logs --tail 100 frontend
```

Expected: no activity migration, schema validation, SSE framing, or frontend
runtime errors. Never print `.env` or provider payloads.

- [x] **Step 7: Final review and evidence summary**

Run:

```powershell
git log --oneline --decorate --max-count=12
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Review every changed file against the approved spec. Report exact commands,
pass/fail results, browser scenarios, known non-blocking warnings, and any
skipped check. Do not claim completion until fresh output from all required
gates and browser acceptance has been inspected.
