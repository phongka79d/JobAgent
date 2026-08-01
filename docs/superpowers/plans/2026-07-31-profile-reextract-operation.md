# Durable Profile Re-extraction Operation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make direct CV re-extraction a durable, profile-owned, recoverable operation that is serialized with uploads and can be safely released with a rehearsed SQLite-volume migration.

**Architecture:** Migration `0008_profile_reextract_ownership` introduces an operation row and profile-scoped draft ownership. A pure document-first staging function produces in-memory artifacts without a database session; a coordinator claims, publishes, recovers, and consumes those artifacts through short SQLite compare-and-swap transactions. The React CV Manager owns typed operation recovery while `App` applies its lock to both upload entry points.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async with SQLite, Alembic, AnyIO, React 19, TypeScript, Vitest, Docker Compose, PowerShell.

**Execution authority:** User-approved on 2026-07-31. This detailed plan is the execution authority for this increment; do not create or require a separate `docs/plans/Plan_18.md`.

---

## File Structure

- `backend/migrations/versions/0008_profile_reextract_ownership.py`: guarded SQLite table rebuild and operation schema.
- `backend/tests/support/db_migration.py`, `backend/tests/integration/test_migrations.py`, `backend/tests/integration/test_database_contract.py`, `backend/tests/integration/test_compose_runtime.py`: migration-head and Compose migration evidence.
- `backend/app/db/models/profiles.py`: `ProfileReextractOperation` and structural draft fields.
- `backend/app/repositories/profile_reextract_operations.py`: claim, state CAS, recovery lookup, and atomic operation consumption.
- `backend/app/repositories/profiles.py`: profile-scoped draft reads, writes, and deletes only.
- `backend/app/services/profile_drafts.py`: pure stage result plus atomic initial-upload and re-extraction publication boundaries.
- `backend/app/services/profile_reextraction.py`: durable direct-operation orchestration, cancellation finalization, review reconciliation, approval, and discard.
- `backend/app/services/profile_approval.py`: operation-aware approval CAS inside the existing SQLite-first approval transaction.
- `backend/app/services/cv_upload.py`, `backend/app/services/activity_gate.py`, `backend/app/services/cv_manager_projection.py`, `backend/app/services/profile_deletion.py`, `backend/app/main.py`: immediate-write upload gate, authoritative locks, action projection, cleanup, and startup recovery.
- `backend/app/schemas/profile_reextraction.py`, `backend/app/schemas/profile.py`, `backend/app/api/profiles.py`, `backend/app/api/profile.py`: strict lifecycle transport and correlated profile projection.
- `frontend/src/features/cv-manager/api.ts`, `frontend/src/features/cv-manager/types.ts`, `frontend/src/features/cv-manager/state.ts`, `frontend/src/features/cv-manager/ProfileReextractReview.tsx`, `frontend/src/features/cv-manager/CvManagerDrawer.tsx`: parsed operation API, recovery state, and review controls.
- `frontend/src/app/App.tsx`, `frontend/src/features/profile/CvSidebar.tsx`, `frontend/src/features/profile/ProfileOverviewPanel.tsx`, `frontend/src/features/chat/ChatPage.tsx`: shared dual-upload lock and in-place 409 action.
- `infrastructure/scripts/app_data_snapshot.ps1`, `infrastructure/scripts/test_app_data_snapshot.ps1`, `backend/app/services/profile_reextract_migration_smoke.py`, `docs/operations/profile-reextract-release.md`: fail-closed volume utility, utility checks, clone smoke verification, and release/rollback commands.

### Task 1: Add guarded operation schema and migration evidence

**Files:**
- Create: `backend/migrations/versions/0008_profile_reextract_ownership.py`
- Modify: `backend/app/db/models/profiles.py`
- Modify: `backend/app/db/seed.py`
- Modify: `backend/tests/support/db_migration.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Modify: `backend/tests/integration/test_database_contract.py`
- Modify: `backend/tests/integration/test_compose_runtime.py`

- [x] **Step 1: Write the failing migration and schema tests.**

```python
def test_0008_rejects_ambiguous_drafts_before_schema_mutation(legacy_db: Path) -> None:
    before = sqlite_schema_snapshot(legacy_db)
    execute_sql(legacy_db, "INSERT INTO profile_drafts VALUES ('d2', NULL, NULL, '{}', '2026-07-31T00:00:00Z', '2026-07-31T00:00:00Z')")
    with pytest.raises(CommandError, match="profile_drafts.target_profile_id"):
        upgrade_database(legacy_db, "0008_profile_reextract_ownership")
    assert sqlite_schema_snapshot(legacy_db) == before


def test_operation_schema_has_exact_constraints(migrated_sqlite: Path) -> None:
    schema = sqlite_schema_snapshot(migrated_sqlite)
    assert "reextract_operation_id" in schema.table_info["profile_drafts"]
    assert schema.foreign_keys["profile_drafts"]["reextract_operation_id"].on_delete == "RESTRICT"
    assert schema.index_sql["uq_profile_reextract_operations_actionable"] == (
        "CREATE UNIQUE INDEX uq_profile_reextract_operations_actionable "
        "ON profile_reextract_operations (profile_id) "
        "WHERE state IN ('running', 'review_ready')"
    )

def test_0008_is_the_migration_head() -> None:
    assert MIGRATION_HEAD == "0008_profile_reextract_ownership"
    assert revision_head() == "0008_profile_reextract_ownership"
```

- [x] **Step 2: Run the migration tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_migrations.py::test_0008_rejects_ambiguous_drafts_before_schema_mutation tests/integration/test_database_contract.py::test_operation_schema_has_exact_constraints -q`

Expected: FAIL because revision `0008_profile_reextract_ownership`, `profile_reextract_operations`, and `reextract_operation_id` do not exist.

- [x] **Step 3: Implement the guarded migration and ORM model.**

```python
class ProfileReextractOperation(Base):
    __tablename__ = "profile_reextract_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    source_attachment_id: Mapped[str] = mapped_column(
        ForeignKey("attachments.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    base_profile_updated_at: Mapped[datetime] = mapped_column(nullable=False)
    base_workspace_updated_at: Mapped[datetime] = mapped_column(nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
```

In revision `0008_profile_reextract_ownership`, first query for null or orphan `target_profile_id`, duplicate `target_profile_id`, orphan `source_attachment_id`, and `PRAGMA foreign_key_check`. Raise `alembic.util.CommandError` before any DDL when any query returns data. Rebuild `profile_drafts` preserving every existing scalar and JSON value, make `target_profile_id` non-null and unique, add nullable unique `reextract_operation_id` with `ON DELETE RESTRICT`, and add the check `reextract_operation_id IS NULL OR source_attachment_id IS NOT NULL`. Create `profile_reextract_operations` with named state/error coupling checks, the exact actionable partial unique index shown in Step 1, and index `ix_profile_reextract_operations_recovery(profile_id, updated_at, id)`. Add `profile_reextract_operations` to `app.db.seed.APPLICATION_TABLE_NAMES`, the single owner consumed by schema-parity and fresh-head checks. Set `tests.support.db_migration.MIGRATION_HEAD` to `0008_profile_reextract_ownership`, make `test_migrations.py` assert that revision, and update `test_compose_runtime.py` to read `0008_profile_reextract_ownership.py` and assert its revision string. Downgrade must raise `CommandError` before DDL when an operation exists or any draft references one; otherwise restore the prior draft shape and drop only the new operation artifacts.

- [x] **Step 4: Run the focused migration and schema tests to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_migrations.py::test_0008_rejects_ambiguous_drafts_before_schema_mutation tests/integration/test_migrations.py::test_0008_preserves_valid_draft_schema_rows_and_json tests/integration/test_migrations.py::test_0008_downgrade_refuses_populated_operation_without_mutation tests/integration/test_migrations.py::test_0008_empty_operation_downgrade_and_reupgrade_preserves_ordinary_draft tests/integration/test_migrations.py::test_0008_is_the_migration_head tests/integration/test_database_contract.py::test_operation_schema_has_exact_constraints tests/integration/test_compose_runtime.py::test_compose_source_has_exact_services_and_migrates_before_uvicorn -q`

Expected: PASS; metadata snapshots, row/scalar/canonical-JSON values, `PRAGMA foreign_key_check`, downgrade refusal, and empty reverse path are all asserted.

- [x] **Step 5: Commit the schema boundary.**

```powershell
git add backend/migrations/versions/0008_profile_reextract_ownership.py backend/app/db/models/profiles.py backend/app/db/seed.py backend/tests/support/db_migration.py backend/tests/integration/test_migrations.py backend/tests/integration/test_database_contract.py backend/tests/integration/test_compose_runtime.py
git commit -m "feat: add durable profile reextract schema"
```

### Task 2: Replace global draft access with profile-scoped repository methods

**Files:**
- Modify: `backend/app/repositories/profiles.py`
- Modify: `backend/app/agent/context.py`
- Modify: `backend/app/api/profile.py`
- Modify: `backend/app/services/attachment_resolve.py`
- Modify: `backend/app/services/activity_gate.py`
- Modify: `backend/app/services/cv_manager.py`
- Modify: `backend/app/services/cv_upload.py`
- Modify: `backend/app/services/profile_approval.py`
- Modify: `backend/app/services/profile_drafts.py`
- Modify: `backend/app/services/profile_projection.py`
- Modify: `backend/app/services/profile_reextraction.py`
- Modify: `backend/app/tools/profile.py`
- Modify: `backend/tests/unit/test_agent_context.py`
- Modify: `backend/tests/unit/test_attachment_resolve.py`
- Modify: `backend/tests/unit/test_profile_extraction.py`
- Modify: `backend/tests/e2e/test_demo_flow.py`
- Modify: `backend/tests/integration/test_agent_runner.py`
- Modify: `backend/tests/integration/test_chat_api.py`
- Modify: `backend/tests/integration/test_conversations_api.py`
- Modify: `backend/tests/integration/test_cv_api.py`
- Modify: `backend/tests/integration/test_cv_manager_api.py`
- Modify: `backend/tests/integration/test_cv_manager_deletion.py`
- Modify: `backend/tests/integration/test_job_tools.py`
- Modify: `backend/tests/integration/test_match_jobs.py`
- Modify: `backend/tests/integration/test_profile_approval.py`
- Modify: `backend/tests/integration/test_profile_deletion.py`
- Modify: `backend/tests/integration/test_profile_reextraction.py`
- Modify: `backend/tests/integration/test_profiles_api.py`

- [x] **Step 1: Write failing owner-isolation and symbolic-current tests.**

```python
async def test_drafts_are_isolated_by_explicit_profile_owner(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        first, second = await seed_two_ready_profiles(session)
        await profiles.upsert_draft_for_profile(session, profile_id=first.id, draft_json=first_payload)
        await profiles.upsert_draft_for_profile(session, profile_id=second.id, draft_json=second_payload)
        assert (await profiles.get_draft_for_profile(session, first.id)).draft_json == first_payload
        assert (await profiles.get_draft_for_profile(session, second.id)).draft_json == second_payload


def test_agent_current_draft_context_uses_requested_profile_only() -> None:
    assert "draft_id='current'" in build_profile_context(profile_id=PROFILE_A)
    assert "Profile B draft" not in build_profile_context(profile_id=PROFILE_A)
```

- [x] **Step 2: Run the scoped repository tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profile_reextraction.py::test_drafts_are_isolated_by_explicit_profile_owner tests/unit/test_agent_context.py::test_agent_current_draft_context_uses_requested_profile_only -q`

Expected: FAIL because `get_current_draft` selects the newest draft across the database.

- [x] **Step 3: Implement explicit repository signatures and migrate every caller.**

```python
async def get_draft_for_profile(session: AsyncSession, profile_id: str) -> ProfileDraft | None:
    statement = select(ProfileDraft).where(ProfileDraft.target_profile_id == _required("profile_id", profile_id))
    return (await session.execute(statement)).scalar_one_or_none()

async def get_draft_for_operation(
    session: AsyncSession, profile_id: str, operation_id: str
) -> ProfileDraft | None:
    statement = select(ProfileDraft).where(ProfileDraft.target_profile_id == profile_id, ProfileDraft.reextract_operation_id == operation_id)
    return (await session.execute(statement)).scalar_one_or_none()

async def upsert_draft_for_profile(
    session: AsyncSession, *, profile_id: str, draft_json: dict[str, Any],
    source_attachment_id: str | None, reextract_operation_id: str | None = None,
) -> ProfileDraft:
    existing = await get_draft_for_profile(session, profile_id)
    if existing is None:
        existing = ProfileDraft(id=new_uuid(), target_profile_id=profile_id, draft_json=draft_json, source_attachment_id=source_attachment_id, reextract_operation_id=reextract_operation_id, created_at=utc_now(), updated_at=utc_now())
        session.add(existing)
    else:
        if existing.reextract_operation_id != reextract_operation_id:
            raise ProfileRepositoryError("draft operation owner cannot change")
        if reextract_operation_id is not None and existing.source_attachment_id != source_attachment_id:
            raise ProfileRepositoryError("operation draft source attachment cannot change")
        existing.draft_json = draft_json
        existing.source_attachment_id = source_attachment_id
        existing.updated_at = utc_now()
    await session.flush()
    return existing

async def delete_draft_for_profile(
    session: AsyncSession, *, profile_id: str, expected_revision: datetime | None = None,
    expected_operation_id: str | None = None,
) -> bool:
    row = await get_draft_for_profile(session, profile_id)
    if row is None or (expected_revision is not None and row.updated_at != expected_revision) or (expected_operation_id is not None and row.reextract_operation_id != expected_operation_id):
        return False
    await session.delete(row)
    await session.flush()
    return True
```

Delete `get_current_draft`, `upsert_current_draft`, and `delete_current_draft` only after migrating every listed production and test caller. Every replacement query must predicate `ProfileDraft.target_profile_id == profile_id`; operation reads must additionally predicate `ProfileDraft.reextract_operation_id == operation_id`. An operation ID may be set only when atomic publication inserts a new row after proving no draft exists. An existing ordinary draft cannot gain an operation ID; an existing operation-linked draft cannot clear, replace, or move that ID and cannot change its source attachment. Agent correction code must reload and pass the same operation ID when updating its review-ready draft. Reject every ownership/source move with `ProfileRepositoryError`. Resolve Agent `draft_id='current'` by the current conversation profile ID, never by global ordering or source attachment. Do not retain a global, newest-row, compatibility, or alias helper. The authoritative caller inventory is the `rg -l` result captured in this task; rerun it before the commit and add any newly found caller to this same commit.

- [x] **Step 4: Run focused scoped-caller regressions to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profile_reextraction.py::test_drafts_are_isolated_by_explicit_profile_owner tests/unit/test_agent_context.py::test_agent_current_draft_context_uses_requested_profile_only tests/unit/test_attachment_resolve.py tests/unit/test_profile_extraction.py tests/integration/test_agent_runner.py tests/integration/test_chat_api.py tests/integration/test_conversations_api.py tests/integration/test_cv_api.py tests/integration/test_cv_manager_api.py tests/integration/test_cv_manager_deletion.py tests/integration/test_job_tools.py tests/integration/test_match_jobs.py tests/integration/test_profile_approval.py tests/integration/test_profile_deletion.py tests/integration/test_profiles_api.py tests/e2e/test_demo_flow.py -q`

Run: `rg -n -S "get_current_draft|upsert_current_draft|delete_current_draft" backend/app backend/tests --glob '*.py'; if ($LASTEXITCODE -ne 1) { exit 1 }`

Expected: PASS; Profile A cannot read, mutate, approve, or discard Profile B's draft, the Agent-facing symbolic draft identifier remains supported, and the zero-old-symbol scan returns exit code 1 with no output.

- [x] **Step 5: Commit the repository boundary.**

```powershell
git add backend/app/repositories/profiles.py backend/app/agent/context.py backend/app/api/profile.py backend/app/services/attachment_resolve.py backend/app/services/activity_gate.py backend/app/services/cv_manager.py backend/app/services/cv_upload.py backend/app/services/profile_approval.py backend/app/services/profile_drafts.py backend/app/services/profile_projection.py backend/app/services/profile_reextraction.py backend/app/tools/profile.py backend/tests/unit/test_agent_context.py backend/tests/unit/test_attachment_resolve.py backend/tests/unit/test_profile_extraction.py backend/tests/e2e/test_demo_flow.py backend/tests/integration/test_agent_runner.py backend/tests/integration/test_chat_api.py backend/tests/integration/test_conversations_api.py backend/tests/integration/test_cv_api.py backend/tests/integration/test_cv_manager_api.py backend/tests/integration/test_cv_manager_deletion.py backend/tests/integration/test_job_tools.py backend/tests/integration/test_match_jobs.py backend/tests/integration/test_profile_approval.py backend/tests/integration/test_profile_deletion.py backend/tests/integration/test_profile_reextraction.py backend/tests/integration/test_profiles_api.py
git commit -m "refactor: scope profile drafts by owner"
```

### Task 3: Add operation repository and immediate-write claim serialization

**Files:**
- Create: `backend/app/repositories/profile_reextract_operations.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/app/services/activity_gate.py`
- Create: `backend/tests/integration/test_profile_reextract_operations.py`
- Modify: `backend/tests/unit/test_service_transaction_ownership.py`

- [x] **Step 1: Write failing duplicate-claim and terminal-replacement tests.**

```python
async def test_claim_allows_one_running_operation(
    factory: async_sessionmaker[AsyncSession], ready_profile: Profile
) -> None:
    barrier = anyio.Event()
    send, receive = anyio.create_memory_object_stream[tuple[str, str]](2)

    async def contender() -> None:
        await barrier.wait()
        try:
            async with immediate_session_scope(factory) as session:
                operation = await claim_operation(
                    session,
                    profile_id=ready_profile.id,
                    source_attachment_id=ready_profile.attachment_id,
                    base_profile_updated_at=ready_profile.updated_at,
                    base_workspace_updated_at=(
                        await workspace_repo.get_workspace_state(session)
                    ).updated_at,
                )
            await send.send(("claimed", operation.id))
        except ProfileReextractOperationConflict:
            await send.send(("conflict", "PROFILE_REEXTRACT_IN_PROGRESS"))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(contender)
        task_group.start_soon(contender)
        barrier.set()
    results = {await receive.receive(), await receive.receive()}
    assert {state for state, _ in results} == {"claimed", "conflict"}


class BusySessionStub:
    def __init__(
        self,
        *,
        execute_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.execute_error = execute_error
        self.commit_error = commit_error
        self.rollback_calls = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        if self.execute_error is not None:
            raise self.execute_error

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollback_calls += 1


class SessionFactoryStub:
    def __init__(self, session: BusySessionStub) -> None:
        self.session = session

    def __call__(self) -> BusySessionStub:
        return self.session


async def test_immediate_scope_maps_busy_from_begin() -> None:
    session = BusySessionStub(
        execute_error=OperationalError(
            "BEGIN IMMEDIATE", {}, sqlite3.OperationalError("database is locked")
        )
    )
    with pytest.raises(ImmediateTransactionBusy):
        async with immediate_session_scope(SessionFactoryStub(session)):
            pytest.fail("BEGIN IMMEDIATE must fail before yielding")
    assert session.rollback_calls == 1


@pytest.mark.parametrize("phase", ["body", "commit"])
async def test_immediate_scope_maps_busy_after_begin(phase: str) -> None:
    busy = OperationalError(
        "write", {}, sqlite3.OperationalError("database is locked")
    )
    session = BusySessionStub(commit_error=busy if phase == "commit" else None)
    with pytest.raises(ImmediateTransactionBusy):
        async with immediate_session_scope(SessionFactoryStub(session)):
            if phase == "body":
                raise busy
    assert session.rollback_calls == 1
```

- [x] **Step 2: Run the operation repository tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profile_reextract_operations.py::test_claim_allows_one_running_operation tests/unit/test_service_transaction_ownership.py::test_immediate_scope_maps_busy_from_begin tests/unit/test_service_transaction_ownership.py::test_immediate_scope_maps_busy_after_begin -q`

Expected: FAIL because no operation repository or `BEGIN IMMEDIATE` transaction helper exists.

- [x] **Step 3: Implement short immediate transactions and operation CAS functions.**

```python
class ImmediateTransactionBusy(RuntimeError):
    """SQLite could not acquire or finish the immediate writer transaction."""


@asynccontextmanager
async def immediate_session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            await session.execute(text("BEGIN IMMEDIATE"))
            yield session
            await session.commit()
        except OperationalError as exc:
            await session.rollback()
            if is_sqlite_busy_or_snapshot(exc):
                raise ImmediateTransactionBusy() from exc
            raise
        except BaseException:
            await session.rollback()
            raise


async def claim_operation(
    session: AsyncSession, *, profile_id: str, source_attachment_id: str,
    base_profile_updated_at: datetime, base_workspace_updated_at: datetime,
) -> ProfileReextractOperation:
    owned_draft = select(ProfileDraft.id).where(ProfileDraft.reextract_operation_id == ProfileReextractOperation.id).exists()
    await session.execute(delete(ProfileReextractOperation).where(ProfileReextractOperation.profile_id == profile_id, ProfileReextractOperation.state.in_(("interrupted", "failed", "stale")), ~owned_draft))
    row = ProfileReextractOperation(id=new_uuid(), profile_id=profile_id, source_attachment_id=source_attachment_id, state="running", base_profile_updated_at=base_profile_updated_at, base_workspace_updated_at=base_workspace_updated_at, error_code=None, created_at=utc_now(), updated_at=utc_now())
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        if is_actionable_operation_unique_conflict(exc):
            raise ProfileReextractOperationConflict("PROFILE_REEXTRACT_IN_PROGRESS") from exc
        raise
    return row

class ProfileReextractOperationConflict(Exception):
    """Repository-level claim/CAS conflict; services map it to public errors."""

async def transition_running_operation(
    session: AsyncSession, *, profile_id: str, operation_id: str,
    to_state: Literal["review_ready", "interrupted", "failed", "stale"],
    error_code: str | None,
) -> bool:
    statement = update(ProfileReextractOperation).where(ProfileReextractOperation.id == operation_id, ProfileReextractOperation.profile_id == profile_id, ProfileReextractOperation.state == "running").values(state=to_state, error_code=error_code, updated_at=utc_now())
    return (await session.execute(statement)).rowcount == 1
```

The coordinator claim uses `immediate_session_scope` and performs all SQLite lifecycle preflight after `BEGIN IMMEDIATE`: load and validate the active ready profile, assert no incomplete profile setup or existing draft, call `assert_workspace_idle`, call `assert_profile_review_clear`, reload and validate attachment ownership/state, reject an actionable operation, remove only draftless `interrupted`/`failed`/`stale` rows, capture profile and workspace revisions, then insert `running`. `claim_operation` performs the terminal cleanup and insert only after those validated values are passed to it. `profile_reextract_operations.py` defines and raises `ProfileReextractOperationConflict`; it must not import `ProfileReextractError`. `is_actionable_operation_unique_conflict(exc)` returns true only for `uq_profile_reextract_operations_actionable`; a matching `IntegrityError` maps at `flush`, and every unrelated `IntegrityError` re-raises unchanged. `claim_operation` must not catch busy/snapshot `OperationalError`. `immediate_session_scope` catches those failures from `BEGIN IMMEDIATE`, body writes, and commit, rolls back, and raises `ImmediateTransactionBusy`. Claim and upload map this unknown writer-contention case to HTTP 409 `PROFILE_LIFECYCLE_BUSY` with retry guidance and no invented operation identity. A duplicate claim that acquires the writer lock and observes/hits the actionable operation still returns `PROFILE_REEXTRACT_IN_PROGRESS` with its exact operation ID. Add regressions that inject `OperationalError("database is locked")` separately from initial execute, body write, and commit; all public claim/upload paths return `PROFILE_LIFECYCLE_BUSY`, never 500. The immediate transaction excludes only retained-file access, provider work, SSE yields, and graph work. Task 5 exclusively verifies exactly-one staging/provider call. Add `assert_profile_reextract_clear` that blocks upload, activation, deletion, and a second claim only for actionable operations or any operation-owned draft.

- [x] **Step 4: Run the operation repository tests to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profile_reextract_operations.py tests/unit/test_service_transaction_ownership.py -q`

Expected: PASS; the deterministic barrier admits one durable claim, preserves stale-with-draft recovery data, and verifies `BEGIN IMMEDIATE` is issued before lifecycle writes.

- [x] **Step 5: Commit operation persistence.**

```powershell
git add backend/app/repositories/profile_reextract_operations.py backend/app/db/session.py backend/app/services/activity_gate.py backend/tests/integration/test_profile_reextract_operations.py backend/tests/unit/test_service_transaction_ownership.py
git commit -m "feat: serialize profile reextract claims"
```

### Task 4: Split pure extraction staging from atomic re-extraction publication

**Files:**
- Modify: `backend/app/services/profile_drafts.py`
- Modify: `backend/app/services/profile_extraction.py`
- Modify: `backend/tests/unit/test_profile_extraction.py`
- Modify: `backend/tests/integration/test_profile_reextraction.py`
- Modify: `backend/tests/integration/test_cv_api.py`

- [x] **Step 1: Write failing pure-stage and publication-CAS tests.**

```python
async def test_stage_cv_document_has_no_open_session_and_no_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import inspect
    import app.services.profile_drafts as profile_drafts

    assert "session" not in inspect.signature(stage_cv_document).parameters
    assert "session_factory" not in inspect.signature(stage_cv_document).parameters
    monkeypatch.setattr(profile_drafts, "session_scope", pytest.fail)
    monkeypatch.setattr(profile_drafts.cv_doc_repo, "upsert_draft", pytest.fail)
    monkeypatch.setattr(profile_drafts.profile_repo, "upsert_draft_for_profile", pytest.fail)
    monkeypatch.setattr(profile_drafts, "persist_canonical_chunks", pytest.fail)
    staged = await stage_cv_document(attachment=attachment, storage=storage, invoker=invoker, normalizer=normalizer)
    assert isinstance(staged, StagedCvProposal)
    assert staged.draft_payload.candidate_profile.full_name == "Alex Example"


async def test_publish_marks_operation_stale_without_partial_writes_when_workspace_revision_changes(
    factory: async_sessionmaker[AsyncSession],
    running_operation: ProfileReextractOperation,
    attachment: Attachment,
) -> None:
    async with factory() as session:
        before_chunks = [
            (row.ordinal, row.text, row.preview, row.char_count, row.token_estimate)
            for row in (await session.scalars(
                select(AttachmentTextChunk)
                .where(AttachmentTextChunk.attachment_id == attachment.id)
                .order_by(AttachmentTextChunk.ordinal)
            )).all()
        ]
        before_document = await cv_doc_repo.get_draft(session, attachment.id)
        assert before_document is not None
        before_document_values = (
            before_document.document_json,
            before_document.profile_json,
            before_document.outline_json,
            before_document.extraction_version,
            before_document.source_hash,
        )
    staged = await stage_cv_document(attachment=attachment, storage=storage, invoker=invoker, normalizer=normalizer)
    async with session_scope(factory) as session:
        workspace = await workspace_repo.get_workspace_state(session)
        assert workspace is not None
        workspace.updated_at = utc_now()
    result = await publish_reextract_stage(
        session_factory=factory,
        profile_id=running_operation.profile_id,
        operation_id=running_operation.id,
        staged=staged,
    )
    assert result.state == "stale"
    async with factory() as session:
        assert await profile_repo.get_draft_for_operation(
            session, running_operation.profile_id, running_operation.id
        ) is None
        after_document = await cv_doc_repo.get_draft(session, attachment.id)
        assert after_document is not None
        assert (
            after_document.document_json,
            after_document.profile_json,
            after_document.outline_json,
            after_document.extraction_version,
            after_document.source_hash,
        ) == before_document_values
        after_chunks = [
            (row.ordinal, row.text, row.preview, row.char_count, row.token_estimate)
            for row in (await session.scalars(
                select(AttachmentTextChunk)
                .where(AttachmentTextChunk.attachment_id == attachment.id)
                .order_by(AttachmentTextChunk.ordinal)
            )).all()
        ]
        assert after_chunks == before_chunks
```

- [x] **Step 2: Run the stage/publication tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/unit/test_profile_extraction.py::test_stage_cv_document_has_no_open_session_and_no_persistence tests/integration/test_profile_reextraction.py::test_publish_marks_operation_stale_without_partial_writes_when_workspace_revision_changes tests/integration/test_cv_api.py -q`

Expected: FAIL because `propose_profile_from_cv` performs staging and draft publication as one path with no operation CAS.

- [x] **Step 3: Implement the shared in-memory stage and atomic publisher.**

```python
@dataclass(frozen=True, slots=True)
class StagedCvProposal:
    attachment_id: str
    chunks: Sequence[CanonicalChunk]
    draft_payload: ProfileDraftPayload
    document_json: dict[str, Any]
    profile_json: dict[str, Any]
    outline_json: dict[str, Any]
    extraction_version: str
    source_hash: str


async def stage_cv_document(*, attachment: Attachment, storage: AttachmentStorage,
                            normalizer: SkillNormalizer, invoker: Any) -> StagedCvProposal:
    artifacts: DocumentPublicationArtifacts = extract_document_publication_from_pdf(storage.resolve_path(attachment.storage_path), attachment_id=attachment.id, invoker=invoker, normalizer=normalizer)
    return StagedCvProposal(attachment_id=attachment.id, chunks=artifacts.chunks, draft_payload=artifacts.draft, document_json=artifacts.document_json, profile_json=artifacts.profile_json, outline_json=artifacts.outline_json, extraction_version=artifacts.extraction_version, source_hash=artifacts.source_hash)

@dataclass(frozen=True, slots=True)
class PublishResult:
    state: Literal["review_ready", "stale"]
    revision: datetime | None

class PublishCasMismatch(Exception):
    def __init__(self, operation_id: str) -> None:
        self.operation_id = operation_id
        super().__init__(operation_id)

async def has_incomplete_profile_setup(
    session: AsyncSession,
) -> bool:
    return (await session.execute(
        select(Profile.id).where(
            Profile.state == PROFILE_STATE_PENDING,
        )
    )).scalar_one_or_none() is not None

async def _publish_reextract_stage_transaction(*, session_factory: async_sessionmaker[AsyncSession],
                                                profile_id: str, operation_id: str,
                                                staged: StagedCvProposal) -> PublishResult:
    async with session_scope(session_factory) as session:
        operation = await operation_repo.get_operation(session, profile_id=profile_id, operation_id=operation_id)
        profile = await profile_repo.get_profile(session, profile_id)
        workspace = await workspace_repo.get_workspace_state(session)
        if operation is None or profile is None or workspace is None or operation.state != "running" or await workspace_repo.get_active_profile_id(session) != profile_id or operation.source_attachment_id != staged.attachment_id or profile.attachment_id != staged.attachment_id or profile.updated_at != operation.base_profile_updated_at or workspace.updated_at != operation.base_workspace_updated_at or await profile_repo.get_draft_for_profile(session, profile_id) is not None or await has_incomplete_profile_setup(session):
            raise PublishCasMismatch(operation_id)
        await persist_canonical_chunks(session, attachment_id=staged.attachment_id, chunks=staged.chunks)
        await cv_doc_repo.upsert_draft(session, attachment_id=staged.attachment_id, document_json=staged.document_json, profile_json=staged.profile_json, outline_json=staged.outline_json, extraction_version=staged.extraction_version, source_hash=staged.source_hash)
        draft = await profile_repo.upsert_draft_for_profile(session, profile_id=profile_id, draft_json=staged.draft_payload.model_dump(mode="json"), source_attachment_id=staged.attachment_id, reextract_operation_id=operation_id)
        changed = await operation_repo.transition_running_operation(session, profile_id=profile_id, operation_id=operation_id, to_state="review_ready", error_code=None)
        if not changed:
            raise PublishCasMismatch(operation_id)
        return PublishResult(state="review_ready", revision=draft.updated_at)

async def publish_reextract_stage(**kwargs: object) -> PublishResult:
    operation_id = cast(str, kwargs["operation_id"])
    try:
        return await _publish_reextract_stage_transaction(**kwargs)
    except PublishCasMismatch:
        async with session_scope(cast(async_sessionmaker[AsyncSession], kwargs["session_factory"])) as session:
            await operation_repo.transition_running_operation(
                session,
                profile_id=cast(str, kwargs["profile_id"]),
                operation_id=operation_id,
                to_state="stale",
                error_code="PROFILE_REEXTRACT_STALE",
            )
        return PublishResult(state="stale", revision=None)
```

`stage_cv_document` may read the retained file and call the provider, but it must not accept a session or write any database row. The purity test inspects its signature and monkeypatches the module's `session_scope`, `cv_doc_repo.upsert_draft`, `profile_repo.upsert_draft_for_profile`, and `persist_canonical_chunks` entrypoints to `pytest.fail` before staging; a row-count assertion alone is insufficient. `publish_reextract_stage` must use a fresh short session and, before any write, check exact operation ID, `running` state, current active profile identity, operation source attachment identity, retained profile attachment identity, captured profile and workspace timestamps, absence of any profile-scoped draft, and global absence of incomplete profile setup via `has_incomplete_profile_setup(session)`. Only then replace canonical chunks, call `cv_documents.upsert_draft` with its actual keyword-only signature shown above, write the profile-scoped operation-linked draft, and change the operation to `review_ready`. `_publish_reextract_stage_transaction` raises `PublishCasMismatch`; the shown outer `publish_reextract_stage` catches it after rollback and opens a separate short session to CAS the exact running operation to `stale` with `PROFILE_REEXTRACT_STALE`.

- [x] **Step 4: Run focused stage and CAS regressions to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/unit/test_profile_extraction.py::test_stage_cv_document_has_no_open_session_and_no_persistence tests/integration/test_profile_reextraction.py::test_publish_marks_operation_stale_without_partial_writes_when_workspace_revision_changes tests/integration/test_profile_reextraction.py::test_publish_compares_profile_workspace_attachment_and_operation tests/integration/test_cv_api.py -q`

Expected: PASS; provider and filesystem work happen without an open database session, successful publication is atomic, and failed CAS leaves no proposal data.

- [x] **Step 5: Commit the stage/publication split.**

```powershell
git add backend/app/services/profile_drafts.py backend/app/services/profile_extraction.py backend/tests/unit/test_profile_extraction.py backend/tests/integration/test_profile_reextraction.py backend/tests/integration/test_cv_api.py
git commit -m "refactor: separate profile extraction staging"
```

### Task 5: Make direct re-extraction durable, cancellable, and restart-recoverable

**Files:**
- Modify: `backend/app/services/profile_reextraction.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/unit/test_profile_reextraction.py`
- Modify: `backend/tests/integration/test_profile_reextraction.py`
- Modify: `backend/tests/integration/test_interrupt_resume.py`

- [x] **Step 1: Write failing claim-before-work, cancellation, pool, and startup tests.**

```python
async def test_stream_claims_before_first_event_or_provider_call() -> None:
    events = coordinator.stream(PROFILE_ID)
    first = await anext(events)
    assert first.operation_id == await only_operation_id(factory, PROFILE_ID)
    invoker.assert_not_called()


async def test_cancelled_stream_persists_interrupted_after_session_close(caplog: pytest.LogCaptureFixture) -> None:
    stream = coordinator.stream(PROFILE_ID)
    await anext(stream)
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())
    assert await operation_state(factory, PROFILE_ID) == "interrupted"
    assert "no active connection" not in caplog.text
    assert "checked out" not in caplog.text


async def test_startup_changes_running_only_to_interrupted() -> None:
    await seed_operation(factory, state="running")
    await seed_operation(factory, state="review_ready", with_draft=True)
    await recover_running_profile_reextract_operations(factory)
    assert await states(factory) == ["interrupted", "review_ready"]
```

- [x] **Step 2: Run durable-stream tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/unit/test_profile_reextraction.py::test_stream_claims_before_first_event_or_provider_call tests/unit/test_profile_reextraction.py::test_cancelled_stream_persists_interrupted_after_session_close tests/integration/test_interrupt_resume.py::test_startup_changes_running_only_to_interrupted -q`

Expected: FAIL because the current stream creates its operation ID in memory and cancellation does not finalize a durable operation.

- [x] **Step 3: Implement coordinator claim, shielded cancellation, and startup recovery.**

```python
async def stream(self, profile_id: str) -> AsyncIterator[ProfileReextractEvent]:
    operation = await self._claim(profile_id)
    try:
        yield _progress(operation_id=operation.id, profile_id=profile_id, stage="validating_source")
        staged = await stage_cv_document(attachment=await self._load_attachment(operation), storage=self._storage, normalizer=self._normalizer, invoker=self._invoker)
        published = await publish_reextract_stage(session_factory=self._session_factory, profile_id=profile_id, operation_id=operation.id, staged=staged)
    except (asyncio.CancelledError, GeneratorExit):
        with anyio.CancelScope(shield=True):
            async with session_scope(self._session_factory) as session:
                await operations.transition_running_operation(session, profile_id=profile_id, operation_id=operation.id, to_state="interrupted", error_code="PROFILE_REEXTRACT_INTERRUPTED")
        raise
```

Keep `CancelScope(shield=True)` outside the complete fresh `session_scope`, let the context manager finish before re-raising, and do not reuse a request session. Record provider and retained-file failures with a short fresh failure transaction. Add `recover_running_profile_reextract_operations(session_factory)` to `lifespan` after SQLite readiness and before serving; it must transition only `running` rows to `interrupted`.

- [x] **Step 4: Run focused durability and cancellation regressions to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/unit/test_profile_reextraction.py tests/integration/test_profile_reextraction.py::test_duplicate_requests_perform_one_staging_and_provider_call tests/integration/test_interrupt_resume.py::test_startup_changes_running_only_to_interrupted tests/integration/test_chat_api.py::test_disconnect_returns_connections_to_pool -q`

Expected: PASS; a committed operation exists before SSE and provider work, duplicate requests return `PROFILE_REEXTRACT_IN_PROGRESS`, cancellation leaves `interrupted`, and logs contain no pool or active-connection warning.

- [x] **Step 5: Commit durable orchestration.**

```powershell
git add backend/app/services/profile_reextraction.py backend/app/main.py backend/tests/unit/test_profile_reextraction.py backend/tests/integration/test_profile_reextraction.py backend/tests/integration/test_interrupt_resume.py
git commit -m "feat: recover durable profile reextract operations"
```

### Task 6: Add operation-aware review reconciliation, approval, discard, and mutation gates

**Files:**
- Modify: `backend/app/repositories/profile_reextract_operations.py`
- Modify: `backend/app/services/profile_reextraction.py`
- Modify: `backend/app/services/profile_approval.py`
- Modify: `backend/app/services/profile_drafts.py`
- Modify: `backend/app/services/activity_gate.py`
- Modify: `backend/app/services/profile_activation.py`
- Modify: `backend/app/services/profile_deletion.py`
- Modify: `backend/app/tools/profile.py`
- Modify: `backend/app/schemas/profile_reextraction.py`
- Modify: `backend/app/api/profiles.py`
- Modify: `backend/tests/integration/test_profile_approval.py`
- Modify: `backend/tests/integration/test_profile_deletion.py`
- Modify: `backend/tests/integration/test_profile_reextraction.py`
- Modify: `backend/tests/integration/test_profiles_api.py`
- Modify: `backend/tests/integration/test_agent_runner.py`

- [x] **Step 1: Write failing stale-review and exact-consumption tests.**

```python
async def test_status_read_reconciles_review_ready_to_stale_and_agent_cannot_edit() -> None:
    await seed_review_ready(factory, operation_id=OPERATION_ID, revision=REVISION)
    await bump_profile_revision(factory, PROFILE_ID)
    review = await coordinator.get_review(PROFILE_ID, operation_id=OPERATION_ID)
    assert review.operation_state == "stale"
    assert review.can_approve is False
    assert review.can_discard is True
    assert (await propose_profile_update_for_profile(PROFILE_ID)).code == "PROFILE_REEXTRACT_STALE"


async def test_approve_and_discard_require_matching_operation_and_revision() -> None:
    with pytest.raises(ProfileReextractError, match="PROFILE_REEXTRACT_CONFLICT"):
        await coordinator.discard(PROFILE_ID, operation_id=OTHER_OPERATION_ID, revision=REVISION)
    await coordinator.approve(PROFILE_ID, operation_id=OPERATION_ID, revision=REVISION)
    assert await operation_exists(factory, OPERATION_ID) is False
    assert await draft_exists(factory, PROFILE_ID) is False
```

- [x] **Step 2: Run review and approval tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profile_reextraction.py::test_status_read_reconciles_review_ready_to_stale_and_agent_cannot_edit tests/integration/test_profile_reextraction.py::test_approve_and_discard_require_matching_operation_and_revision tests/integration/test_profile_approval.py tests/integration/test_profile_deletion.py tests/integration/test_profiles_api.py tests/integration/test_agent_runner.py -q`

Expected: FAIL because review, approval, discard, Agent correction, activation, and deletion do not compare the operation identity and captured workspace revision.

- [x] **Step 3: Add exact review and consumption CAS contracts.**

```python
async def get_review(
    self, profile_id: str, *, operation_id: str | None
) -> ProfileReextractReview:
    return await self._load_reconciled_review(profile_id=profile_id, operation_id=operation_id)

async def approve(self, profile_id: str, *, operation_id: str | None,
                  revision: datetime) -> ProfileReextractApprovalResponse:
    return await self._approve_exact(profile_id=profile_id, operation_id=operation_id, revision=revision)

async def discard(self, profile_id: str, *, operation_id: str | None,
                  revision: datetime) -> None:
    await self._discard_exact(profile_id=profile_id, operation_id=operation_id, revision=revision)

async def _validate_operation_linked_approval(
    session: AsyncSession,
    *,
    preflight: _Preflight,
    expected_profile_id: str,
    expected_operation_id: str | None,
) -> ProfileReextractOperation | None:
    operation_id = preflight.draft_reextract_operation_id
    if operation_id is None:
        if expected_operation_id is not None:
            raise ProfileApprovalError(
                "Ordinary draft cannot consume a re-extraction operation",
                code="PROFILE_REEXTRACT_CONFLICT",
            )
        return None
    if expected_operation_id != operation_id:
        raise ProfileApprovalError(
            "Re-extraction operation identity changed",
            code="PROFILE_REEXTRACT_CONFLICT",
        )
    operation = await operation_repo.get_operation(
        session, profile_id=expected_profile_id, operation_id=operation_id
    )
    profile = await profile_repo.get_profile(session, expected_profile_id)
    workspace = await workspace_repo.get_workspace_state(session)
    if (
        operation is None
        or profile is None
        or workspace is None
        or operation.state != "review_ready"
        or profile.updated_at != operation.base_profile_updated_at
        or workspace.updated_at != operation.base_workspace_updated_at
    ):
        raise ProfileApprovalError(
            "Re-extraction review is stale",
            code="PROFILE_REEXTRACT_STALE",
        )
    return operation


# Inside commit_approved_draft's existing DB-only transaction, after its live
# _load_preflight(session, storage=None, check_files=False,
# expected_profile_id=expected_profile_id) call:
operation = await _validate_operation_linked_approval(
    session,
    preflight=live,
    expected_profile_id=expected_profile_id,
    expected_operation_id=expected_operation_id,
)
profile_updated_at, approved_profile_id, conversation_id = (
    await _run_sqlite_approval(session, live, failpoint=failpoint)
)
# _run_sqlite_approval has already promoted/deleted the matching document draft
# and deleted the profile draft, so the restrictive operation FK is now clear.
if operation is not None:
    deleted = await operation_repo.delete_operation(
        session,
        profile_id=expected_profile_id,
        operation_id=operation.id,
        expected_state="review_ready",
    )
    if not deleted:
        raise ProfileApprovalError(
            "Re-extraction operation changed during approval",
            code="PROFILE_REEXTRACT_CONFLICT",
        )
```

On every review read, compare a `review_ready` operation's captured profile/workspace timestamps in a short transaction and CAS it to `stale` when either differs. A stale row with a draft remains readable and discardable but is not approvable or editable by `propose_profile_update`; add an integration test through the real `build_propose_profile_update_tool` result's `.ainvoke()` path and its existing `execute_tool` owner, not a direct service-only surrogate. Extend `_Preflight` with `draft_reextract_operation_id` loaded from the scoped draft row. Preserve the existing ordinary initial-upload and Agent-only approval path when that value is null. An ordinary review requires `operation_id=null`, returns `source="agent_update"`, and rejects a supplied operation ID. An operation-linked review requires its exact non-null operation ID and returns `source="reextract"`; missing, crossed, stale, and replayed identities fail without mutation. For an operation-linked draft, require exact operation/profile/workspace/draft CAS. The existing `_run_sqlite_approval` promotes and removes the matching document draft and removes the profile draft; only after it returns may the same transaction delete the matching operation whose foreign key uses `ON DELETE RESTRICT`. Gate activation and profile deletion with operation ownership and remove terminal operation metadata without a draft before otherwise permitted profile deletion. Add end-to-end tests proving multiple Agent corrections accumulate through the existing canonical dedupe path, review with `operation_id=null`, and update the active profile only after explicit approval.

This task owns the discriminated `operation_id` changes for existing review endpoints. Add the required-but-nullable `operation_id: UuidStr | None` field to `ProfileReextractApproveRequest`; use a nullable review/discard query. `GET /reextract-draft`, `POST /reextract-draft/approve`, and `DELETE /reextract-draft` must pass it to the coordinator. A profile-scoped ordinary draft accepts only null, while an operation-linked draft accepts only its exact UUID. `ProfileReextractReview` exposes `source: Literal["agent_update", "reextract"]`, nullable `operation_id`, and nullable `operation_state`, with validators enforcing the source/identity combination. Task 8 owns only the new status endpoint and `/api/profile` operation envelope/projection. Keep the coordinator's internal exact methods until this task updates all three routes; do not ship a route that can consume an operation-linked draft by profile identity alone.

- [x] **Step 4: Run focused review, approval, and deletion regressions to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profile_reextraction.py::test_status_read_reconciles_review_ready_to_stale_and_agent_cannot_edit tests/integration/test_profile_reextraction.py::test_approve_and_discard_require_matching_operation_and_revision tests/integration/test_profile_approval.py tests/integration/test_profile_deletion.py tests/integration/test_profiles_api.py tests/integration/test_agent_runner.py tests/unit/test_profile_projection.py -q`

Expected: PASS; review reconciliation is durable, stale review cannot be approved or edited, exact approval/discard consumes only matching rows, and deletion preserves restrictive-FK integrity.

- [x] **Step 5: Commit review and approval safety.**

```powershell
git add backend/app/repositories/profile_reextract_operations.py backend/app/services/profile_reextraction.py backend/app/services/profile_approval.py backend/app/services/profile_drafts.py backend/app/services/activity_gate.py backend/app/services/profile_activation.py backend/app/services/profile_deletion.py backend/app/tools/profile.py backend/app/schemas/profile_reextraction.py backend/app/api/profiles.py backend/tests/integration/test_profile_approval.py backend/tests/integration/test_profile_deletion.py backend/tests/integration/test_profile_reextraction.py backend/tests/integration/test_profiles_api.py backend/tests/integration/test_agent_runner.py
git commit -m "feat: enforce reextract review compare and swap"
```

### Task 7: Serialize uploads and expose only allowed CV actions

**Files:**
- Modify: `backend/app/services/cv_upload.py`
- Modify: `backend/app/services/activity_gate.py`
- Modify: `backend/app/services/cv_manager_projection.py`
- Modify: `backend/app/services/cv_manager.py`
- Modify: `backend/app/schemas/profile_reextraction.py`
- Modify: `backend/app/api/attachments.py`
- Modify: `backend/app/api/profiles.py`
- Modify: `backend/tests/integration/test_cv_api.py`
- Modify: `backend/tests/integration/test_cv_manager_api.py`
- Modify: `backend/tests/integration/test_cv_manager_deletion.py`

- [x] **Step 1: Write failing final-gate race and archived-action tests.**

```python
async def test_upload_that_passed_prebyte_gate_is_rejected_at_final_immediate_gate() -> None:
    upload_at_prebyte_gate.set()
    await claim_started.wait()
    response = await finish_upload()
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_REEXTRACT_IN_PROGRESS"
    assert response.json()["detail"]["operation_id"] == OPERATION_ID
    assert await no_finalized_upload_file(storage)


async def test_upload_blocked_by_agent_review_returns_nullable_operation_context() -> None:
    await seed_agent_update_draft(profile_id=PROFILE_ID, revision=REVISION)
    response = await upload_cv_request()
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "PROFILE_REVIEW_PENDING",
        "summary": "Approve or discard the pending profile review first",
        "profile_id": PROFILE_ID,
        "review_source": "agent_update",
        "operation_id": None,
        "review_revision": REVISION,
    }


async def test_upload_that_passed_prebyte_gate_loses_to_agent_review() -> None:
    upload_at_prebyte_gate.set()
    await seed_agent_update_draft(profile_id=PROFILE_ID, revision=REVISION)
    response = await finish_upload()
    assert response.status_code == 409
    assert response.json()["detail"]["review_source"] == "agent_update"
    assert response.json()["detail"]["operation_id"] is None
    assert await no_finalized_upload_file(storage)


async def test_upload_then_reextract_and_reextract_then_upload_are_serialized() -> None:
    upload_first = await run_barrier_ordering(first="upload")
    reextract_first = await run_barrier_ordering(first="reextract")
    for outcome in (upload_first, reextract_first):
        assert outcome.authoritative_result_count == 1
        assert outcome.orphan_row_count == 0
        assert outcome.losing_upload_file_exists is False


@asynccontextmanager
async def busy_immediate_scope(*args: object, **kwargs: object) -> AsyncIterator[None]:
    raise ImmediateTransactionBusy()
    yield


async def test_upload_begin_immediate_busy_is_typed_409(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cv_upload, "immediate_session_scope", busy_immediate_scope)
    response = await upload_cv_request()
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "PROFILE_LIFECYCLE_BUSY",
        "summary": "CV lifecycle is busy; retry the action",
    }


def test_inactive_archived_cv_never_projects_reextract() -> None:
    actions = allowed_actions(state="archived", owner=archived_owner, is_active=False, file_available=True)
    assert "reextract" not in actions
    assert actions == ["preview", "download", "activate_profile"]
```

- [x] **Step 2: Run upload/CV projection tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_cv_api.py::test_upload_that_passed_prebyte_gate_is_rejected_at_final_immediate_gate tests/integration/test_cv_api.py::test_upload_blocked_by_agent_review_returns_nullable_operation_context tests/integration/test_cv_api.py::test_upload_that_passed_prebyte_gate_loses_to_agent_review tests/integration/test_cv_api.py::test_upload_then_reextract_and_reextract_then_upload_are_serialized tests/integration/test_cv_api.py::test_upload_begin_immediate_busy_is_typed_409 tests/integration/test_cv_manager_api.py::test_inactive_archived_cv_never_projects_reextract tests/integration/test_cv_manager_deletion.py -q`

Expected: FAIL because the final upload write uses a normal transaction and archived inactive profiles still receive `reextract`.

- [x] **Step 3: Implement the final `BEGIN IMMEDIATE` upload gate and action projection.**

```python
async with immediate_session_scope(factory) as session:
    await assert_upload_lifecycle_clear(session, code="PROFILE_REEXTRACT_IN_PROGRESS")
    row = await att_repo.create_staged(session, file_hash=file_hash, original_name=original_name,
                                       size_bytes=size_bytes, storage_path=final_relative,
                                       page_count=page_count, attachment_id=attachment_id)
    profile = await profile_repo.create_pending_profile(session, attachment_id=row.id,
                                                        display_name=original_name)
```

Keep the pre-byte guard as an optimization. Immediately before the first application insert, acquire `BEGIN IMMEDIATE` and recheck actionable re-extraction operations, every profile-scoped pending draft (ordinary Agent or operation-linked), incomplete profile setup, and workspace activity. `assert_upload_lifecycle_clear` must call the scoped review gate inside this transaction. Map observed operation/review conflicts to `PROFILE_REEXTRACT_IN_PROGRESS` or `PROFILE_REVIEW_PENDING`; map `ImmediateTransactionBusy` before a reliable owner can be read to `PROFILE_LIFECYCLE_BUSY`. Delete the finalized file on every failed persistence path and never emit a 500 for an integrity/busy race. In `allowed_actions`, append `reextract` only when `state` is `active`, `is_active` is true, owner state is `ready`, and the retained file is available.

Use a discriminated safe error contract rather than forcing ordinary Agent reviews to invent an operation ID:

```python
class ProfileReextractInProgressDetail(BaseModel):
    code: Literal["PROFILE_REEXTRACT_IN_PROGRESS"]
    summary: str
    profile_id: UuidStr
    operation_id: UuidStr


class ProfileReviewPendingDetail(BaseModel):
    code: Literal["PROFILE_REVIEW_PENDING"]
    summary: str
    profile_id: UuidStr
    review_source: Literal["agent_update", "reextract"]
    operation_id: UuidStr | None
    review_revision: AwareUtcDatetime

    @model_validator(mode="after")
    def validate_owner(self) -> Self:
        if (self.review_source == "reextract") != (self.operation_id is not None):
            raise ValueError("reextract review identity is inconsistent")
        return self
```

Extend `ActivityBlockedError` and `CvUploadError` with optional safe profile/review context. `assert_profile_review_clear` loads the exact profile-scoped draft and reports `review_source`, nullable operation ID, and revision. `attachments._http_for_upload_error` emits `ProfileReextractInProgressDetail` only for a running operation and emits `ProfileReviewPendingDetail` for any durable review. An ordinary Agent review therefore has `review_source="agent_update"` and `operation_id=null`; an operation-linked review has `review_source="reextract"` and its exact UUID. Unrelated upload failures preserve their current detail shape. Task 8 reuses `ProfileReextractInProgressDetail` for duplicate starts.

- [x] **Step 4: Run focused upload race and projection regressions to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_cv_api.py::test_upload_that_passed_prebyte_gate_is_rejected_at_final_immediate_gate tests/integration/test_cv_api.py::test_upload_then_reextract_and_reextract_then_upload_are_serialized tests/integration/test_cv_manager_api.py::test_inactive_archived_cv_never_projects_reextract tests/integration/test_cv_manager_deletion.py -q`

Expected: PASS; both barrier-controlled ordering cases preserve one authoritative result with no orphan rows or finalized files, and inactive archived CVs do not advertise re-extraction.

- [x] **Step 5: Commit upload serialization.**

```powershell
git add backend/app/services/cv_upload.py backend/app/services/activity_gate.py backend/app/services/cv_manager_projection.py backend/app/services/cv_manager.py backend/app/schemas/profile_reextraction.py backend/app/api/attachments.py backend/app/api/profiles.py backend/tests/integration/test_cv_api.py backend/tests/integration/test_cv_manager_api.py backend/tests/integration/test_cv_manager_deletion.py
git commit -m "fix: gate uploads behind reextract operations"
```

### Task 8: Publish the strict lifecycle API and correlated profile projection

**Files:**
- Modify: `backend/app/schemas/common.py`
- Modify: `backend/app/schemas/profile_reextraction.py`
- Modify: `backend/app/schemas/profile.py`
- Modify: `backend/app/repositories/profile_reextract_operations.py`
- Modify: `backend/app/services/profile_reextraction.py`
- Modify: `backend/app/api/profiles.py`
- Modify: `backend/app/api/profile.py`
- Modify: `backend/tests/support/health.py`
- Modify: `backend/tests/integration/test_cv_api.py`
- Modify: `backend/tests/integration/test_profiles_api.py`
- Modify: `backend/tests/integration/test_profile_reextraction.py`
- Modify: `backend/tests/unit/test_api_sse.py`

- [x] **Step 1: Write failing endpoint and safe-payload tests.**

```python
def test_reextract_routes_require_correlated_operation_identity(client: TestClient) -> None:
    response = client.get(f"/api/profiles/{PROFILE_ID}/reextract-operation")
    assert response.status_code == 200
    assert response.json() == {"operation": None}


def test_status_payload_has_no_private_extraction_data() -> None:
    payload = operation_status.model_dump_json()
    assert operation_status.error_code == "PROFILE_REEXTRACT_INTERRUPTED"
    assert operation_status.error_summary == "The re-extraction was interrupted"
    assert operation_status.review_revision is None
    for forbidden in ("storage_path", "source_attachment_id", "chunks", "document_json", "provider", "prompt"):
        assert forbidden not in payload


@pytest.mark.parametrize(
    ("state", "error_code", "error_summary", "review_revision", "actions"),
    [
        ("running", None, None, None, (False, False, False)),
        ("review_ready", None, None, REVISION, (True, False, True)),
        ("interrupted", "PROFILE_REEXTRACT_INTERRUPTED", "The re-extraction was interrupted", None, (False, True, False)),
        ("failed", "PROFILE_REEXTRACT_FAILED", "CV re-extraction could not be completed", None, (False, True, False)),
        ("stale", "PROFILE_REEXTRACT_STALE", "The profile changed during re-extraction", REVISION, (True, False, True)),
        ("stale", "PROFILE_REEXTRACT_STALE", "The profile changed during re-extraction", None, (False, True, False)),
    ],
)
def test_status_action_matrix_is_server_owned(
    state: str,
    error_code: str | None,
    error_summary: str | None,
    review_revision: datetime | None,
    actions: tuple[bool, bool, bool],
) -> None:
    can_review, can_retry, can_discard = actions
    status = ProfileReextractOperationStatus(
        profile_id=PROFILE_ID,
        operation_id=OPERATION_ID,
        state=state,
        error_code=error_code,
        error_summary=error_summary,
        review_revision=review_revision,
        can_review=can_review,
        can_retry=can_retry,
        can_discard=can_discard,
    )
    assert (status.can_review, status.can_retry, status.can_discard) == actions
    with pytest.raises(ValidationError):
        ProfileReextractOperationStatus.model_validate(
            {**status.model_dump(), "can_retry": not can_retry}
        )
```

- [x] **Step 2: Run API tests to verify they fail.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profiles_api.py::test_reextract_routes_require_correlated_operation_identity tests/integration/test_profile_reextraction.py::test_status_payload_has_no_private_extraction_data tests/integration/test_profile_reextraction.py::test_status_action_matrix_is_server_owned tests/integration/test_profile_reextraction.py::test_status_read_reconciles_review_ready_without_owned_draft_to_stale tests/integration/test_cv_api.py::test_get_profile_projects_correlated_reextract_operation tests/integration/test_health.py::test_only_public_functional_routes_are_health_chat_cv_and_profile tests/unit/test_api_sse.py -q`

Expected: FAIL because the status endpoint and strict nullable `operation` envelope do not exist.

- [x] **Step 3: Implement exact request/response contracts and route signatures.**

```python
class ProfileReextractOperationStatus(BaseModel):
    model_config = StrictModelConfig

    profile_id: UuidStr
    operation_id: UuidStr
    state: Literal["running", "review_ready", "interrupted", "failed", "stale"]
    error_code: str | None = Field(max_length=80)
    error_summary: str | None = Field(max_length=200)
    review_revision: AwareUtcDatetime | None
    can_review: bool
    can_retry: bool
    can_discard: bool

    @model_validator(mode="after")
    def validate_state_actions(self) -> Self:
        if self.state in {"running", "review_ready"}:
            if self.error_code is not None or self.error_summary is not None:
                raise ValueError("actionable operations cannot expose an error")
        elif self.error_code is None or self.error_summary is None:
            raise ValueError("terminal operations require a safe error")
        if self.state == "review_ready" and self.review_revision is None:
            raise ValueError("review-ready operations require a review revision")
        if self.state not in {"review_ready", "stale"} and self.review_revision is not None:
            raise ValueError("operation state cannot own a review revision")
        expected = {
            "running": (False, False, False),
            "review_ready": (True, False, True),
            "interrupted": (False, True, False),
            "failed": (False, True, False),
            "stale": (
                (True, False, True)
                if self.review_revision is not None
                else (False, True, False)
            ),
        }[self.state]
        if (self.can_review, self.can_retry, self.can_discard) != expected:
            raise ValueError("operation actions do not match its durable state")
        return self

class ProfileReextractOperationEnvelope(BaseModel):
    model_config = StrictModelConfig

    operation: ProfileReextractOperationStatus | None

@router.get("/profiles/{profile_id}/reextract-operation", response_model=ProfileReextractOperationEnvelope)
async def get_profile_reextract_operation(profile_id: UuidStr, deps: ProfileReextractDeps) -> ProfileReextractOperationEnvelope:
    return ProfileReextractOperationEnvelope(operation=await _profile_reextract_coordinator(deps).get_status(profile_id))
```

Use exactly these new Task 8 routes: `POST /api/profiles/{profile_id}/reextract` and `GET /api/profiles/{profile_id}/reextract-operation`. Existing review, approve, and discard routes already receive the discriminated nullable `operation_id` in Task 6 and are not modified here. The status route always returns the strict `ProfileReextractOperationEnvelope` envelope: `operation` is `ProfileReextractOperationStatus | None`, so an existing ordinary profile with no operation returns `{ "operation": null }`; a missing profile remains a typed 404. Map duplicate start to HTTP 409 with `PROFILE_REEXTRACT_IN_PROGRESS` and the non-null `ProfileReextractInProgressDetail`. Preserve bounded SSE progress, and reject any emitted event whose profile ID differs from the route profile or whose operation ID differs from the first event.

`ProfileReextractionCoordinator.get_status()` owns the short transactional read. Reuse a session-level status projector from `profile_reextraction.py` in `GET /api/profile` so status/review reconciliation is implemented once and committed. `get_status()` loads only the deterministic latest operation for the requested profile, reconciles `review_ready` against captured profile/workspace revisions, and also CAS-transitions it to `stale` when its exact operation-owned draft is absent. Extend `reconcile_review_ready_to_stale` rather than creating a second stale rule. A `review_ready` status is therefore impossible without its exact draft and revision.

Lock this public matrix: `running` has no actions; `review_ready` has `can_review=true`, `can_retry=false`, `can_discard=true`; `interrupted` and `failed` are retryable only; `stale` with its exact draft is reviewable/discardable but not retryable until discard; `stale` without a draft is retryable only. Only an exact operation-owned draft supplies `review_revision`. `running`/`review_ready` expose null error fields; terminal states expose their bounded stored code and an allowlisted safe summary. Status payloads never expose attachment IDs, storage paths, source text, provider/prompt data, chunks, or document JSON.

`GET /api/profile` adds a nullable `reextract_operation` safe projection for the active profile and adds required nullable `operation_id` to `pending_review`. Validate `source="agent_update"` with null operation identity and `source="reextract"` with a non-null exact identity. Keep `pending_review` and `reextract_operation` as separate fields so an ordinary Agent review is never synthesized into an operation. Move the generic `SafeWarning` owner to `schemas/common.py` and re-export/import it from existing callers as needed before `profile.py` imports the operation status type; do not solve the schema cycle with `Any`, duplicate models, or deferred unvalidated dictionaries. Add the status route to `EXPECTED_PUBLIC_API_ROUTES` and `EXPECTED_ROUTE_CONTRACTS` in `tests/support/health.py`.

- [x] **Step 4: Run focused public-contract tests to verify they pass.**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_profiles_api.py tests/integration/test_profile_reextraction.py::test_api_rejects_crossed_missing_stale_and_replayed_operation_identity tests/integration/test_profile_reextraction.py::test_status_read_reconciles_review_ready_to_stale tests/integration/test_profile_reextraction.py::test_status_read_reconciles_review_ready_without_owned_draft_to_stale tests/integration/test_cv_api.py::test_get_profile_projects_correlated_reextract_operation tests/integration/test_health.py tests/integration/test_chat_api.py::test_public_routes_match_the_master_endpoint_inventory tests/unit/test_api_sse.py -q`

Expected: PASS; all five endpoints have strict schemas, duplicate start is a stable 409 without repeat work, and no API payload leaks retained-file or provider details.

- [x] **Step 5: Commit the public lifecycle contract.**

```powershell
git add backend/app/schemas/common.py backend/app/schemas/profile_reextraction.py backend/app/schemas/profile.py backend/app/repositories/profile_reextract_operations.py backend/app/services/profile_reextraction.py backend/app/api/profiles.py backend/app/api/profile.py backend/tests/support/health.py backend/tests/integration/test_cv_api.py backend/tests/integration/test_profiles_api.py backend/tests/integration/test_profile_reextraction.py backend/tests/unit/test_api_sse.py
git commit -m "feat: expose profile reextract operation api"
```

### Task 9: Make CV Manager recovery typed and independent of drawer close

**Files:**
- Modify: `frontend/src/features/cv-manager/types.ts`
- Modify: `frontend/src/features/cv-manager/api.ts`
- Modify: `frontend/src/features/cv-manager/state.ts`
- Modify: `frontend/src/features/cv-manager/ProfileReextractReview.tsx`
- Modify: `frontend/src/features/cv-manager/CvManagerDrawer.tsx`
- Modify: `frontend/src/test/cv-manager-api.test.ts`
- Modify: `frontend/src/test/cv-manager-reextract.test.tsx`

- [x] **Step 1: Write failing strict-parser, close, and recovery tests.**

```tsx
it('enforces review source and operation ownership', () => {
  expect(() => parseProfileReextractReview(Object.assign({}, staleReview, {operation_id: null}))).toThrow();
  expect(parseProfileReextractReview(Object.assign({}, agentReview, {source: 'agent_update', operation_id: null})).operation_id).toBeNull();
  expect(() => parseProfileReextractReview(Object.assign({}, staleReview, {can_approve: true}))).toThrow();
});

it('closing the drawer does not abort running re-extraction', async () => {
  render(<Harness />);
  await userEvent.click(screen.getByRole('button', {name: 'Re-extract'}));
  await userEvent.click(screen.getByRole('button', {name: 'Close'}));
  expect(streamAbort).not.toHaveBeenCalled();
  expect(await screen.findByText('Extracting the CV document')).toBeInTheDocument();
});
```

- [x] **Step 2: Run frontend parser/state tests to verify they fail.**

Run: `cd frontend; npm test -- --run src/test/cv-manager-api.test.ts src/test/cv-manager-reextract.test.tsx`

Expected: FAIL because the frontend does not parse operation status, stale correlation, or preserve the stream after close.

- [x] **Step 3: Implement strict operation parsers and status-first recovery state.**

```ts
export type ProfileReextractOperation = {
  profile_id: string;
  operation_id: string;
  state: 'running' | 'review_ready' | 'interrupted' | 'failed' | 'stale';
  error_code: string | null;
  error_summary: string | null;
  review_revision: string | null;
  can_review: boolean;
  can_retry: boolean;
  can_discard: boolean;
};

export type ProfileReextractOperationEnvelope = {
  operation: ProfileReextractOperation | null;
};

export async function getProfileReextractOperation(profileId: string, signal?: AbortSignal): Promise<ProfileReextractOperationEnvelope> {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}/reextract-operation`), {method: 'GET', headers: {Accept: 'application/json'}, signal});
  return parsedJson(response, parseProfileReextractOperationEnvelope);
}
```

Use the existing `apiUrl`, `parsedJson`, `ChatApiError`, and exact-key parsers. `parseProfileReextractOperationEnvelope` must require exactly the `operation` key and parse it as nullable; it must reject missing, extra, or malformed fields. The operation parser requires `error_code`, safe derived `error_summary`, and `review_revision`, rejecting the old generic `revision` key. Expand review, approve, and discard calls to carry `operation_id: string | null`. The review parser enforces `source="agent_update"` with null operation/state and `source="reextract"` with a non-null UUID/state; operation-linked state/action combinations remain strict. On CV Manager open, profile scope change, stream closure, and explicit refresh, fetch authoritative operation status before deciding whether to fetch a re-extraction review. `operation: null` is ordinary no-operation state, not an error and does not hide an independently projected Agent review. Change `close` so it only hides the drawer, restores focus through `CvManagerDrawer`, and leaves the re-extraction controller and stream intact. Abort only on unmount or actual active-profile scope replacement. Render `running`, `review_ready`, `interrupted`, `failed`, stale re-extraction review, and ordinary Agent review actions from parsed server flags/source; never treat stream completion as success.

- [x] **Step 4: Run focused CV Manager tests to verify they pass.**

Run: `cd frontend; npm test -- --run src/test/cv-manager-api.test.ts src/test/cv-manager-reextract.test.tsx src/test/cv-manager.test.tsx`

Expected: PASS; malformed and contradictory payloads are rejected, close/reopen and reload recover server truth, and stale review offers discard without save.

- [x] **Step 5: Commit frontend operation recovery.**

```powershell
git add frontend/src/features/cv-manager/types.ts frontend/src/features/cv-manager/api.ts frontend/src/features/cv-manager/state.ts frontend/src/features/cv-manager/ProfileReextractReview.tsx frontend/src/features/cv-manager/CvManagerDrawer.tsx frontend/src/test/cv-manager-api.test.ts frontend/src/test/cv-manager-reextract.test.tsx
git commit -m "feat: recover cv manager reextract operations"
```

### Task 10: Lock both upload inputs and give upload 409s a direct operation action

**Files:**
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/lib/api/chat.ts`
- Modify: `frontend/src/features/profile/CvSidebar.tsx`
- Modify: `frontend/src/features/profile/ProfileOverviewPanel.tsx`
- Modify: `frontend/src/features/profile/api.ts`
- Modify: `frontend/src/features/profile/types.ts`
- Modify: `frontend/src/features/chat/ChatPage.tsx`
- Modify: `frontend/src/test/cv-sidebar.test.tsx`
- Modify: `frontend/src/test/chat-page.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: Write failing App-level lock and direct-action tests.**

```tsx
it('disables sidebar and chat CV uploads while the active operation is running', async () => {
  render(<App deps={runningOperationDeps} />);
  expect(screen.getByLabelText('Upload CV from sidebar')).toBeDisabled();
  expect(screen.getByLabelText('Upload CV in chat')).toBeDisabled();
});

it('shows Check re-extraction beside a PROFILE_REEXTRACT_IN_PROGRESS upload error', async () => {
  render(<App deps={uploadConflictDeps} />);
  await userEvent.upload(screen.getByLabelText('Upload CV from sidebar'), pdfFile);
  await userEvent.click(screen.getByRole('button', {name: 'Check re-extraction'}));
  expect(openExistingCvManagerOperation).toHaveBeenCalledWith(ACTIVE_PROFILE_ID, OPERATION_ID);
  expect(startNewCvManagerReextract).not.toHaveBeenCalled();
  expect(startReextract).not.toHaveBeenCalled();
});

it('opens an ordinary Agent review without inventing an operation id', async () => {
  render(<App deps={agentReviewConflictDeps} />);
  await userEvent.upload(screen.getByLabelText('Upload CV from sidebar'), pdfFile);
  await userEvent.click(screen.getByRole('button', {name: 'Review changes'}));
  expect(openAgentPendingReview).toHaveBeenCalledWith(ACTIVE_PROFILE_ID, REVISION);
  expect(openExistingCvManagerOperation).not.toHaveBeenCalled();
  expect(startReextract).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run upload UX tests to verify they fail.**

Run: `cd frontend; npm test -- --run src/app/App.test.tsx src/test/cv-sidebar.test.tsx src/test/chat-page.test.tsx`

Expected: FAIL because `App` does not receive a durable operation lock and upload errors provide no exact pending-operation action.

- [ ] **Step 3: Wire the single CV Manager controller through `App` and both upload surfaces.**

```tsx
const cvManager = useCvManagerState({profileId: selectedProfile?.id ?? null, profileReady: selectedProfile?.state === 'ready'});
const reextractLocked = cvManager.state.reextract?.operation?.state === 'running';
const uploadLocked = workspaceLocked || tailoringLocked || reextractLocked;

<CvSidebar cvManager={cvManager} uploadDisabled={uploadLocked} onProfileReextractConflict={(operationId) => openExistingCvManagerOperation(selectedProfile?.id ?? null, operationId)} />
<ChatPage uploadDisabled={uploadLocked} onProfileReextractConflict={(operationId) => openExistingCvManagerOperation(selectedProfile?.id ?? null, operationId)} />
```

Lift the sole `useCvManagerState` call out of `CvSidebar` into `App`, pass its `CvManagerController` down to `CvSidebar` and the drawer, and delete the sidebar-owned hook call. Define three separate actions: `startNewCvManagerReextract(profileId)` invokes `cvManager.startReextract(profileId)` only after the user chooses Re-extract; `openExistingCvManagerOperation(profileId, operationId)` opens/refreshes that exact operation without calling start; and `openAgentPendingReview(profileId, reviewRevision)` loads the exact ordinary review with `operation_id=null`. Keep upload locks active only for `running`; interrupted and failed states permit uploads, while review-ready and stale-with-draft behavior follows server truth. `PROFILE_REEXTRACT_IN_PROGRESS` renders **Check re-extraction** and requires the non-null operation detail. `PROFILE_REVIEW_PENDING` renders **Review changes**: `review_source="reextract"` opens its operation, while `review_source="agent_update"` opens the exact profile/revision ordinary review. No 409 action may call `startNewCvManagerReextract` or start a second extraction. Extend `ChatApiError` and `parseErrorBody` in `frontend/src/lib/api/chat.ts` to preserve the safe structured detail consumed by `profile/api.ts`; then make `profile/types.ts` strictly validate the `PROFILE_REEXTRACT_IN_PROGRESS` and `PROFILE_REVIEW_PENDING` unions, including source/nullability/revision invariants. Preserve existing `code`/`summary` behavior for unrelated callers and do not infer operation identity from local profile lists.

- [ ] **Step 4: Run focused App and upload-control tests to verify they pass.**

Run: `cd frontend; npm test -- --run src/app/App.test.tsx src/test/cv-sidebar.test.tsx src/test/chat-page.test.tsx src/test/cv-manager-reextract.test.tsx`

Expected: PASS; both controls lock together, direct 409 actions open the correlated operation, terminal retryable failures re-enable upload, and inactive archived items have no Re-extract control.

- [ ] **Step 5: Commit shared upload behavior.**

```powershell
git add frontend/src/app/App.tsx frontend/src/lib/api/chat.ts frontend/src/features/profile/CvSidebar.tsx frontend/src/features/profile/ProfileOverviewPanel.tsx frontend/src/features/profile/api.ts frontend/src/features/profile/types.ts frontend/src/features/chat/ChatPage.tsx frontend/src/test/cv-sidebar.test.tsx frontend/src/test/chat-page.test.tsx frontend/src/app/App.test.tsx
git commit -m "fix: lock cv uploads during reextract"
```

### Task 11: Add fail-closed volume snapshot, clone smoke check, and release procedure

**Files:**
- Create: `infrastructure/scripts/app_data_snapshot.ps1`
- Create: `infrastructure/scripts/test_app_data_snapshot.ps1`
- Create: `backend/app/services/profile_reextract_migration_smoke.py`
- Modify: `backend/tests/integration/test_graph_rebuild_cli.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Create: `docs/operations/profile-reextract-release.md`

- [x] **Step 1: Write failing PowerShell contract checks and smoke test.**

```powershell
$script = Join-Path $PSScriptRoot 'app_data_snapshot.ps1'
Assert-Throws { & $script -Action Backup -ProjectName jobagentlatest -VolumeName wrong_volume -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath (Join-Path $env:TEMP 'outside.tar') }
Assert-Throws { & $script -Action Verify -ProjectName jobagentlatest -VolumeName jobagentlatest_app_data -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath (Join-Path $env:TEMP 'outside.tar') }
Assert-Contains (Get-Content -Raw $script) '[ValidateSet(''Backup'', ''Restore'', ''Verify'')]'
Assert-NotContains (Get-Content -Raw $script) 'down -v'
```

```python
def test_migration_smoke_reports_expected_inventory_without_network(monkeypatch: pytest.MonkeyPatch, migrated_sqlite: Path) -> None:
    import httpx
    monkeypatch.setattr(httpx.Client, "request", pytest.fail)
    monkeypatch.setattr(httpx.AsyncClient, "request", pytest.fail)
    result = run_smoke(sqlite_path=migrated_sqlite)
    assert result.alembic_revision == "0008_profile_reextract_ownership"
    assert result.foreign_key_check == []
```

- [x] **Step 2: Run utility/static checks to verify they fail.**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/test_app_data_snapshot.ps1`

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_graph_rebuild_cli.py::test_migration_smoke_reports_expected_inventory_without_network tests/integration/test_migrations.py::test_0008_is_the_migration_head -q`

Expected: FAIL because the snapshot utility and migration smoke module do not exist.

- [x] **Step 3: Implement Backup, Restore, Verify, and read-only smoke contracts.**

```powershell
param(
  [Parameter(Mandatory = $true)][ValidateSet('Backup', 'Restore', 'Verify')][string]$Action,
  [Parameter(Mandatory = $true)][string]$ProjectName,
  [Parameter(Mandatory = $true)][string]$VolumeName,
  [string]$ExpectedConsumer,
  [string]$ExpectedPurpose,
  [Parameter(Mandatory = $true)][string]$ArchivePath,
  [string]$ExpectedArchiveSha256,
  [string]$ExpectedAlembicRevision,
  [switch]$ConfirmRestore
)
```

Require `jobagentlatest`, reject archive and manifest paths inside the repository worktree, and reject a missing or incorrect expected consumer or clone purpose. `Backup` requires a stopped backend, has no `ExpectedArchiveSha256` parameter requirement, writes an archive plus manifest outside the worktree, and records SHA-256, archive size, full relative-path inventory, SQLite/WAL/SHM presence, table counts, active profile, pending action, and Alembic revision. `Restore` and `Verify` require `ExpectedArchiveSha256`; `Restore` also requires `ConfirmRestore`. Validate authoritative volume name and Compose label separately from the exact expected consumer, and validate clone label `jobagent.release.purpose=plan18-rehearsal` separately from source-volume rules. Restore through a temporary directory and replace only after complete inventory/hash validation. The smoke module must open the supplied SQLite path read-only, report revision/table/file/profile/pending-action parity, verify profile-draft and operation schema metadata, and run `PRAGMA foreign_key_check` without provider, filesystem write, or network use.

- [x] **Step 4: Run focused snapshot and smoke checks to verify they pass.**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/test_app_data_snapshot.ps1`

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/integration/test_graph_rebuild_cli.py::test_migration_smoke_reports_expected_inventory_without_network tests/integration/test_migrations.py::test_0008_preserves_valid_draft_schema_rows_and_json tests/integration/test_migrations.py::test_0008_is_the_migration_head -q`

Expected: PASS; Backup accepts no expected hash, Verify/Restore reject absent or incorrect expected hashes, private-output checks fail closed, and smoke remains provider-free and read-only.

- [x] **Step 5: Write and verify the exact release/rehearsal/rollback procedure.**

```powershell
$ComposeArgs = @('--env-file', '.env', '-f', 'infrastructure/docker-compose.yml', '-p', 'jobagentlatest')
$ReleaseSha = (git rev-parse --short=12 HEAD).Trim()
$AppVolume = 'jobagentlatest_app_data'
$CloneVolume = 'jobagentlatest_app_data_plan18_rehearsal'
$BackupRoot = Join-Path $HOME 'JobAgentBackups'
$BackupArchive = Join-Path $BackupRoot "jobagentlatest-plan18-$ReleaseSha.tar"
docker compose @ComposeArgs config --services
```

In `docs/operations/profile-reextract-release.md`, require exactly `backend`, `frontend`, and `neo4j` before every release action. Record and tag running backend/frontend image IDs before build; stop backend; run `Backup` without an expected hash; calculate `$BackupSha256`; build `backend frontend` using `docker compose @ComposeArgs build --pull`; tag candidate IDs after build; create the labelled clone; and restore it using `ExpectedArchiveSha256`. Keep backend stopped continuously from backup through networkless clone migration rehearsal and candidate cutover. Do not run a browser test before candidate cutover. At cutover reverify authoritative volume and consumer separately, stop frontend, recreate only backend/frontend with `up -d --wait --wait-timeout 180 --force-recreate`, then immediately inspect the deployed backend/frontend image IDs and require equality with the rehearsed candidate IDs before health, browser, or log checks. Roll back immediately on image-ID mismatch, migration, health, inventory, browser, or log failure. Rollback stops frontend/backend, restores the verified full source-volume snapshot, restores pre-release tags, restarts backend/frontend, checks the old revision and inventory, then rebuilds the derived graph. The procedure must not use `docker compose down -v`.

- [x] **Step 6: Commit snapshot and release assets.**

```powershell
git add infrastructure/scripts/app_data_snapshot.ps1 infrastructure/scripts/test_app_data_snapshot.ps1 backend/app/services/profile_reextract_migration_smoke.py backend/tests/integration/test_graph_rebuild_cli.py backend/tests/integration/test_migrations.py docs/operations/profile-reextract-release.md
git commit -m "feat: add profile reextract release rehearsal"
```

### Task 12: Run complete source, clone, browser, and release acceptance evidence

**Files:**
- Modify: `docs/operations/profile-reextract-release.md`
- Modify: `README.md`
- Create: `docs/acceptance/profile-reextract-operation-evidence.md`

- [ ] **Step 1: Add failing acceptance ledger checks for required evidence rows.**

```powershell
$evidence = Get-Content -Raw 'docs/acceptance/profile-reextract-operation-evidence.md'
@('migration-upgrade', 'downgrade-refusal', 'duplicate-claim', 'upload-race', 'pool-cleanliness', 'clone-rehearsal', 'candidate-browser', 'rollback') | ForEach-Object {
  if ($evidence -notmatch [regex]::Escape($_)) { throw "missing evidence row: $_" }
}
```

- [ ] **Step 2: Run the acceptance ledger check to verify it fails.**

Run: `powershell -NoProfile -Command "$evidence = Test-Path 'docs/acceptance/profile-reextract-operation-evidence.md'; if (-not $evidence) { throw 'profile reextract acceptance ledger is missing' }"`

Expected: FAIL because the acceptance ledger does not exist.

- [ ] **Step 3: Document and execute the full validation sequence on synthetic data only.**

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m mypy app
cd ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

After all source gates pass, follow `docs/operations/profile-reextract-release.md` exactly: back up the stopped authoritative volume, tag pre-release images before build and candidate images after build, restore and rehearse the labelled clone, perform candidate cutover, verify the deployed image IDs equal the rehearsed candidate IDs, then run the browser flow against synthetic PDFs. Capture screenshots for running re-extraction, both disabled upload controls, direct 409 action, close/reopen, reload recovery, stale review, discard, retry, approval, active-CV lineage, narrow viewport, and keyboard focus restoration. Collect `docker compose @ComposeArgs logs --no-color backend frontend` after browser acceptance and fail on `Traceback`, `no active connection`, `checked out`, `pool`, or an unexpected ` 5xx `. On any post-cutover failure, perform the documented rollback immediately before any further browser attempt. Keep full commands, screenshot files, manifest inventory, filenames, local hashes, archive paths, and user paths outside Git. The tracked ledger may contain only synthetic case IDs, counts, redacted image-ID suffixes or non-reversible hashes where needed, pass/fail codes, UTC timestamps, and non-sensitive artifact handles; it must not contain private screenshot paths, manifest paths, inventory, filenames, local file hashes, or user paths.

- [ ] **Step 4: Run the final local static checks and whitespace check.**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/test_app_data_snapshot.ps1`

Run: `powershell -NoProfile -Command "$p = 'T[B]D|T[O]DO|\.{3}|all[ ]files[ ]above|implement[ ]the[ ]lifecycle'; rg -n -i -- $p docs/superpowers/plans/2026-07-31-profile-reextract-operation.md; if ($LASTEXITCODE -ne 1) { exit 1 }"`

Run: `rg -n -S "DocumentPublicationArtifacts|upsert_draft\(|ImmediateTransactionBusy|ProfileReextractOperationConflict|ProfileReextractInProgressDetail|ProfileReviewPendingDetail|ProfileReextractOperationStatus|ProfileReextractOperationEnvelope|error_summary|review_revision|useCvManagerState|run_smoke\(sqlite_path" docs/superpowers/plans/2026-07-31-profile-reextract-operation.md`

Run: `git add -N docs/acceptance/profile-reextract-operation-evidence.md; git diff --check -- docs/acceptance/profile-reextract-operation-evidence.md; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`

Expected: the utility tests pass; the placeholder scan returns exit code 1 with no matches; the Windows-safe intent-to-add `git diff --check` exits 0 with no whitespace error.

- [ ] **Step 5: Commit the acceptance documentation.**

```powershell
git add docs/operations/profile-reextract-release.md README.md docs/acceptance/profile-reextract-operation-evidence.md
git commit -m "docs: record profile reextract acceptance evidence"
```

## Completion Criteria

- Migration `0008_profile_reextract_ownership` is the only schema change and preserves valid data while refusing unsafe forward or reverse mutation.
- Direct re-extraction claims before SSE, retained-file work, or provider work; duplicate requests produce one expensive execution and HTTP 409 `PROFILE_REEXTRACT_IN_PROGRESS`.
- Publication, review reconciliation, approval, discard, Agent correction, upload, activation, and deletion use explicit profile and operation ownership with the required compare-and-swap revisions.
- No database session spans retained-file access, provider calls, SSE yield, Neo4j work, or cancellation finalization.
- CV Manager recovery is authoritative after close, reload, disconnect, and restart; `App` locks sidebar and chat uploads together and provides correlated pending actions.
- Compose remains exactly `frontend`, `backend`, and `neo4j`; release uses a private full-volume backup, labelled clone rehearsal, candidate tags, immediate rollback on post-cutover failure, and never `down -v`.
