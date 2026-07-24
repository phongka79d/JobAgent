# CV Profiles and Multi-Conversation Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the singleton CV/profile/conversation workflow with durable CV-backed profiles, persisted extraction reuse, and isolated selectable/deletable conversations per profile.

**Architecture:** SQLite remains the authoritative owner of pending/ready profiles, retained CV attachments, extracted documents/chunks, preferences, conversations, messages, runs, tools, and profile-scoped evaluations. A new upload atomically creates one pending profile and bootstrap conversation before extraction; approval promotes that same identity to ready. A singleton `workspace_state` row selects the workspace profile, while every approved-data consumer separately requires ready state and every chat request resolves its profile/CV ownership from the conversation ID. Neo4j remains a rebuildable, ready-profile-keyed projection. The React shell owns profile/conversation selection above the existing single ChatPage/SSE reducer, using Astryx navigation rows, tags, menus, and confirmation dialogs.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy/aiosqlite, Alembic, LangGraph checkpoints, Neo4j, Pytest, Ruff, Mypy, React 19, TypeScript, Vite, Vitest, Astryx 0.1.4, PowerShell, Docker Compose.

---

## Scope and invariants

- This remains one plan because no subsystem is independently shippable: the profile/conversation IDs are introduced by one destructive schema, and backend ownership, graph identity, frontend hydration, and deletion semantics must change together to prevent cross-profile data exposure. The tasks are still independently committed and testable in dependency order.
- The approved design at `docs/superpowers/specs/2026-07-23-cv-profile-conversation-design.md` is the authority for this plan. Existing singleton-oriented README text and tests are replaced as part of the implementation; no compatibility migration is added.
- A retained CV attachment belongs to exactly one profile. A pending profile owns no approved extraction; a ready profile owns one persisted extraction revision. Every profile owns its durable conversations. Selecting a ready profile or conversation performs SQLite reads/selection only: zero extraction, LLM, embedding, scoring, filesystem-write, or provider calls.
- A new unique CV upload creates one pending profile and one empty `Chat mới` bootstrap conversation before extraction. First approval promotes that same row, adds profile preferences and approved extraction facts, preserves the conversation ID, and activates the attachment. Explicit re-extraction targets an existing ready profile, preserves all conversation IDs, and is approval-gated.
- `workspace_state.active_profile_id` is the selected profile pointer and may temporarily reference the one pending profile. Approved context, matching, evaluation, observability, and graph code must also require `Profile.state == "ready"`.
- `POST /api/profiles/{profile_id}/reextract` is the profile-owned re-extraction route. It uses the existing SSE vocabulary and the existing ChatPage stream owner; the server derives the attachment and selected conversation and never accepts client CV/profile JSON.
- Conversation and profile deletion are permanent. Every UI delete uses an Astryx `AlertDialog`; the backend repeats ownership/activity checks and never trusts a client confirmation string.
- A running or interrupted run blocks profile switching, conversation switching/creation/deletion, and profile deletion. The backend gate is authoritative; the frontend lock is only an affordance.
- Saved Jobs remain global. Evaluation rows carry `profile_id` and are never displayed as current for another profile.
- The rollout is destructive by explicit choice: the new migration refuses non-empty legacy application data, and the documented release procedure removes the disposable SQLite/retained-file/Neo4j volumes before startup. LangGraph checkpoint tables are never owned by Alembic.
- Astryx is the only new visual system. New layout uses `AppShell`, `SideNav`, `List`/`ListItem`, Stack primitives, `Token`, `DropdownMenu`, `Dialog`, `AlertDialog`, and `MobileNav`; no new `<div>` layout, raw hex/px values, or second stream store is allowed.

## Frozen cross-layer contracts

Define these names once in the first implementation tasks and reuse them in every later task:

~~~python
# backend/app/db/models/profiles.py
PROFILE_STATE_READY = "ready"
PROFILE_STATE_PENDING = "pending"
PROFILE_STATE_DELETING = "deleting"
PROFILE_STATES = frozenset({
    PROFILE_STATE_PENDING,
    PROFILE_STATE_READY,
    PROFILE_STATE_DELETING,
})
PROFILE_SETUP_STATUS_AWAITING_EXTRACTION = "awaiting_extraction"
PROFILE_SETUP_STATUS_AWAITING_APPROVAL = "awaiting_approval"
PROFILE_SETUP_STATUS_EXTRACTION_FAILED = "extraction_failed"
WORKSPACE_STATE_ID = "main"
PROFILE_DISPLAY_NAME_MAX = 120
CONVERSATION_TITLE_MAX = 120
PROFILE_SKILL_TAG_LIMIT = 12
NEW_CONVERSATION_TITLE = "Chat mới"
~~~

~~~python
# backend/app/services/conversation_titles.py
def derive_conversation_title(message: str) -> str:
    normalized = " ".join(message.split())
    if not normalized:
        return NEW_CONVERSATION_TITLE
    return normalized[:CONVERSATION_TITLE_MAX].rstrip() or NEW_CONVERSATION_TITLE
~~~

The public profile projection contains only safe, persisted fields:

~~~text
ProfileListItem:
  id, display_name, cv_filename, attachment_state, location,
  skill_tags[{key, label}], skill_count, extraction_version,
  source_hash, state, setup_status, is_active,
  created_at, updated_at, last_opened_at
  pending rows: location/extraction_version/source_hash null,
                skill_tags [], skill_count 0,
                setup_status awaiting_extraction | awaiting_approval |
                             extraction_failed
  ready rows: setup_status null
ProfileDetail:
  ready ProfileListItem fields + profile (validated CandidateProfile),
  preferences (validated JobPreferences), attachment metadata,
  selected_conversation_id
ConversationSummary:
  id, profile_id, title, created_at, updated_at, last_opened_at, is_selected
SelectionResponse:
  profile (ProfileDetail), conversation (ConversationSummary | null)
~~~

Stable error codes are defined in one backend module and mirrored as a TypeScript string union:

~~~text
PROFILE_NOT_FOUND, PROFILE_NOT_READY, PROFILE_SWITCH_BLOCKED,
PROFILE_DELETE_BLOCKED, PROFILE_SETUP_IN_PROGRESS, CONVERSATION_NOT_FOUND,
CONVERSATION_PROFILE_MISMATCH, CONVERSATION_SWITCH_BLOCKED,
CONVERSATION_DELETE_BLOCKED, RUN_PROFILE_MISMATCH,
NO_ACTIVE_PROFILE, INVALID_DISPLAY_NAME, PROFILE_INCONSISTENT
~~~

The following response/request contracts are the implementation target:

~~~python
class ProfileListResponse(BaseModel):
    items: list[ProfileListItem]
    active_profile_id: UuidStr | None

class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]
    next_cursor: str | None

class ProfileUpdateRequest(BaseModel):
    model_config = StrictModelConfig
    display_name: str = Field(min_length=1, max_length=PROFILE_DISPLAY_NAME_MAX)

class SafeWarning(BaseModel):
    code: str
    summary: str
    guidance: str

class SelectionResponse(BaseModel):
    profile: ProfileDetail
    conversation: ConversationSummary | None
    warning: SafeWarning | None = None
~~~

Upload bootstrap uses the same server-owned profile/conversation identifiers:

~~~python
class PendingProfileBootstrap(BaseModel):
    model_config = StrictModelConfig
    profile: ProfileListItem
    conversation: ConversationSummary
    start_extraction: bool

class CvUploadResponse(BaseModel):
    model_config = StrictModelConfig
    attachment: AttachmentPublic
    outcome: Literal[
        "new_pending", "retry_pending", "existing_pending",
        "existing_active", "existing_profile",
    ]
    profile: ProfileUploadSummary | None = None
    draft: DraftUploadSummary | None = None
    bootstrap: PendingProfileBootstrap | None = None
~~~

Define the remaining shared types before implementing repositories/routes so later tasks use the same names:

~~~python
class ConversationQuery(BaseModel):
    model_config = StrictModelConfig
    limit: int = Field(default=50, ge=1, le=100)
    before: str | None = None

@dataclass(frozen=True)
class ConversationListPage:
    rows: list[Conversation]
    next_cursor: str | None

@dataclass(frozen=True)
class ConversationOwner:
    conversation_id: str
    profile_id: str
    attachment_id: str

class ConversationMutationResponse(BaseModel):
    conversation: ConversationSummary

class ConversationDeleteResponse(BaseModel):
    deleted_conversation_id: UuidStr
    selected_conversation: ConversationSummary
    replacement_conversation_id: UuidStr | None

class ProfileDeleteResponse(BaseModel):
    deleted_profile_id: UuidStr
    active_profile: ProfileListItem | None
    selected_conversation: ConversationSummary | None

@dataclass(frozen=True)
class ConversationDeleteResult:
    deleted_conversation_id: str
    selected_conversation_id: str
    replacement_conversation_id: str | None
~~~

ConversationListPage, ConversationOwner, and ConversationDeleteResult are internal repository/service types and belong outside Pydantic schema modules; schema modules must not import ORM classes. The API serializes rows into ConversationListResponse. ConversationOwner is the only accepted source for profile/attachment context in a turn or resume. ConversationDeleteResponse always contains the server-selected replacement/current conversation, and only sets replacement_conversation_id when the deleted row was the last one.

`PATCH /api/profiles/{profile_id}` accepts exactly `{"display_name": "Ada Lovelace"}`. `POST /api/profiles/{profile_id}/reextract` accepts an empty object only and returns SSE. Conversation history/turn routes are scoped by path ID; resume remains `/api/chat/runs/{run_id}/resume` but resolves ownership durably.

## File map and ownership

| Area | Files to create or modify | Responsibility |
| --- | --- | --- |
| Schema/persistence | backend/app/db/models/profiles.py, chat.py, job_evaluations.py, db/seed.py, migrations/versions/0005_cv_profiles_multi_conversation.py | Pending/ready profile shapes, multi-row preferences/conversations, workspace selection, destructive fresh-schema reset |
| Repositories/gates | backend/app/repositories/profiles.py, new workspace_state.py, new conversations.py, chat_messages.py, agent_runs.py, job_evaluations.py, new services/activity_gate.py, new services/conversation_titles.py | ID-scoped reads/writes, ownership resolution, deterministic selection, run activity checks |
| Profile lifecycle | new backend/app/api/profiles.py, new backend/app/api/conversations.py, existing api/profile.py, main.py, schemas/profile_setup.py, services/profile_approval.py, profile_drafts.py, profile_activation.py, cv_upload.py | Safe pending bootstrap/list DTOs, activation, rename, in-place approval promotion, re-extraction, staged upload |
| Chat ownership | backend/app/services/chat_turns.py, chat_history.py, job_save_confirmation.py, agent/state.py, agent/graph.py, agent/context.py, agent/active_cv_context.py, services/active_cv_reader.py | Conversation/profile context, title update, run resume, no cross-owner history |
| Deletion | new backend/app/services/conversation_deletion.py, new profile_deletion.py, graph/delete_profile.py, existing CV cleanup modules | Checkpoint/file/graph/SQLite ordering and retryable state |
| Evaluation/graph | services/evaluation_context.py, job_evaluation.py, saved_jobs.py, matching.py, graph/sync_candidate.py, sync_cv.py, consistency.py, observability*.py, rebuild*.py, selected_skill_projection.py | Profile-keyed evaluations and Candidate/CV graph branches |
| Frontend transport/state | frontend/src/features/profile/types.ts, api.ts, new workspaceState.ts, frontend/src/lib/api/chat.ts, features/chat/model.ts, ChatPage.tsx, app/App.tsx | Strict DTO parsing, server-truth selection, keyed single reducer/SSE hydration |
| Frontend Astryx UI | new ProfileConversationSidebar.tsx, ProfileListPanel.tsx, ConversationListPanel.tsx, ProfileRenameDialog.tsx, ProfileDeleteDialog.tsx, ConversationDeleteDialog.tsx, existing profile/observability components | Metadata tags, menus, dialogs, mobile drawer, lock propagation |
| Verification/docs | backend/frontend tests, docs/operations/cv-profile-multi-conversation-rollout.md, docs/acceptance/cv-profile-multi-conversation-checklist.md | Contract, isolation, reset, full-gate, and browser evidence |

---

### Task 1: Add source-grounded identity fields and the destructive schema contract

**Files:**
- Modify: backend/app/schemas/profile.py
- Create: backend/app/services/profile_identity_guard.py
- Modify: backend/app/db/models/profiles.py, chat.py, job_evaluations.py
- Modify: backend/app/db/models/__init__.py
- Create: backend/migrations/versions/0005_cv_profiles_multi_conversation.py
- Modify: backend/app/db/seed.py
- Modify: backend/tests/support/db_migration.py, backend/tests/support/schema_parity.py
- Test: backend/tests/unit/test_profile_schemas.py, backend/tests/unit/test_profile_identity_guard.py, backend/tests/unit/test_attachment_profile_models.py, backend/tests/unit/test_chat_models.py, backend/tests/integration/test_migrations.py, backend/tests/integration/test_database_contract.py

- [x] **Step 1: Write failing identity and model-contract tests**

Add backend/tests/unit/test_profile_identity_guard.py with a source-grounding matrix:

~~~python
def test_identity_guard_keeps_only_values_present_in_source_fragments() -> None:
    profile = CandidateProfile.model_validate(
        _profile(full_name="Ada Lovelace", location="London")
    )
    guarded = guard_optional_identity_fields(
        profile,
        source_fragments=("Ada Lovelace", "Software engineer", "London, UK"),
    )
    assert guarded.full_name == "Ada Lovelace"
    assert guarded.location == "London"

def test_identity_guard_nulls_inferred_or_unsupported_values() -> None:
    profile = CandidateProfile.model_validate(
        _profile(full_name="Invented Name", location="Mars")
    )
    guarded = guard_optional_identity_fields(
        profile, source_fragments=("Backend engineer",)
    )
    assert guarded.full_name is None
    assert guarded.location is None
~~~

Extend the exact-field tests so `CandidateProfile` includes optional `full_name` and `location`, rejects unknown fields, accepts `None`, and preserves strict validation. Add model tests asserting `Profile.attachment_id` is unique/non-null, `WorkspaceState.id` is fixed to `main`, `Conversation.profile_id` is non-null, and `JobEvaluation.profile_id` participates in the named unique constraint.

- [x] **Step 2: Run the new tests to verify RED**

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_identity_guard.py tests/unit/test_profile_schemas.py tests/unit/test_attachment_profile_models.py tests/unit/test_chat_models.py -q
~~~

Expected: collection or assertions fail because the new models, fields, and guard do not yet exist.

- [x] **Step 3: Extend the validated profile contract and add the pure guard**

In backend/app/schemas/profile.py, add the fields before the existing summary fields:

~~~python
class CandidateProfile(BaseModel):
    model_config = StrictModelConfig

    full_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    summary: str
    current_title: str | None
    total_experience_years: float | None
    skills: list[CandidateSkill]
    experiences: list[ExperienceItem]
    education: list[EducationItem]
    languages: list[LanguageItem]
    extraction_confidence: float = Field(ge=0.0, le=1.0)
~~~

Create profile_identity_guard.py with no ORM/provider imports:

~~~python
from collections.abc import Sequence
import re
from app.schemas.profile import CandidateProfile

_SPACE_RE = re.compile(r"\s+")

def _normalized(value: str) -> str:
    return _SPACE_RE.sub(" ", value.casefold()).strip()

def guard_optional_identity_fields(
    profile: CandidateProfile,
    *,
    source_fragments: Sequence[str],
) -> CandidateProfile:
    source = _normalized(" ".join(item for item in source_fragments if item))
    updates: dict[str, str | None] = {}
    for field_name in ("full_name", "location"):
        value = getattr(profile, field_name)
        if value is not None and _normalized(value) not in source:
            updates[field_name] = None
    return profile.model_copy(update=updates)
~~~

Call this guard only after the document extractor has supplied direct source fragments; never derive a name/location from filename, email, phone, or street-address fields.

- [x] **Step 4: Replace singleton ORM contracts with first-class rows**

Replace the singleton `CandidateProfile` ORM class with `Profile(__tablename__="profiles")`, add `ProfilePreference(__tablename__="profile_preferences")` and `WorkspaceState(__tablename__="workspace_state")` in profiles.py, and replace `Conversation` in chat.py with `__tablename__ = "conversations"` and a UUID default. Keep `ProfileDraft` as the one pending approval row but add nullable `target_profile_id` with `ondelete="CASCADE"`. Remove `CONVERSATION_ID`, `CANDIDATE_PROFILE_ID`, and `JOB_PREFERENCES_ID` from production callers; retain only `WORKSPACE_STATE_ID = "main"` for the workspace singleton.

Use these exact new columns:

~~~text
profiles: id, attachment_id, display_name, profile_json, location,
          extraction_version, source_hash, state, created_at, updated_at,
          last_opened_at
profile_preferences: profile_id, preferences_json, created_at, updated_at
workspace_state: id, active_profile_id, updated_at
conversations: id, profile_id, title, created_at, updated_at, last_opened_at
~~~

Keep the existing message/run/tool status checks and indexes, but point `chat_messages.conversation_id` to `conversations.id`. Change evaluation uniqueness to `(job_id, profile_id, evaluation_context_hash)` and add `profile_id` to its index/FK set.

- [x] **Step 5: Create the guarded 0005 migration**

Create backend/migrations/versions/0005_cv_profiles_multi_conversation.py with revision `0005_cv_profiles_multi_conversation` and down revision `0004_add_job_evaluations`. Before any drop, run this exact preflight pattern through `op.get_bind()`:

~~~python
_LEGACY_DATA_TABLES = (
    "attachments", "attachment_text_chunks", "cv_documents",
    "cv_document_drafts", "candidate_profile", "profile_drafts",
    "job_posts", "chat_messages", "agent_runs", "tool_executions",
    "job_evaluations",
)

def _assert_reset_workspace(bind: sa.Connection) -> None:
    checks = {
        table: int(bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
        for table in _LEGACY_DATA_TABLES
    }
    seed_conversation = int(
        bind.execute(sa.text("SELECT COUNT(*) FROM conversation WHERE id <> 'main'")).scalar_one()
    )
    seed_preferences = int(
        bind.execute(sa.text("SELECT COUNT(*) FROM job_preferences WHERE id <> 'active'")).scalar_one()
    )
    if any(checks.values()) or seed_conversation or seed_preferences:
        raise RuntimeError(
            "0005 requires an empty JobAgent workspace; run the documented "
            "Compose volume reset before upgrading"
        )
~~~

After the guard, drop the actual 0004 table names in dependency order (`tool_executions`, `agent_runs`, `chat_messages`, `job_evaluations`, `conversation`, `job_preferences`, `candidate_profile`, `profile_drafts`) and recreate the accepted metadata with explicit `op.create_table`/`op.create_index` calls for `profiles`, `profile_preferences`, `workspace_state`, `conversations`, and the dependent chat/evaluation tables. Do not call `Base.metadata.create_all()` and do not touch tables whose names start with `checkpoint` or `langgraph_`. Create `workspace_state(main, NULL, CURRENT_TIMESTAMP)` and no profile/conversation rows; startup seeds only the workspace row idempotently.

- [x] **Step 6: Update migration/parity harnesses and run schema tests**

Set `MIGRATION_HEAD = "0005_cv_profiles_multi_conversation"`, replace `APPLICATION_TABLE_NAMES` with the new table set, update expected constraint/index counts from the metadata oracle rather than hard-coded old values, and replace singleton assertions with:

~~~python
assert counts["profiles"] == 0
assert counts["profile_preferences"] == 0
assert counts["conversations"] == 0
assert counts["workspace_state"] == 1
assert active_profile_id is None
~~~

Add tests proving a non-empty legacy attachment database raises the reset guidance error, an empty full migration has no extraction/provider calls, and checkpoint-like tables survive unchanged.

Run:

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_identity_guard.py tests/unit/test_profile_schemas.py tests/unit/test_attachment_profile_models.py tests/unit/test_chat_models.py tests/integration/test_migrations.py tests/integration/test_database_contract.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app migrations tests --no-cache
~~~

Expected: all focused tests pass, parity covers the replacement tables, and no migration creates profile data or calls a provider.

- [x] **Step 7: Commit the schema foundation**

~~~powershell
Set-Location ..
git add backend/app/schemas/profile.py backend/app/services/profile_identity_guard.py backend/app/db/models/profiles.py backend/app/db/models/chat.py backend/app/db/models/job_evaluations.py backend/app/db/models/__init__.py backend/app/db/seed.py backend/migrations/versions/0005_cv_profiles_multi_conversation.py backend/tests/support/db_migration.py backend/tests/support/schema_parity.py backend/tests/unit/test_profile_identity_guard.py backend/tests/unit/test_profile_schemas.py backend/tests/unit/test_attachment_profile_models.py backend/tests/unit/test_chat_models.py backend/tests/integration/test_migrations.py backend/tests/integration/test_database_contract.py
git commit -m "feat: add profile and conversation schema"
~~~

---

### Task 2: Implement ID-scoped repositories, workspace selection, titles, and the activity gate

**Files:**
- Modify: backend/app/repositories/profiles.py
- Create: backend/app/repositories/workspace_state.py, backend/app/repositories/conversations.py
- Modify: backend/app/repositories/chat_messages.py, agent_runs.py, job_evaluations.py
- Create: backend/app/services/conversation_titles.py, backend/app/services/activity_gate.py
- Modify: backend/app/db/seed.py, backend/app/main.py
- Test: backend/tests/unit/test_conversation_titles.py, backend/tests/unit/test_activity_gate.py, backend/tests/integration/test_profile_selection.py, backend/tests/integration/test_chat_persistence.py

- [x] Step 1: Add failing repository and gate tests

Seed two profiles, three conversations, and one running/interrupted run, then assert all operations are scoped:

~~~python
async def test_recent_conversation_is_selected_by_last_opened_timestamp(session):
    selected = await conversation_repo.most_recent_for_profile(
        session, profile_id=PROFILE_A
    )
    assert selected.id == CONVERSATION_A_2

async def test_gate_rejects_running_and_interrupted_runs(session):
    with pytest.raises(ActivityBlockedError) as exc:
        await assert_workspace_idle(session)
    assert exc.value.code == "PROFILE_SWITCH_BLOCKED"
~~~

Add a message repository test showing that list_messages_before with conversation B never returns conversation A rows, and a run ownership test resolving run ID -> message -> conversation -> profile.

- [x] Step 2: Run the tests to verify RED

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_conversation_titles.py tests/unit/test_activity_gate.py tests/integration/test_profile_selection.py tests/integration/test_chat_persistence.py -q
~~~

Expected: missing-module/signature failures and singleton rows prevent the new tests from passing.

- [x] Step 3: Add deterministic title and profile repository primitives

Create conversation_titles.py with the frozen derive_conversation_title implementation from the contract. Refactor profiles.py to expose these exact operations without opening or committing sessions:

~~~python
async def get_profile(session: AsyncSession, profile_id: str) -> Profile | None:
    return await session.get(Profile, profile_id)

async def list_profiles(session: AsyncSession) -> list[Profile]:
    result = await session.execute(
        select(Profile).order_by(
            Profile.last_opened_at.desc(),
            Profile.updated_at.desc(),
            Profile.id.desc(),
        )
    )
    return list(result.scalars().all())

async def create_profile(
    session: AsyncSession,
    *,
    attachment_id: str,
    display_name: str,
    profile_json: dict[str, Any],
    location: str | None,
    extraction_version: str,
    source_hash: str,
) -> Profile:
    now = utc_now()
    row = Profile(
        id=new_uuid(),
        attachment_id=attachment_id,
        display_name=display_name,
        profile_json=profile_json,
        location=location,
        extraction_version=extraction_version,
        source_hash=source_hash,
        state=PROFILE_STATE_READY,
        created_at=now,
        updated_at=now,
        last_opened_at=now,
    )
    session.add(row)
    await session.flush()
    return row
~~~

Add update_display_name, get_profile_preferences, and upsert_profile_preferences with the same session/flush ownership. Reject whitespace-only IDs/names before SQL.

- [x] Step 4: Add workspace and conversation repositories

Create workspace_state.py with get_state, get_active_profile_id, and set_active_profile_id. Create conversations.py with these exact implementations; encode/decode uses a strict Pydantic cursor containing last_opened_at, updated_at, and id:

~~~python
async def list_for_profile(
    session: AsyncSession,
    *,
    profile_id: str,
    limit: int,
    before: str | None,
) -> ConversationListPage:
    point = decode_conversation_cursor(before) if before is not None else None
    predicates = [Conversation.profile_id == profile_id]
    if point is not None:
        predicates.append(
            tuple_(
                Conversation.last_opened_at,
                Conversation.updated_at,
                Conversation.id,
            ) < (point.last_opened_at, point.updated_at, point.id)
        )
    result = await session.execute(
        select(Conversation)
        .where(*predicates)
        .order_by(
            Conversation.last_opened_at.desc(),
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .limit(limit + 1)
    )
    rows = list(result.scalars().all())
    visible = rows[:limit]
    next_cursor = encode_conversation_cursor(visible[-1]) if len(rows) > limit else None
    return ConversationListPage(rows=visible, next_cursor=next_cursor)

async def get_owned(
    session: AsyncSession, *, conversation_id: str
) -> Conversation | None:
    return await session.get(Conversation, conversation_id)

async def create_for_profile(
    session: AsyncSession,
    *,
    profile_id: str,
    title: str = NEW_CONVERSATION_TITLE,
) -> Conversation:
    profile = await profiles_repo.get_profile(session, profile_id)
    if profile is None or profile.state != PROFILE_STATE_READY:
        raise ConversationRepositoryError("profile is not ready")
    now = utc_now()
    row = Conversation(
        id=new_uuid(), profile_id=profile_id, title=title,
        created_at=now, updated_at=now, last_opened_at=now,
    )
    session.add(row)
    await session.flush()
    return row

async def select_for_profile(
    session: AsyncSession,
    *,
    profile_id: str,
    conversation_id: str,
    now: datetime,
) -> Conversation:
    row = await session.get(Conversation, conversation_id)
    if row is None or row.profile_id != profile_id:
        raise ConversationRepositoryError("conversation profile mismatch")
    row.last_opened_at = now
    row.updated_at = now
    await session.flush()
    return row

async def most_recent_for_profile(
    session: AsyncSession, *, profile_id: str
) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.profile_id == profile_id)
        .order_by(
            Conversation.last_opened_at.desc(),
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()

async def update_title_from_first_user_message(
    session: AsyncSession, *, conversation_id: str, message: str
) -> Conversation:
    row = await session.get(Conversation, conversation_id)
    if row is None:
        raise ConversationRepositoryError("conversation not found")
    prior = int((await session.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role == CHAT_MESSAGE_ROLE_USER,
            func.trim(ChatMessage.content) != "",
        )
    )).scalar_one())
    if row.title == NEW_CONVERSATION_TITLE and prior == 0:
        row.title = derive_conversation_title(message)
        row.updated_at = utc_now()
        await session.flush()
    return row
~~~

Use an opaque URL-safe cursor containing the ordering timestamp pair and ID; malformed cursors go through the existing Pydantic 422 boundary.

- [x] Step 5: Require conversation IDs in message, run, and evaluation repositories

Change the message repository interface from implicit main to explicit arguments:

~~~python
async def insert_message(
    session: AsyncSession,
    *,
    conversation_id: str,
    role: str,
    content: str,
    structured_payload: dict[str, Any] | None = None,
    source_attachment_id: str | None = None,
    redacted_at: datetime | None = None,
) -> ChatMessage:
    if role not in CHAT_MESSAGE_ROLES:
        raise InvalidMessageRoleError("invalid durable message role")
    if content == "" and structured_payload is None:
        raise ChatMessageRepositoryError("message requires content or payload")
    row = ChatMessage(
        id=new_uuid(), conversation_id=conversation_id, role=role,
        content=content, structured_payload=structured_payload,
        source_attachment_id=source_attachment_id, redacted_at=redacted_at,
        created_at=utc_now(), updated_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return row

async def list_messages_before(
    session: AsyncSession,
    *,
    conversation_id: str,
    limit: int,
    before: tuple[datetime, str] | None = None,
) -> list[ChatMessage]:
    predicates = [ChatMessage.conversation_id == conversation_id]
    if before is not None:
        created_at, message_id = before
        predicates.append(or_(
            ChatMessage.created_at < created_at,
            and_(ChatMessage.created_at == created_at, ChatMessage.id < message_id),
        ))
    result = await session.execute(
        select(ChatMessage).where(*predicates)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())

async def list_messages(
    session: AsyncSession, *, conversation_id: str
) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    return list(result.scalars().all())
~~~

Remove all implicit singleton filters. Add resolve_run_owner(session, run_id) -> ConversationOwner, list_run_ids_for_conversation, and list_run_ids_for_profile to agent_runs.py. Add profile_id to every evaluation repository lookup/insert/latest method and require it in the query predicate.

- [x] Step 6: Centralize the activity gate and workspace seed

Create activity_gate.py with one joined predicate reused by these exact functions:

~~~python
async def assert_workspace_idle(
    session: AsyncSession, *, code: str = "PROFILE_SWITCH_BLOCKED"
) -> None:
    if await _has_activity(session):
        raise ActivityBlockedError(code, "finish or resolve the active run first")

async def assert_conversation_idle(
    session: AsyncSession,
    *,
    conversation_id: str,
    code: str = "CONVERSATION_SWITCH_BLOCKED",
) -> None:
    if await _has_activity(
        session, Conversation.id == conversation_id
    ):
        raise ActivityBlockedError(code, "conversation has an active run")

async def assert_profile_idle(
    session: AsyncSession,
    *,
    profile_id: str,
    code: str = "PROFILE_DELETE_BLOCKED",
) -> None:
    if await _has_activity(session, Conversation.profile_id == profile_id):
        raise ActivityBlockedError(code, "profile has an active run")
~~~

Implement `_has_activity` as `select(AgentRun.id).join(ChatMessage, AgentRun.user_message_id == ChatMessage.id).join(Conversation, ChatMessage.conversation_id == Conversation.id).where(AgentRun.state.in_(("running", "interrupted")), *owner_predicates).limit(1)`. Replace ensure_singleton_seeds with ensure_workspace_seed, inserting only workspace_state(id='main', active_profile_id=NULL). Stop calling the old seed helper from main.py and add PATCH to CORS allow_methods.

- [x] Step 7: Run repository/static gates and commit

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_conversation_titles.py tests/unit/test_activity_gate.py tests/integration/test_profile_selection.py tests/integration/test_chat_persistence.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/repositories/profiles.py backend/app/repositories/workspace_state.py backend/app/repositories/conversations.py backend/app/repositories/chat_messages.py backend/app/repositories/agent_runs.py backend/app/repositories/job_evaluations.py backend/app/services/conversation_titles.py backend/app/services/activity_gate.py backend/app/db/seed.py backend/app/main.py backend/tests/unit/test_conversation_titles.py backend/tests/unit/test_activity_gate.py backend/tests/integration/test_profile_selection.py backend/tests/integration/test_chat_persistence.py
git commit -m "refactor: scope repositories to profile conversations"
~~~

---

### Task 3: Add profile DTOs and profile lifecycle routes

**Files:**
- Modify: backend/app/schemas/profile.py
- Create: backend/app/api/profiles.py
- Modify: backend/app/api/profile.py, backend/app/api/cvs.py, backend/app/main.py
- Create: backend/app/services/profile_projection.py
- Modify: backend/app/services/profile_activation.py
- Test: backend/tests/integration/test_profiles_api.py, backend/tests/unit/test_profile_projection.py, backend/tests/integration/test_profile_selection.py

- [x] Step 1: Write failing API/projection tests

Add tests for safe list/detail output, fallback naming, rename scope, activation, and zero-provider selection:

~~~python
def test_profile_projection_uses_extracted_name_then_sanitized_filename():
    assert project_display_name(profile_json_with_name, "resume.pdf") == "Ada Lovelace"
    assert project_display_name(profile_json_without_name, "../Ada CV.pdf") == "Ada CV.pdf"

def test_patch_rejects_extra_fields(client):
    response = client.patch(
        f"/api/profiles/{PROFILE_ID}",
        json={"display_name": "A", "location": "Berlin"},
    )
    assert response.status_code == 422

def test_activate_profile_does_not_call_provider_stack(
    client, provider_spies, seeded_profiles
):
    response = client.post(f"/api/profiles/{PROFILE_B}/activate")
    assert response.status_code == 200
    assert provider_spies.calls == []
~~~

Cover GET /api/profiles, GET /api/profiles/{id}, PATCH, and POST /activate routing/error mapping, including PROFILE_NOT_FOUND, PROFILE_NOT_READY, and PROFILE_SWITCH_BLOCKED. Task 7 adds DELETE only after its external-cleanup coordinator exists.

- [x] Step 2: Run the API tests to verify RED

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_projection.py tests/integration/test_profiles_api.py tests/integration/test_profile_selection.py -q
~~~

Expected: routes and projection module are absent, and old /api/profile is the only profile read surface.

- [x] Step 3: Implement safe profile projection and response schemas

Create profile_projection.py with a pure mapper that validates profile_json and preferences before exposing them. Use these rules:

Define ProfileProjectionError(code, summary) and ProfileActivationError(code, summary) as safe application exceptions carrying only the stable code and summary fields; API adapters map them to the HTTP status table without including ORM/provider details.

~~~python
def project_skill_tags(
    profile: CandidateProfile,
) -> tuple[list[ProfileSkillTag], int]:
    selected = [skill for skill in profile.skills if not skill.excluded]
    tags = [
        ProfileSkillTag(
            key=skill.skill.canonical_key,
            label=skill.skill.display_name,
        )
        for skill in selected
    ]
    return tags[:PROFILE_SKILL_TAG_LIMIT], len(tags)

def project_display_name(
    profile: CandidateProfile, original_name: str
) -> str:
    if profile.full_name and profile.full_name.strip():
        return profile.full_name.strip()
    return sanitize_original_name(original_name)
~~~

ProfileListItem must include no profile_json, raw CV text, contact data, storage path, provider payload, or secret. ProfileDetail may include only validated candidate/preferences documents and safe attachment metadata.

Export these read/projection functions from profile_projection.py so route and activation code share one mapper:

~~~python
async def build_profile_list_response(
    session: AsyncSession,
) -> ProfileListResponse:
    rows = await profiles_repo.list_profiles(session)
    active_id = await workspace_repo.get_active_profile_id(session)
    return ProfileListResponse(
        items=[await project_profile_list_item(session, row, active_id) for row in rows],
        active_profile_id=active_id,
    )

async def build_profile_detail(
    session: AsyncSession, *, profile_id: str
) -> ProfileDetail:
    row = await profiles_repo.get_profile(session, profile_id)
    if row is None:
        raise ProfileProjectionError("PROFILE_NOT_FOUND", "profile not found")
    return await project_profile_detail(session, row)
~~~

Implement project_profile_list_item(session, row, active_id) and project_profile_detail(session, row) in the same module; both load the attachment/document/preferences by the row’s attachment/profile IDs, call parse_candidate_profile and parse_job_preferences, and raise PROFILE_INCONSISTENT on validation or ownership failure. They never read the active workspace row as a substitute for the requested row.

- [x] Step 4: Implement list/detail/rename/activate routes

Create backend/app/api/profiles.py with these thin route implementations; build_profile_list_response/build_profile_detail are read-only functions in profile_projection.py and activate_profile_by_id owns the transaction plus post-commit graph refresh:

~~~python
@router.get("/profiles", response_model=ProfileListResponse)
async def list_profiles() -> ProfileListResponse:
    factory = get_session_factory()
    async with factory() as session:
        response = await build_profile_list_response(session)
        await session.commit()
    return response

@router.get("/profiles/{profile_id}", response_model=ProfileDetail)
async def get_profile(profile_id: Annotated[UuidStr, Path()]) -> ProfileDetail:
    factory = get_session_factory()
    async with factory() as session:
        response = await build_profile_detail(session, profile_id=profile_id)
        await session.commit()
    return response

@router.patch("/profiles/{profile_id}", response_model=ProfileDetail)
async def patch_profile(
    profile_id: Annotated[UuidStr, Path()],
    body: ProfileUpdateRequest,
) -> ProfileDetail:
    display_name = body.display_name.strip()
    if not display_name:
        raise _http("INVALID_DISPLAY_NAME", "display name must not be blank", 422)
    async with session_scope(get_session_factory()) as session:
        await profiles_repo.update_display_name(
            session, profile_id=profile_id, display_name=display_name
        )
        return await build_profile_detail(session, profile_id=profile_id)

@router.post("/profiles/{profile_id}/activate", response_model=SelectionResponse)
async def activate_profile(
    request: Request,
    profile_id: Annotated[UuidStr, Path()],
) -> SelectionResponse:
    return await activate_profile_by_id(
        profile_id=profile_id,
        session_factory=get_session_factory(),
        graph_driver=request.app.state.neo4j_driver,
    )

~~~

Activation performs one short transaction: assert workspace idle; load a ready profile; archive the previous attachment; activate the target attachment; set workspace_state.active_profile_id; update last_opened_at; and return the target’s most recent conversation. After commit, call profile-scoped graph refresh from persisted data only; return a safe rebuild warning if Neo4j is unavailable without rolling back SQLite.

Expose the service boundary used by the route:

~~~python
async def activate_profile_by_id(
    *,
    profile_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    graph_driver: AsyncDriver | None,
) -> SelectionResponse:
    async with session_scope(session_factory) as session:
        await assert_workspace_idle(session, code="PROFILE_SWITCH_BLOCKED")
        profile = await profiles_repo.get_profile(session, profile_id)
        if profile is None:
            raise ProfileActivationError("PROFILE_NOT_FOUND", "profile not found")
        if profile.state != PROFILE_STATE_READY:
            raise ProfileActivationError("PROFILE_NOT_READY", "profile is not ready")
        await attachment_repo.archive_all_except(session, profile.attachment_id)
        await attachment_repo.mark_active(session, profile.attachment_id)
        await workspace_repo.set_active_profile_id(session, profile_id)
        profile.last_opened_at = utc_now()
        selected = await conversations_repo.most_recent_for_profile(
            session, profile_id=profile_id
        )
        response = await build_selection_response(session, profile, selected)
    if graph_driver is not None:
        try:
            await refresh_profile_branch(graph_driver, profile_id=profile_id)
        except ProfileGraphSyncError:
            return response.model_copy(update={"warning": SafeWarning(
                code="NEO4J_SYNC_FAILED",
                summary="profile selected; graph refresh failed",
                guidance="Run the documented Neo4j rebuild command",
            )})
    return response
~~~

The function returns the exact ProfileDetail and selected ConversationSummary from the committed rows; a graph failure is represented as a safe warning field, never as a rollback.

Define build_selection_response(session, profile, selected) as a thin call to project_profile_detail plus project_conversation, and define refresh_profile_branch(driver, profile_id) as the single post-commit call to the profile-parameterized graph sync functions. ProfileGraphSyncError is the safe adapter exception already used by graph synchronization; it is caught only after SQLite commits.

Keep GET /api/profile and /api/profile/cv as compatibility reads for the upload/draft surface, but resolve them through workspace_state.active_profile_id; they must not reintroduce singleton rows.

- [x] Step 5: Register routes and update public API tests

Include profiles_router in main.py, expose PATCH, and replace the old “exactly seven singleton routes” assertion with route tests for the implemented profile routes and compatibility reads. Assert that route handlers never call extraction, embedding, scoring, or graph writes before the SQLite selection commit. Reserve DELETE /profiles/{profile_id} for Task 7.

- [x] Step 6: Run focused profile gates and commit

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_projection.py tests/integration/test_profiles_api.py tests/integration/test_profile_selection.py tests/integration/test_chat_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/schemas/profile.py backend/app/api/profiles.py backend/app/api/profile.py backend/app/api/cvs.py backend/app/main.py backend/app/services/profile_projection.py backend/app/services/profile_activation.py backend/tests/unit/test_profile_projection.py backend/tests/integration/test_profiles_api.py backend/tests/integration/test_profile_selection.py backend/tests/integration/test_chat_api.py
git commit -m "feat: add profile selection API"
~~~

---

### Task 4: Scope chat history, turns, titles, Agent state, and resume to the owning conversation

**Files:**
- Create: backend/app/api/conversations.py
- Create: backend/app/services/conversations.py
- Create: backend/app/api/query_params.py
- Modify: backend/app/schemas/chat.py, backend/app/api/chat.py
- Modify: backend/app/services/chat_turns.py, chat_history.py, job_save_confirmation.py
- Modify: backend/app/agent/state.py, graph.py, context.py, active_cv_context.py
- Modify: backend/app/services/active_cv_reader.py
- Test: backend/tests/integration/test_conversations_api.py, test_chat_history.py, test_chat_persistence.py, test_chat_api.py, test_interrupt_resume.py, backend/tests/unit/test_agent_context.py, test_agent_graph.py, test_active_cv_reader.py

- [x] Step 1: Add failing cross-owner tests

Create test_conversations_api.py covering two profiles and two conversations:

~~~python
def test_history_and_turn_path_cannot_cross_profiles(client, seeded_profiles):
    foreign = client.get(
        f"/api/conversations/{PROFILE_B_CONVERSATION}/history"
    )
    assert foreign.status_code == 200
    mismatch = client.post(
        f"/api/conversations/{PROFILE_A_CONVERSATION}/turns",
        json={"message": "hello", "attachment_ids": [PROFILE_B_ATTACHMENT]},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "CONVERSATION_PROFILE_MISMATCH"

def test_first_user_message_derives_local_bounded_title(
    client, seeded_profiles
):
    response = client.post(
        f"/api/conversations/{PROFILE_A_CONVERSATION}/turns",
        json={"message": "  A   normalized first message  ", "attachment_ids": []},
    )
    assert response.status_code == 200
    assert seeded_profiles.profile_a_conversation.title == (
        "A normalized first message"
    )
~~~

Extend history/resume tests to prove profile A rows never appear in profile B, and that a run resume resolves its stored conversation/profile rather than trusting a caller-selected profile.

- [x] Step 2: Run chat tests to verify RED

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_conversations_api.py tests/integration/test_chat_history.py tests/integration/test_chat_persistence.py tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py tests/unit/test_agent_context.py tests/unit/test_agent_graph.py -q
~~~

Expected: old /api/chat/history and /api/chat/turns implementations still force main and build_initial_agent_state returns main.

- [x] Step 3: Add conversation DTOs and routes

Move the current _history_query validator from api/chat.py to api/query_params.py as the single reusable dependency, then add a path-scoped conversation ID validation dependency and register:

~~~python
@router.get("/profiles/{profile_id}/conversations", response_model=ConversationListResponse)
async def list_profile_conversations(
    profile_id: UuidStr, query: Annotated[ConversationQuery, Depends()]
) -> ConversationListResponse:
    return await list_conversations(
        profile_id=profile_id, limit=query.limit, before=query.before,
        session_factory=get_session_factory(),
    )

@router.post("/profiles/{profile_id}/conversations", response_model=ConversationMutationResponse)
async def create_profile_conversation(profile_id: UuidStr) -> ConversationMutationResponse:
    return await create_conversation(
        profile_id=profile_id, session_factory=get_session_factory()
    )

@router.post("/conversations/{conversation_id}/select", response_model=ConversationMutationResponse)
async def select_conversation(conversation_id: UuidStr) -> ConversationMutationResponse:
    return await select_owned_conversation(
        conversation_id=conversation_id,
        session_factory=get_session_factory(),
    )

@router.get("/conversations/{conversation_id}/history", response_model=HistoryPage)
async def get_conversation_history(
    conversation_id: UuidStr,
    query: Annotated[HistoryQuery, Depends(_history_query)],
) -> HistoryPage:
    factory = get_session_factory()
    async with factory() as session:
        page = await get_history_page(
            session, conversation_id=conversation_id,
            limit=query.limit, before=query.before,
        )
        await session.commit()
    return page

@router.post("/conversations/{conversation_id}/turns")
async def post_conversation_turn(
    conversation_id: UuidStr,
    body: ChatTurnRequest,
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> EventSourceResponse:
    events = stream_chat_turn(
        conversation_id=conversation_id,
        message=body.message,
        attachment_ids=body.attachment_ids,
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await open_sse_response(events, error_mapper=_http_for_chat_error)
~~~

Implement services/conversations.py with these concrete service signatures:

~~~python
class ConversationServiceError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        self.code = code
        self.summary = summary
        super().__init__(summary)

def project_conversation(
    row: Conversation, *, selected: bool
) -> ConversationSummary:
    return ConversationSummary(
        id=row.id, profile_id=row.profile_id, title=row.title,
        created_at=row.created_at, updated_at=row.updated_at,
        last_opened_at=row.last_opened_at, is_selected=selected,
    )

def project_conversation_list(
    page: ConversationListPage, *, selected_id: str | None
) -> ConversationListResponse:
    return ConversationListResponse(
        items=[
            project_conversation(row, selected=row.id == selected_id)
            for row in page.rows
        ],
        next_cursor=page.next_cursor,
    )

async def list_conversations(
    *, profile_id: str, limit: int, before: str | None,
    session_factory: async_sessionmaker[AsyncSession],
) -> ConversationListResponse:
    async with session_scope(session_factory) as session:
        profile = await profiles_repo.get_profile(session, profile_id)
        if profile is None:
            raise ConversationServiceError("PROFILE_NOT_FOUND", "profile not found")
        page = await conversations_repo.list_for_profile(
            session, profile_id=profile_id, limit=limit, before=before
        )
        selected = await conversations_repo.most_recent_for_profile(
            session, profile_id=profile_id
        )
        return project_conversation_list(
            page, selected_id=selected.id if selected is not None else None
        )

async def create_conversation(
    *, profile_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> ConversationMutationResponse:
    async with session_scope(session_factory) as session:
        await assert_workspace_idle(session, code="CONVERSATION_SWITCH_BLOCKED")
        row = await conversations_repo.create_for_profile(
            session, profile_id=profile_id, title=NEW_CONVERSATION_TITLE
        )
        return ConversationMutationResponse(
            conversation=project_conversation(row, selected=True)
        )

async def select_owned_conversation(
    *, conversation_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> ConversationMutationResponse:
    async with session_scope(session_factory) as session:
        await assert_workspace_idle(session, code="CONVERSATION_SWITCH_BLOCKED")
        owner = await conversations_repo.resolve_owner(session, conversation_id)
        if owner is None:
            raise ConversationServiceError(
                "CONVERSATION_NOT_FOUND", "conversation not found"
            )
        active_id = await workspace_repo.get_active_profile_id(session)
        if active_id != owner.profile_id:
            raise ConversationServiceError(
                "CONVERSATION_PROFILE_MISMATCH", "conversation is not active"
            )
        row = await conversations_repo.select_for_profile(
            session, profile_id=owner.profile_id,
            conversation_id=conversation_id, now=utc_now(),
        )
        return ConversationMutationResponse(
            conversation=project_conversation(row, selected=True)
        )
~~~

Each handler maps stable errors without message/CV/provider text. Task 7 adds DELETE only after its checkpoint coordinator exists.

- [x] Step 4: Thread IDs through turn creation and context

Change create_user_turn to accept conversation_id and resolve the owning profile_id, attachment_id, and preferences inside its transaction:

~~~python
async def create_user_turn(
    *,
    conversation_id: str,
    message: str,
    attachment_ids: Sequence[str],
    source_attachment_id: str | None,
    session_factory: async_sessionmaker[AsyncSession],
) -> CreatedTurn:
    factory = session_factory
    async with session_scope(factory) as session:
        owner = await conversations_repo.resolve_owner(
            session, conversation_id=conversation_id
        )
        if owner is None:
            raise ChatTurnError("CONVERSATION_NOT_FOUND", "conversation not found")
        await assert_conversation_idle(
            session, conversation_id=conversation_id,
            code="CONVERSATION_SWITCH_BLOCKED",
        )
        await conversations_repo.update_title_from_first_user_message(
            session, conversation_id=conversation_id, message=message
        )
        user = await messages_repo.insert_message(
            session, conversation_id=conversation_id,
            role=CHAT_MESSAGE_ROLE_USER, content=message,
            source_attachment_id=source_attachment_id,
        )
        run = await runs_repo.create_run(
            session, user_message_id=user.id,
            source_attachment_id=source_attachment_id,
        )
    return CreatedTurn(
        user_message_id=user.id, run_id=run.id,
        conversation_id=owner.conversation_id,
        profile_id=owner.profile_id,
        attachment_id=owner.attachment_id,
    )
~~~

Insert the user message with the explicit conversation ID, create the run linked to that message, and call update_title_from_first_user_message only when the conversation is still Chat mới and has no prior non-empty user message. Pass conversation_id and profile_id into load_recent_context, load_candidate_context, and load_active_cv_context; each loader must assert durable ownership and fail closed on mismatch.

Remove AGENT_CONVERSATION_ID and the CONVERSATION_ID == 'main' assertions. Change build_initial_agent_state and initial_graph_state to require the resolved conversation ID and profile ID:

~~~python
state = build_initial_agent_state(
    conversation_id=owner.conversation_id,
    profile_id=owner.profile_id,
    user_message=message,
    recent_context=recent,
    candidate_context=candidate,
    active_cv_context=cv_context,
)
~~~

- [x] Step 5: Scope history and resume, including job-save confirmation

Change get_history_page(session, conversation_id=conversation_id, limit=limit, before=before) and every repository query to include conversation_id. Keep the response cursor shape unchanged. In stream_resume, call resolve_run_owner before claiming the run, reject deleted or mismatched owners with RUN_PROFILE_MISMATCH, and pass the owner’s conversation/profile context to the graph. Remove the message conversation singleton check in job_save_confirmation.py; replace it with durable owner lookup and preserve the existing exact initiating-message check.

- [x] Step 6: Run chat/context gates and commit

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_conversations_api.py tests/integration/test_chat_history.py tests/integration/test_chat_persistence.py tests/integration/test_chat_api.py tests/integration/test_interrupt_resume.py tests/integration/test_agent_runner.py tests/integration/test_active_cv_tool.py tests/unit/test_agent_context.py tests/unit/test_agent_graph.py tests/unit/test_active_cv_reader.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/api/conversations.py backend/app/api/query_params.py backend/app/api/chat.py backend/app/schemas/chat.py backend/app/services/conversations.py backend/app/services/chat_turns.py backend/app/services/chat_history.py backend/app/services/job_save_confirmation.py backend/app/agent/state.py backend/app/agent/graph.py backend/app/agent/context.py backend/app/agent/active_cv_context.py backend/app/services/active_cv_reader.py backend/tests/integration/test_conversations_api.py backend/tests/integration/test_chat_history.py backend/tests/integration/test_chat_persistence.py backend/tests/integration/test_chat_api.py backend/tests/integration/test_interrupt_resume.py backend/tests/integration/test_agent_runner.py backend/tests/integration/test_active_cv_tool.py backend/tests/unit/test_agent_context.py backend/tests/unit/test_agent_graph.py backend/tests/unit/test_active_cv_reader.py
git commit -m "feat: isolate chat by conversation and profile"
~~~

---

### Task 5: Bootstrap a pending profile and owned conversation before extraction

**Files:**
- Modify: backend/app/db/models/profiles.py
- Modify: backend/migrations/versions/0005_cv_profiles_multi_conversation.py
- Modify: backend/app/schemas/profile.py, attachments.py
- Create: backend/app/schemas/profile_setup.py
- Modify: backend/app/repositories/profiles.py, conversations.py, workspace_state.py
- Modify: backend/app/services/activity_gate.py, cv_upload.py, profile_projection.py, conversations.py
- Modify: backend/app/services/chat_turns.py, profile_drafts.py, profile_approval.py, profile_activation.py
- Modify: backend/app/tools/profile.py, backend/app/agent/context.py, active_cv_context.py
- Modify: backend/app/api/attachments.py, profile.py, profiles.py, conversations.py
- Modify: backend/app/services/job_evaluation.py, matching.py, saved_jobs.py, observability.py
- Modify: backend/app/graph/rebuild_snapshot.py
- Modify: frontend/src/features/profile/types.ts, conversationTypes.ts, api.ts, workspaceState.ts, CvSidebar.tsx
- Modify: frontend/src/features/chat/ChatPage.tsx, frontend/src/app/App.tsx
- Test: backend/tests/unit/test_attachment_profile_models.py, test_agent_context.py
- Test: backend/tests/integration/test_migrations.py, test_database_contract.py, test_cv_api.py, test_profiles_api.py, test_profile_selection.py, test_conversations_api.py, test_chat_persistence.py, test_profile_approval.py, test_job_evaluations.py, test_graph_rebuild_behavior.py
- Test: frontend/src/test/profile-api.test.ts, profile-workspace-state.test.tsx, chat-page.test.tsx, frontend/src/app/App.test.tsx, frontend/src/test/cv-sidebar.test.tsx

- [x] **Step 1: Write failing pending-shape schema tests**

Extend the model, migration, and database-contract tests with one coherent
incomplete shape and one coherent ready shape:

~~~python
def test_pending_profile_requires_null_approved_fields() -> None:
    table = Profile.__table__
    assert table.c.profile_json.nullable is True
    assert table.c.extraction_version.nullable is True
    assert table.c.source_hash.nullable is True
    assert PROFILE_STATE_PENDING == "pending"
    assert PROFILE_STATES == frozenset({"pending", "ready", "deleting"})


def test_database_rejects_partial_pending_profile(migrated_sqlite: Path) -> None:
    async def body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment = await _seed_staged_attachment(session, marker="partial")
                session.add(Profile(
                    id=new_uuid(),
                    attachment_id=attachment.id,
                    display_name="partial.pdf",
                    profile_json=None,
                    location="Invented",
                    extraction_version=None,
                    source_hash=None,
                    state="pending",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    last_opened_at=utc_now(),
                ))
                with pytest.raises(IntegrityError):
                    await session.flush()
        finally:
            await engine.dispose()
    run_async(body())
~~~

Add a database test that inserts one pending profile, then proves a second
profile with `profile_json IS NULL` fails the named unique incomplete-profile
index. Add parity assertions for nullable approved fields, the state/shape CHECK,
and `uq_profiles__single_incomplete`. Keep `workspace_state(main, NULL)` and zero
profiles/conversations after migration.

- [x] **Step 2: Run schema tests to verify RED**

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_attachment_profile_models.py tests/integration/test_migrations.py tests/integration/test_database_contract.py -q
~~~

Expected: assertions fail because `pending`, nullable approved fields, the
state/shape CHECK, and the single-incomplete index do not exist.

- [x] **Step 3: Implement the pending persistence contract and rerun schema tests**

Define the shared state names once in `db/models/profiles.py`:

~~~python
PROFILE_STATE_PENDING = "pending"
PROFILE_STATE_READY = "ready"
PROFILE_STATE_DELETING = "deleting"
PROFILE_STATES = frozenset({
    PROFILE_STATE_PENDING,
    PROFILE_STATE_READY,
    PROFILE_STATE_DELETING,
})
PROFILE_SETUP_STATUS_AWAITING_EXTRACTION = "awaiting_extraction"
PROFILE_SETUP_STATUS_AWAITING_APPROVAL = "awaiting_approval"
PROFILE_SETUP_STATUS_EXTRACTION_FAILED = "extraction_failed"
~~~

Make `profile_json`, `extraction_version`, and `source_hash` nullable. Add one
named CHECK equivalent to:

~~~sql
(state = 'pending'
 AND profile_json IS NULL AND location IS NULL
 AND extraction_version IS NULL AND source_hash IS NULL)
OR
(state = 'ready'
 AND profile_json IS NOT NULL
 AND extraction_version IS NOT NULL AND source_hash IS NOT NULL)
OR
(state = 'deleting' AND (
    (profile_json IS NULL AND location IS NULL
     AND extraction_version IS NULL AND source_hash IS NULL)
 OR (profile_json IS NOT NULL
     AND extraction_version IS NOT NULL AND source_hash IS NOT NULL)
))
~~~

Add a SQLite unique expression index named
`uq_profiles__single_incomplete` over constant `1` with
`WHERE profile_json IS NULL`; this also prevents a new pending row while failed
cleanup retains a deleting incomplete row. Mirror the ORM metadata and explicit
0005 migration. Do not add placeholder profile JSON or reuse
`attachments.file_hash` as `profiles.source_hash`.

Run:

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_attachment_profile_models.py tests/integration/test_migrations.py tests/integration/test_database_contract.py -q
~~~

Expected: the schema tests pass with zero application rows after migration.

- [x] **Step 4: Write failing upload-bootstrap and safe-projection tests**

Add response/parser contracts for these exact values:

~~~python
ProfileSetupStatus = Literal[
    "awaiting_extraction", "awaiting_approval", "extraction_failed"
]
CvUploadOutcome = Literal[
    "new_pending", "retry_pending", "existing_pending",
    "existing_active", "existing_profile",
]

class PendingProfileBootstrap(BaseModel):
    model_config = StrictModelConfig
    profile: ProfileListItem
    conversation: ConversationSummary
    start_extraction: bool

class CvUploadResponse(BaseModel):
    model_config = StrictModelConfig
    attachment: AttachmentPublic
    outcome: CvUploadOutcome
    profile: ProfileUploadSummary | None = None
    draft: DraftUploadSummary | None = None
    bootstrap: PendingProfileBootstrap | None = None
~~~

Add model validation for the frozen coupling: every pending outcome requires a
bootstrap whose pending profile owns the returned conversation and top-level
attachment; `new_pending` and `retry_pending` require
`start_extraction=True`; `existing_pending` derives the flag from the absence
of a draft or active/interrupted run; `existing_active` and `existing_profile`
require `bootstrap=None` and a safe ready-profile reference. Reject every
inconsistent combination in backend model tests and mirror those cases in the
frontend parser tests.

Move `CvUploadResponse` into the new `schemas/profile_setup.py` so it may reuse
`ProfileListItem` and `ConversationSummary` without making `profile.py` import a
schema that imports it back. Update API/service imports; keep `AttachmentPublic`
in `attachments.py`.

Add integration tests:

~~~python
def test_new_upload_bootstraps_one_pending_profile_and_conversation(
    health_env, provider_spies
) -> None:
    with health_client() as client:
        response = client.post(
            "/api/attachments/cv",
            files={"file": ("Ada.pdf", PDF_BYTES, "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "new_pending"
    assert body["bootstrap"]["profile"]["state"] == "pending"
    assert body["bootstrap"]["profile"]["setup_status"] == "awaiting_extraction"
    assert body["bootstrap"]["conversation"]["profile_id"] == body["bootstrap"]["profile"]["id"]
    assert body["bootstrap"]["start_extraction"] is True
    assert provider_spies.calls == []


def test_different_upload_is_blocked_while_pending(health_env) -> None:
    first = _upload_pdf("first.pdf", PDF_BYTES)
    second = _upload_pdf("second.pdf", OTHER_PDF_BYTES)
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "PROFILE_SETUP_IN_PROGRESS"
~~~

Cover `retry_pending`, `existing_pending`, `start_extraction=False` when a draft
or running/interrupted run exists, exact-hash reuse with stable profile and
conversation IDs, rollback file cleanup, and `GET /api/profiles` pending output.
Pending list rows must have `location=None`, `skill_tags=[]`, `skill_count=0`,
`extraction_version=None`, `source_hash=None`, and one of the three fixed
`setup_status` values. `GET /api/profiles/{id}`, PATCH, activate, and reextract
must return `PROFILE_NOT_READY` for pending rows.

- [x] **Step 5: Run upload/projection tests to verify RED**

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_cv_api.py tests/integration/test_profiles_api.py tests/integration/test_profile_selection.py tests/integration/test_conversations_api.py -q
~~~

Expected: new upload still returns a staged attachment only; no pending owner,
bootstrap DTO, setup status, or pending gate exists.

- [x] **Step 6: Implement atomic upload bootstrap and safe pending reads**

Add these repository boundaries:

~~~python
async def create_pending_profile(
    session: AsyncSession, *, attachment_id: str, display_name: str
) -> Profile: ...

async def get_incomplete_profile(session: AsyncSession) -> Profile | None: ...

async def create_bootstrap_for_profile(
    session: AsyncSession, *, profile_id: str
) -> Conversation: ...
~~~

`create_pending_profile` writes only the attachment ID, sanitized filename
display name, null approved fields, `pending`, and timestamps.
`create_bootstrap_for_profile` is the only conversation creator allowed for a
pending profile; the existing public `create_for_profile` remains ready-only.

In `cv_upload.py`, enforce workspace idleness and the single-incomplete gate
before file reads, then recheck them in the write transaction. For a new hash,
promote the UUID file outside SQLite and use one `session_scope` to insert the
staged attachment, pending profile, bootstrap conversation, and
`workspace_state.active_profile_id`. On transaction failure remove only that
new UUID file. Keep a previous ready attachment active until promotion.

Derive `start_extraction` from durable rows: it is false when a targeted draft
or running/interrupted run exists, otherwise true for staged new/retried pending
rows. A different hash while an incomplete row exists raises
`PROFILE_SETUP_IN_PROGRESS`; exact-hash reuse returns the existing bootstrap.

Update `profile_projection.py` to derive setup status in this precedence:

~~~python
if attachment.state == ATTACHMENT_STATE_FAILED:
    setup_status = PROFILE_SETUP_STATUS_EXTRACTION_FAILED
elif draft is not None and draft.target_profile_id == profile.id:
    setup_status = PROFILE_SETUP_STATUS_AWAITING_APPROVAL
else:
    setup_status = PROFILE_SETUP_STATUS_AWAITING_EXTRACTION
~~~

Allow list and bootstrap-conversation hydration for the selected pending
profile, but keep detail, rename, activation, re-extraction, new conversation,
selection, and conversation deletion ready-only.

- [x] **Step 7: Write failing owned-turn, promotion, and ready-truth tests**

Add tests proving the pending profile is a real owner and never approved truth:

~~~python
def test_pending_extraction_turn_and_resume_keep_bootstrap_owner(
    pending_setup_context,
) -> None:
    turn = pending_setup_context.start_extraction()
    assert turn.profile_id == pending_setup_context.profile_id
    assert turn.conversation_id == pending_setup_context.conversation_id
    assert turn.attachment_id == pending_setup_context.attachment_id
    draft = pending_setup_context.current_draft()
    assert draft.target_profile_id == pending_setup_context.profile_id


def test_approval_promotes_in_place_without_second_conversation(
    pending_setup_context,
) -> None:
    before = pending_setup_context.conversation_ids()
    result = pending_setup_context.approve()
    assert result.profile_id == pending_setup_context.profile_id
    assert result.conversation_id == pending_setup_context.conversation_id
    assert pending_setup_context.profile_state() == "ready"
    assert pending_setup_context.conversation_ids() == before


def test_pending_selection_never_loads_approved_truth(
    pending_setup_context, provider_spies
) -> None:
    assert pending_setup_context.candidate_context() == []
    assert pending_setup_context.evaluate_saved_job().code == "PROFILE_NOT_READY"
    assert pending_setup_context.graph_snapshot_profile_ids() == []
    assert provider_spies.calls == []
~~~

Cover the bootstrap turn's exact staged attachment requirement, unrelated
attachment rejection before message/run insert, draft-correction turns after
Request Changes, synthetic bootstrap title exclusion, guarded identity used by
post-commit graph sync, prior active attachment archival on promotion, pending
exclusion from active-CV readers/matching/evaluation/observability/rebuild, and
safe compatibility `GET /api/profile` output.

- [x] **Step 8: Run owned-turn/promotion tests to verify RED**

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_chat_persistence.py tests/integration/test_profile_approval.py tests/unit/test_agent_context.py tests/integration/test_job_evaluations.py tests/integration/test_graph_rebuild_behavior.py -q
~~~

Expected: the profile tool does not target the injected profile owner,
approval attempts singleton/new-row behavior, and approved-data readers do not
consistently reject pending selection.

- [x] **Step 9: Implement explicit pending ownership and in-place promotion**

In the profile tool, read the injected graph `profile_id`. Pass it as
`target_profile_id` only when the row owns the effective attachment and is
pending, or when the run is an explicit ready-profile re-extraction. In
`propose_profile_from_cv`, repeat the state/attachment ownership check before
provider work and again before publishing chunks/document/draft.

In `create_user_turn`, allow a pending owner only when either:

~~~python
bootstrap = requested_attachment_ids == [owner.attachment_id] and draft is None
correction = not requested_attachment_ids and draft is not None and (
    draft.target_profile_id == owner.profile_id
)
~~~

Stamp the bootstrap message/run with `source_attachment_id=owner.attachment_id`.
Exclude source-owned synthetic turns when deriving the first ordinary
conversation title. Candidate context for pending is empty; working-memory
draft context is allowed only for the exact pending owner.

Replace ambiguous compatibility reads with a repository boundary named
`get_selected_ready_profile`. Use it in active-CV readers, matching, evaluation,
Saved Job currentness, and graph/observability inputs. Pending returns
`PROFILE_NOT_READY` before provider/scoring/graph work. Rebuild includes only
ready rows.

Refactor approval into explicit pending-promotion and ready-re-extraction
branches. Pending promotion updates the existing row, creates its preferences,
promotes the document/chunks, archives the independently loaded prior active
attachment, activates the pending attachment, and keeps the existing bootstrap
conversation. Request Changes preserves the targeted pending draft. Use the
guarded persisted profile—not the unguarded provider draft—for graph sync.

- [x] **Step 10: Write failing frontend bootstrap-adoption tests**

~~~tsx
it('adopts server bootstrap IDs before starting one extraction turn', async () => {
  const upload = vi.fn().mockResolvedValue(pendingUploadResponse);
  const sendTurn = vi.fn().mockResolvedValue(undefined);
  render(<App deps={{sidebar: {uploadCv: upload}, chat: {sendConversationTurn: sendTurn}}} />);
  await userEvent.upload(screen.getByTestId('jobagent-cv-upload'), pdfFile);
  await waitFor(() => expect(sendTurn).toHaveBeenCalledTimes(1));
  expect(sendTurn.mock.calls[0][0]).toBe(pendingUploadResponse.bootstrap.conversation.id);
});


it('does not restart an existing pending draft', async () => {
  render(<App deps={depsFor(existingPendingResponse({start_extraction: false}))} />);
  await userEvent.upload(screen.getByTestId('jobagent-cv-upload'), pdfFile);
  expect(sendConversationTurn).not.toHaveBeenCalled();
});

it('retries the failed exact hash through the shared picker with stable IDs', async () => {
  const upload = vi.fn().mockResolvedValue(retryPendingResponse);
  render(<App deps={depsFor({uploadCv: upload})} />);
  await userEvent.upload(screen.getByTestId('jobagent-cv-upload'), samePdfFile);
  expect(upload).toHaveBeenCalledWith(samePdfFile, expect.anything());
  expect(retryPendingResponse.outcome).toBe('retry_pending');
  expect(retryPendingResponse.bootstrap.profile.id).toBe(pendingProfile.id);
  expect(retryPendingResponse.bootstrap.conversation.id).toBe(bootstrapConversation.id);
  expect(retryPendingResponse.bootstrap.start_extraction).toBe(true);
  await waitFor(() => expect(sendConversationTurn).toHaveBeenCalledTimes(1));
});
~~~

Add strict parser tests for the five outcomes, bootstrap coupling, nullable
pending profile fields, fixed setup status values, and rejection of extra/raw
fields. Assert `workspace/bootstrapAdopted` invokes neither activate nor create,
and that Save Profile reloads workspace state so pending metadata is replaced.
Cover reload persistence, request-change correction enablement,
ordinary-chat lock for awaiting-extraction/extraction-failed, and no second
reducer/store.

- [x] **Step 11: Run frontend tests to verify RED**

~~~powershell
Set-Location ..\frontend
npm test -- --run src/test/profile-api.test.ts src/test/profile-workspace-state.test.tsx src/test/chat-page.test.tsx src/app/App.test.tsx src/test/cv-sidebar.test.tsx
~~~

Expected: upload responses have no bootstrap parser/action and App cannot select
the server conversation before scheduling the turn.

- [x] **Step 12: Implement frontend bootstrap adoption and run all Task 5 gates**

Add `workspace/bootstrapAdopted` to the existing reducer. It applies only the
server profile/conversation IDs and projections, marks the returned conversation
selected, and clears prior profile/conversation selection without inventing
replacement IDs. `App.handleSidebarUploadSuccess` dispatches this action before
setting `sidebarAttachmentTurn`, and sets a turn only when
`bootstrap.start_extraction` is true.

Pass the selected profile state/setup status to ChatPage. Ordinary composer use
is allowed for ready profiles and pending `awaiting_approval` correction turns;
it is disabled for pending `awaiting_extraction` and `extraction_failed`.
The sidebar-owned automatic turn may still start for an adopted pending
conversation because it uses the dedicated effect and the same ChatPage reducer.
On Save Profile, reload workspace profiles/conversations so the promoted ready
projection replaces pending metadata.

Run:

~~~powershell
Set-Location ..\backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_attachment_profile_models.py tests/unit/test_agent_context.py tests/integration/test_migrations.py tests/integration/test_database_contract.py tests/integration/test_cv_api.py tests/integration/test_profiles_api.py tests/integration/test_profile_selection.py tests/integration/test_conversations_api.py tests/integration/test_chat_persistence.py tests/integration/test_profile_approval.py tests/integration/test_job_evaluations.py tests/integration/test_graph_rebuild_behavior.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..\frontend
npm test -- --run src/test/profile-api.test.ts src/test/profile-workspace-state.test.tsx src/test/chat-page.test.tsx src/app/App.test.tsx src/test/cv-sidebar.test.tsx
npm run lint
npm run typecheck
Set-Location ..
git add backend/app/db/models/profiles.py backend/migrations/versions/0005_cv_profiles_multi_conversation.py backend/app/schemas/profile.py backend/app/schemas/attachments.py backend/app/schemas/profile_setup.py backend/app/repositories/profiles.py backend/app/repositories/conversations.py backend/app/repositories/workspace_state.py backend/app/services/activity_gate.py backend/app/services/cv_upload.py backend/app/services/profile_projection.py backend/app/services/conversations.py backend/app/services/chat_turns.py backend/app/services/profile_drafts.py backend/app/services/profile_approval.py backend/app/services/profile_activation.py backend/app/tools/profile.py backend/app/agent/context.py backend/app/agent/active_cv_context.py backend/app/api/attachments.py backend/app/api/profile.py backend/app/api/profiles.py backend/app/api/conversations.py backend/app/services/job_evaluation.py backend/app/services/matching.py backend/app/services/saved_jobs.py backend/app/services/observability.py backend/app/graph/rebuild_snapshot.py backend/tests/unit/test_attachment_profile_models.py backend/tests/unit/test_agent_context.py backend/tests/integration/test_migrations.py backend/tests/integration/test_database_contract.py backend/tests/integration/test_cv_api.py backend/tests/integration/test_profiles_api.py backend/tests/integration/test_profile_selection.py backend/tests/integration/test_conversations_api.py backend/tests/integration/test_chat_persistence.py backend/tests/integration/test_profile_approval.py backend/tests/integration/test_job_evaluations.py backend/tests/integration/test_graph_rebuild_behavior.py frontend/src/features/profile/types.ts frontend/src/features/profile/conversationTypes.ts frontend/src/features/profile/api.ts frontend/src/features/profile/workspaceState.ts frontend/src/features/profile/CvSidebar.tsx frontend/src/features/chat/ChatPage.tsx frontend/src/app/App.tsx frontend/src/test/profile-api.test.ts frontend/src/test/profile-workspace-state.test.tsx frontend/src/test/chat-page.test.tsx frontend/src/app/App.test.tsx frontend/src/test/cv-sidebar.test.tsx
git commit -m "feat: bootstrap pending CV profiles"
~~~

Expected: all focused backend/frontend tests and static gates pass; upload and
selection paths record zero provider calls; the worktree is clean after the
single Task 5 commit.

---

### Task 6: Make approval, persisted extraction, rename, and explicit re-extraction profile-aware

**Files:**
- Modify: backend/app/services/profile_drafts.py, profile_approval.py, profile_activation.py, cv_upload.py
- Modify: backend/app/services/profile_extraction.py, backend/app/services/cv_skill_contracts.py
- Modify: backend/app/services/cv_document_projection.py, cv_document_extraction.py
- Modify: backend/app/api/profiles.py, backend/app/api/cvs.py
- Test: backend/tests/unit/test_profile_extraction.py, backend/tests/fixtures/skill_extraction_golden.json, backend/tests/integration/test_profile_approval.py, backend/tests/integration/test_profiles_api.py
- Create: backend/tests/integration/test_profile_reextraction.py

- [x] Step 1: Add failing approval and reuse tests

Use ScriptedStructuredInvoker, FakeEmbeddingClient, and the existing _seed_cv_document_draft fixture:

~~~python
def test_first_approval_promotes_pending_profile_and_preserves_bootstrap_chat(
    approval_context,
):
    pending_id = approval_context.profile_id
    conversation_id = approval_context.conversation_id
    result = commit_approved_draft(**approval_context.arguments)
    assert result.profile_id == pending_id
    assert result.conversation_id == conversation_id
    assert approval_context.profile_state() == "ready"
    assert approval_context.conversation_ids() == [conversation_id]
    assert approval_context.provider.calls == 1

def test_activate_existing_profile_reads_persisted_extraction_without_provider_calls(
    selection_context,
):
    before = (
        selection_context.extractor.calls,
        selection_context.embedder.calls,
        selection_context.scorer.calls,
    )
    selection_context.activate_profile()
    after = (
        selection_context.extractor.calls,
        selection_context.embedder.calls,
        selection_context.scorer.calls,
    )
    assert after == before

def test_reextract_same_profile_preserves_conversations_and_marks_old_evidence_stale(
    reextract_context,
):
    old_ids = reextract_context.conversation_ids()
    reextract_context.approve_revision()
    assert reextract_context.conversation_ids() == old_ids
    assert reextract_context.evaluation_currentness() == "stale"
~~~

- [x] Step 2: Run approval/re-extraction tests to verify RED

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_profiles_api.py tests/integration/test_profile_reextraction.py -q
~~~

Expected: extracted identity fields and the profile re-extraction route remain incomplete; stale singleton-oriented approval tests still fail until they are migrated to durable pending/ready IDs.

- [x] Step 3: Stamp draft ownership and guard extracted identity

Add target_profile_id to every draft read/write path. Initial extraction uses the injected pending owner created in Task 5; profile re-extraction uses the requested ready profile ID. Both paths verify that the target owns the attachment before provider work and before publication. Extend the structured profile-extraction schema/prompt and synthetic golden fixtures to emit nullable full_name/location, project only direct document evidence into those fields, then run guard_optional_identity_fields over the source fragments before persisting draft/document-draft profile_json and again before approved profile persistence; persist location from the guarded profile, never from an unvalidated projection. A missing or unsupported value remains null.

- [x] Step 4: Split pending promotion from ready-profile replacement

Refactor _run_sqlite_approval into two explicit branches:

~~~python
profile = await profiles_repo.get_profile(session, draft.target_profile_id)
if profile is None:
    raise ProfileApprovalError("PROFILE_NOT_FOUND", "profile not found")
if profile.state == PROFILE_STATE_PENDING:
    if profile.attachment_id != attachment.id:
        raise ProfileApprovalError("PROFILE_INCONSISTENT", "profile ownership mismatch")
    profile.display_name = project_display_name(
        guarded_profile, attachment.original_name
    )
    profile.profile_json = guarded_profile.model_dump(mode="json")
    profile.location = guarded_profile.location
    profile.extraction_version = document.extraction_version
    profile.source_hash = document.source_hash
    profile.state = PROFILE_STATE_READY
    profile.updated_at = utc_now()
    await profiles_repo.upsert_profile_preferences(
        session,
        profile_id=profile.id,
        preferences_json=preferences.model_dump(mode="json"),
    )
    conversation = await conversations_repo.most_recent_for_profile(
        session, profile_id=profile.id
    )
    if conversation is None:
        raise ProfileApprovalError("PROFILE_INCONSISTENT", "bootstrap conversation missing")
elif profile.state == PROFILE_STATE_READY:
    profile.profile_json = guarded_profile.model_dump(mode="json")
    profile.location = guarded_profile.location
    profile.extraction_version = document.extraction_version
    profile.source_hash = document.source_hash
    profile.updated_at = utc_now()
    # Preserve preferences and every conversation ID.
else:
    raise ProfileApprovalError("PROFILE_NOT_READY", "profile is not ready")
~~~

Only pending promotion archives the independently loaded prior active ready attachment and activates the pending attachment; workspace selection and the bootstrap conversation ID already belong to the pending profile. Both branches atomically replace the persisted document/chunks after provider/embedding work completes outside SQLite. Preserve source_hash revision checks and let existing evaluation currentness mark old evidence stale. Graph sync must receive the guarded profile reloaded from committed SQLite truth.

- [x] Step 5: Add profile-owned re-extraction SSE route

Implement POST /api/profiles/{profile_id}/reextract as a strict empty-body route. It requires the target to be the ready active workspace profile (the UI selects a profile first), asserts idle, resolves its attachment and selected conversation, and calls the existing stream_chat_turn/stream_cv_reprocess machinery with source_attachment_id plus target_profile_id. Do not accept attachment_id, profile JSON, source text, or client-selected conversation in the request body. Approval resumes through POST /api/chat/runs/{run_id}/resume and uses the same SSE events.

- [x] Step 6: Handle exact-hash upload reuse without duplicate profiles

When cv_upload.py finds an exact-hash attachment already owned by a ready/archived profile, return a safe existing-profile reference and skip extraction; do not create a pending duplicate for the same attachment. Pending exact-hash new/retry behavior belongs to Task 5. Add tests proving no extractor/embedding calls on archived ready-profile reuse.

- [x] Step 7: Run lifecycle gates and commit

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_profiles_api.py tests/integration/test_profile_reextraction.py tests/integration/test_cv_manager_api.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/services/profile_drafts.py backend/app/services/profile_approval.py backend/app/services/profile_activation.py backend/app/services/cv_upload.py backend/app/services/profile_extraction.py backend/app/services/cv_skill_contracts.py backend/app/services/cv_document_projection.py backend/app/services/cv_document_extraction.py backend/app/api/profiles.py backend/app/api/cvs.py backend/tests/unit/test_profile_extraction.py backend/tests/fixtures/skill_extraction_golden.json backend/tests/integration/test_profile_approval.py backend/tests/integration/test_profiles_api.py backend/tests/integration/test_profile_reextraction.py backend/tests/integration/test_cv_manager_api.py
git commit -m "feat: persist profile extraction revisions"
~~~

---

### Task 7: Implement conversation and profile deletion coordinators with checkpoint safety

**Files:**
- Create: backend/app/services/conversation_deletion.py, backend/app/services/profile_deletion.py
- Create: backend/app/graph/delete_profile.py
- Modify: backend/app/api/conversations.py, backend/app/api/profiles.py
- Modify: backend/app/services/cv_manager.py, cv_deletion_ownership.py, backend/app/agent/checkpoint.py
- Test: backend/tests/integration/test_conversation_deletion.py, test_profile_deletion.py, backend/tests/integration/test_cv_manager_deletion.py, backend/tests/integration/test_agent_runner.py

- [x] Step 1: Write failing deletion/coordinator tests

Use FakeDriver, AttachmentStorage, and existing checkpoint test helpers:

~~~python
def test_delete_conversation_removes_only_owned_rows_and_checkpoints(
    deletion_context,
):
    result = deletion_context.delete(CONVERSATION_A_1)
    assert result.selected_conversation_id == CONVERSATION_A_2
    assert deletion_context.count_messages(CONVERSATION_A_1) == 0
    assert deletion_context.count_messages(CONVERSATION_B_1) > 0
    assert deletion_context.deleted_checkpoint_ids == [RUN_A_1]

def test_delete_last_conversation_creates_one_empty_replacement(
    deletion_context,
):
    result = deletion_context.delete(ONLY_CONVERSATION)
    assert result.replacement_conversation_id is not None
    assert deletion_context.count_conversations(PROFILE_A) == 1

def test_profile_delete_preserves_other_profile_and_global_job(
    deletion_context,
):
    deletion_context.delete_profile(PROFILE_A)
    assert deletion_context.profile_exists(PROFILE_B)
    assert deletion_context.job_exists(GLOBAL_JOB)
    assert deletion_context.evaluation_exists(GLOBAL_JOB, PROFILE_B)
    assert not deletion_context.evaluation_exists(GLOBAL_JOB, PROFILE_A)


def test_pending_profile_discard_skips_graph_and_restores_ready_fallback(
    pending_deletion_context,
):
    result = pending_deletion_context.delete_pending()
    assert result.active_profile.id == pending_deletion_context.ready_profile_id
    assert pending_deletion_context.pending_profile_exists() is False
    assert pending_deletion_context.pending_file_exists() is False
    assert pending_deletion_context.graph_delete_calls == []
~~~

Add fault-injection tests proving retained-file or graph cleanup failure leaves profiles.state == deleting, returns a safe retryable error, and never reports success. Cover a pending-shape deleting retry, which remains the unique incomplete profile and continues to block new upload until finalization.

- [x] Step 2: Run deletion tests to verify RED

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_conversation_deletion.py tests/integration/test_profile_deletion.py tests/integration/test_cv_manager_deletion.py -q
~~~

Expected: no coordinator or profile graph-delete module exists, and the old CV deletion path redacts rather than removes all profile conversations.

- [x] Step 3: Implement conversation deletion ordering

Create conversation_deletion.py with this order and no transaction spanning external work:

~~~python
async def delete_conversation(
    *,
    conversation_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    sqlite_path: str | Path,
) -> ConversationDeleteResult:
    async with session_scope(session_factory) as session:
        owner = await conversations_repo.get_owned(
            session, conversation_id=conversation_id
        )
        if owner is None:
            raise ConversationDeletionError(
                "CONVERSATION_NOT_FOUND", "conversation not found"
            )
        await assert_conversation_idle(
            session,
            conversation_id=conversation_id,
            code="CONVERSATION_DELETE_BLOCKED",
        )
        run_ids = await runs_repo.list_run_ids_for_conversation(
            session, conversation_id
        )
    async with open_checkpointer(sqlite_path) as saver:
        await delete_run_checkpoints(saver, run_ids)
    async with session_scope(session_factory) as session:
        await conversations_repo.delete(session, conversation_id)
        selected, deleted_was_last = await conversations_repo.delete_and_select(
            session, profile_id=owner.profile_id, conversation_id=conversation_id
        )
    return ConversationDeleteResult(
        deleted_conversation_id=conversation_id,
        selected_conversation_id=selected.id,
        replacement_conversation_id=selected.id if deleted_was_last else None,
    )
~~~

Implement delete_and_select so the final transaction cascades messages/runs/tools, preserves the current selected conversation when a non-selected row is deleted, and creates exactly one empty Chat mới row only when no conversation remains. Return the explicit deleted_was_last boolean; never infer replacement status from timestamps.

- [x] Step 4: Implement retryable profile deletion

Create profile_deletion.py with these phases: owner/activity validation; classify the profile as approved-shape or incomplete-shape; mark a ready or pending profile and its attachment deleting (or resume idempotently when both are already deleting); enumerate all profile run IDs regardless of source_attachment_id; open the existing AsyncSqliteSaver through open_checkpointer(sqlite_path) and delete those threads; delete the retained file idempotently; call exact profile graph branch deletion idempotently only for an approved-shape profile; final transaction selects the most recently opened remaining ready profile or clears workspace state, archives every other ready attachment, activates the fallback attachment when one exists, then deletes conversations, preferences, evaluations, chunks/documents/drafts, profile, and attachment. If any external phase fails, leave the original approved/incomplete field shape with deleting markers and return PROFILE_DELETE_RETRYABLE with no raw path/error.

Add delete_profile_branch(driver, profile_id) in graph/delete_profile.py. Its Cypher must match only Candidate with profile_id parameter and its owned CV/section/entry nodes, preserve Job/Skill nodes, and pass the existing allowlist assertion. Do not reuse delete_cv_branch, which intentionally preserves Candidate nodes, and never call this graph boundary for an incomplete pending/deleting profile.

- [x] Step 5: Replace old attachment-delete API semantics

Add the routes only after the coordinators compile:

~~~python
@router.delete("/conversations/{conversation_id}", response_model=ConversationDeleteResponse)
async def delete_conversation(conversation_id: UuidStr) -> ConversationDeleteResponse:
    return await conversation_deletion.delete_conversation(
        conversation_id=conversation_id,
        session_factory=get_session_factory(),
        sqlite_path=get_settings().SQLITE_PATH,
    )

@router.delete("/profiles/{profile_id}", response_model=ProfileDeleteResponse)
async def delete_profile(
    request: Request, profile_id: UuidStr
) -> ProfileDeleteResponse:
    return await profile_deletion.delete_profile(
        profile_id=profile_id,
        session_factory=get_session_factory(),
        storage=request.app.state.storage,
        graph_driver=request.app.state.neo4j_driver,
        sqlite_path=get_settings().SQLITE_PATH,
    )
~~~

Restrict or remove DELETE /api/cvs/{attachment_id} so it only handles unowned staged/failed attachments and cannot delete a profile CV. Update error maps and tests to ensure a profile delete removes every conversation even when messages lack source_attachment_id.

- [x] Step 6: Run deletion/checkpoint gates and commit

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_conversation_deletion.py tests/integration/test_profile_deletion.py tests/integration/test_cv_manager_deletion.py tests/integration/test_agent_runner.py tests/unit/test_job_graph_deletion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/services/conversation_deletion.py backend/app/services/profile_deletion.py backend/app/graph/delete_profile.py backend/app/api/conversations.py backend/app/api/profiles.py backend/app/api/cvs.py backend/app/services/cv_manager.py backend/app/services/cv_deletion_ownership.py backend/app/agent/checkpoint.py backend/tests/integration/test_conversation_deletion.py backend/tests/integration/test_profile_deletion.py backend/tests/integration/test_cv_manager_deletion.py backend/tests/integration/test_agent_runner.py backend/tests/unit/test_job_graph_deletion.py
git commit -m "feat: add retryable profile and conversation deletion"
~~~

---

### Task 8: Make Saved Jobs and evaluations profile-specific while keeping Jobs global

**Files:**
- Modify: backend/app/db/models/job_evaluations.py, backend/app/schemas/job_evaluations.py
- Modify: backend/app/services/evaluation_context.py, job_evaluation.py, saved_jobs.py, matching.py
- Modify: backend/app/repositories/job_evaluations.py, backend/app/api/jobs.py
- Test: backend/tests/unit/test_evaluation_context.py, test_job_evaluation.py, backend/tests/integration/test_job_evaluations.py, test_saved_jobs_api.py, test_match_jobs.py

- [x] Step 1: Write failing two-profile evaluation tests

Extend existing _seed_parents, _facts, and _match_payload fixtures:

~~~python
def test_one_saved_job_has_independent_current_evaluation_per_profile(
    evaluation_context,
):
    result_a = evaluation_context.evaluate(GLOBAL_JOB, PROFILE_A)
    result_b = evaluation_context.evaluate(GLOBAL_JOB, PROFILE_B)
    assert result_a.evaluation_id != result_b.evaluation_id
    assert evaluation_context.currentness(GLOBAL_JOB, PROFILE_A) == "current"
    assert evaluation_context.currentness(GLOBAL_JOB, PROFILE_B) == "current"

def test_delete_profile_removes_only_its_evaluations(evaluation_context):
    evaluation_context.delete_profile(PROFILE_A)
    assert evaluation_context.saved_job_exists(GLOBAL_JOB)
    assert evaluation_context.evaluation_exists(GLOBAL_JOB, PROFILE_B)
    assert not evaluation_context.evaluation_exists(GLOBAL_JOB, PROFILE_A)
~~~

Add a zero-provider activation test showing switching profiles changes list/detail currentness only through context lookup and does not evaluate automatically.

- [x] Step 2: Run evaluation tests to verify RED

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_evaluation_context.py tests/unit/test_job_evaluation.py tests/integration/test_job_evaluations.py tests/integration/test_saved_jobs_api.py tests/integration/test_match_jobs.py -q
~~~

Expected: the current uniqueness key omits profile_id, and services read the singleton active profile/preferences.

- [x] Step 3: Add profile identity to context and persistence

Change EvaluationContextFacts to require profile_id and include it in canonical JSON/hash bytes before active_attachment_id. Change JobEvaluationRecord, repository filters, service _resolve_context, and API response currentness to carry the profile ID. Use the active workspace profile only when the API caller omits an explicit profile; never accept a client profile ID that is not the workspace owner.

- [x] Step 4: Preserve global Saved Job behavior

Refactor saved_jobs.py and matching.py shared-context loaders to resolve (profile, preferences, attachment) from workspace_state. Keep Job list/detail global and preserve exact no-provider/no-mutation GET behavior. Add profile ID to cache/currentness keys, invalidate currentness after activation/re-extraction, and never auto-call evaluate_job.

- [x] Step 5: Run evaluation/static gates and commit

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_evaluation_context.py tests/unit/test_job_evaluation.py tests/integration/test_job_evaluations.py tests/integration/test_saved_jobs_api.py tests/integration/test_match_jobs.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/db/models/job_evaluations.py backend/app/schemas/job_evaluations.py backend/app/services/evaluation_context.py backend/app/services/job_evaluation.py backend/app/services/saved_jobs.py backend/app/services/matching.py backend/app/repositories/job_evaluations.py backend/app/api/jobs.py backend/tests/unit/test_evaluation_context.py backend/tests/unit/test_job_evaluation.py backend/tests/integration/test_job_evaluations.py backend/tests/integration/test_saved_jobs_api.py backend/tests/integration/test_match_jobs.py
git commit -m "feat: scope evaluations to profiles"
~~~

---

### Task 9: Key Neo4j Candidate/CV projections, reads, rebuilds, and profile deletion by profile ID

**Files:**
- Modify: backend/app/graph/constraints.py, sync_candidate.py, sync_cv.py, consistency.py, selected_skill_projection.py
- Modify: backend/app/graph/observability.py, observability_cv.py, rebuild_snapshot.py, rebuild.py, rebuild_ops.py
- Modify: backend/app/services/observability.py, matching.py, job_evaluation.py
- Modify: backend/app/graph/delete_profile.py
- Test: backend/tests/unit/test_graph_setup.py, test_cv_graph.py, test_observability_graph.py, test_job_graph_deletion.py, backend/tests/integration/test_candidate_sync.py, test_graph_rebuild_behavior.py, test_graph_rebuild_contracts.py, test_observability_api.py, test_job_evaluations.py

- [x] Step 1: Add failing graph isolation tests

Extend fake-driver tests with two profile branches:

~~~python
def test_candidate_and_cv_sync_use_profile_identity(graph_context):
    graph_context.sync_candidate(PROFILE_A, graph_context.profile_a)
    graph_context.sync_candidate(PROFILE_B, graph_context.profile_b)
    assert graph_context.candidate_merge_keys() == {PROFILE_A, PROFILE_B}

def test_graph_reads_never_choose_first_candidate(graph_context):
    snapshot = graph_context.load_snapshot(PROFILE_B)
    assert snapshot.candidate.profile_id == PROFILE_B
~~~

Add rebuild assertions that every ready profile is projected, deleted profile branches do not remove global Jobs/Skills, and consistency checks compare only the requested profile revision.

- [x] Step 2: Run graph tests to verify RED

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_graph_setup.py tests/unit/test_cv_graph.py tests/unit/test_observability_graph.py tests/unit/test_job_graph_deletion.py tests/integration/test_candidate_sync.py tests/integration/test_graph_rebuild_behavior.py tests/integration/test_graph_rebuild_contracts.py tests/integration/test_observability_api.py -q
~~~

Expected: graph functions still hard-code active, select the first Candidate, and rebuild one branch.

- [x] Step 3: Set profile-keyed graph identity

Pass profile_id to sync_candidate, sync_cv, payload builders, consistency checks, selected-skill snapshots, and observability loaders. Replace the singleton Candidate constraint with a unique Candidate.profile_id constraint, and use Candidate with profile_id parameter as the merge/read key. Key CV/section/entry node IDs with profile_id plus stable document IDs; preserve source attachment/hash as properties for evidence and stale checks. Ensure profile-scoped Cypher remains allowlisted and parameterized.

- [x] Step 4: Scope graph reads and rebuild every ready profile

Change load_bounded_graph_projection, load_active_cv_branch, selected-job skill maps, and evaluation retrieval to require a profile ID. Replace first Candidate and literal active queries with the profile parameter. Make load_rebuild_inputs return all ready profile/document rows and make rebuild_graph loop over them while retaining global Job/Skill seed/rebuild behavior. A graph refresh failure after profile activation leaves SQLite selection committed and returns NEO4J_SYNC_FAILED/safe rebuild guidance.

- [x] Step 5: Run graph/evaluation gates and commit

~~~powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_graph_setup.py tests/unit/test_cv_graph.py tests/unit/test_observability_graph.py tests/unit/test_job_graph_deletion.py tests/integration/test_candidate_sync.py tests/integration/test_graph_rebuild_behavior.py tests/integration/test_graph_rebuild_contracts.py tests/integration/test_observability_api.py tests/integration/test_job_evaluations.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/graph/constraints.py backend/app/graph/sync_candidate.py backend/app/graph/sync_cv.py backend/app/graph/consistency.py backend/app/graph/selected_skill_projection.py backend/app/graph/observability.py backend/app/graph/observability_cv.py backend/app/graph/rebuild_snapshot.py backend/app/graph/rebuild.py backend/app/graph/rebuild_ops.py backend/app/graph/delete_profile.py backend/app/services/observability.py backend/app/services/matching.py backend/app/services/job_evaluation.py backend/tests/unit/test_graph_setup.py backend/tests/unit/test_cv_graph.py backend/tests/unit/test_observability_graph.py backend/tests/unit/test_job_graph_deletion.py backend/tests/integration/test_candidate_sync.py backend/tests/integration/test_graph_rebuild_behavior.py backend/tests/integration/test_graph_rebuild_contracts.py backend/tests/integration/test_observability_api.py backend/tests/integration/test_job_evaluations.py
git commit -m "feat: key graph projections by profile"
~~~

---

### Task 10: Add strict frontend profile/conversation DTOs and typed transports

**Files:**
- Modify: frontend/src/features/profile/types.ts, api.ts
- Create: frontend/src/features/profile/conversationTypes.ts
- Modify: frontend/src/lib/api/chat.ts
- Test: frontend/src/test/profile-api.test.ts, frontend/src/test/conversation-api.test.ts, frontend/src/test/saved-jobs-api.test.ts, frontend/src/test/cv-sidebar.test.tsx

- [x] Step 1: Write failing parser and request tests

Add strict UUID fixtures and safe fields:

~~~ts
it('parses bounded profile metadata and rejects raw CV fields', () => {
  const parsed = parseProfileListResponse({
    items: [{
      id: PROFILE_A,
      display_name: 'Ada',
      cv_filename: 'ada.pdf',
      attachment_state: 'active',
      location: 'London',
      skill_tags: [{key: 'python', label: 'Python'}],
      skill_count: 1,
       extraction_version: 'cv-v2',
       source_hash: 'hash-a',
       state: 'ready',
       setup_status: null,
       is_active: true,
      created_at: NOW,
      updated_at: NOW,
      last_opened_at: NOW,
    }],
    active_profile_id: PROFILE_A,
  });
  expect(parsed.items[0]?.location).toBe('London');
  expect(() => parseProfileListResponse({
    items: [],
    active_profile_id: null,
    storage_path: 'secret',
  })).toThrow();
});

it('sends profile and conversation IDs in paths', async () => {
  await activateProfile(PROFILE_A);
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/api/profiles/' + PROFILE_A + '/activate'),
    expect.anything(),
  );
});
~~~

Cover every endpoint method, stable error parsing, cursor query, empty replacement selection, and rejection of unknown/raw fields. Add ready/pending/deleting shape fixtures: ready requires `setup_status=null` and non-null approved fields, pending requires a fixed non-null setup status plus null location/extraction/source fields and empty skill metadata, and deleting preserves either coherent shape.

- [x] Step 2: Run frontend transport tests to verify RED

~~~powershell
Set-Location frontend
npm test -- --run src/test/profile-api.test.ts src/test/conversation-api.test.ts
~~~

Expected: profile/conversation types and clients are missing.

- [x] Step 3: Define strict DTOs and parsers

Create conversationTypes.ts and extend profile/types.ts with exact TypeScript types:

~~~ts
export type ProfileSkillTag = {key: string; label: string};

export type CandidateSkillDetail = {
  skill: {
    canonical_key: string;
    display_name: string;
    aliases: string[];
    category: string | null;
  };
  confidence: number;
  proficiency: 'beginner' | 'intermediate' | 'advanced' | 'unknown';
  years: number | null;
  source: 'cv' | 'user_correction';
  excluded: boolean;
  evidence: string[];
};

export type ExperienceDetail = {
  title: string; company: string | null;
  start_date_text: string | null; end_date_text: string | null;
  summary: string;
};

export type EducationDetail = {
  institution: string; degree: string | null; field: string | null;
  graduation_year: number | null;
};

export type LanguageDetail = {name: string; proficiency: string | null};

export type ProfileListItem = {
  id: string;
  display_name: string;
  cv_filename: string;
  attachment_state: 'staged' | 'active' | 'archived' | 'failed' | 'deleting';
  location: string | null;
  skill_tags: ProfileSkillTag[];
  skill_count: number;
  extraction_version: string | null;
  source_hash: string | null;
  state: 'pending' | 'ready' | 'deleting';
  setup_status: 'awaiting_extraction' | 'awaiting_approval' | 'extraction_failed' | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
};

export type CandidateProfileDetail = {
  full_name: string | null;
  location: string | null;
  summary: string;
  current_title: string | null;
  total_experience_years: number | null;
  skills: CandidateSkillDetail[];
  experiences: ExperienceDetail[];
  education: EducationDetail[];
  languages: LanguageDetail[];
  extraction_confidence: number;
};

export type ProfileDetail = ProfileListItem & {
  profile: CandidateProfileDetail;
  preferences: JobPreferencesSummary;
  attachment: AttachmentPublic;
  selected_conversation_id: string | null;
};

export type ConversationSummary = {
  id: string;
  profile_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_opened_at: string;
  is_selected: boolean;
};

export type SafeWarning = {
  code: string;
  summary: string;
  guidance: string;
};

export type SelectionResponse = {
  profile: ProfileDetail;
  conversation: ConversationSummary | null;
  warning: SafeWarning | null;
};

export type PendingProfileBootstrap = {
  profile: ProfileListItem;
  conversation: ConversationSummary;
  start_extraction: boolean;
};

export type CvUploadResponse = {
  attachment: AttachmentPublic;
  outcome: 'new_pending' | 'retry_pending' | 'existing_pending' | 'existing_active' | 'existing_profile';
  profile: ProfileUploadSummary | null;
  draft: DraftUploadSummary | null;
  bootstrap: PendingProfileBootstrap | null;
};
~~~

The backend model and frontend parser enforce this outcome/field coupling matrix:

| outcome | bootstrap | start_extraction | identity rule |
| --- | --- | --- | --- |
| `new_pending` | required | true | new server profile/conversation IDs |
| `retry_pending` | required | true | same pending profile/conversation IDs |
| `existing_pending` | required | false when a draft or active/interrupted run exists; otherwise server-derived | same pending profile/conversation IDs |
| `existing_active` | null | n/a | safe active ready-profile reference only |
| `existing_profile` | null | n/a | safe archived ready-profile reference only |

Pending outcomes reject a missing bootstrap, non-pending profile, mismatched profile/conversation ownership, or mismatched top-level attachment. Ready reuse outcomes reject a non-null bootstrap. Parsers must enforce UUID v4, exact keys, bounded strings, safe attachment metadata, this lifecycle/outcome matrix, and no storage path, contact details, raw CV text, or provider payloads. Keep the existing ChatApiError safe status/code/summary mapping.

- [x] Step 4: Implement typed profile and conversation clients

Rename the existing singleton compatibility reader to fetchActiveProfileCompat(signal), then add fetchProfiles, fetchProfile(profileId, signal), updateProfile, activateProfile, deleteProfile, fetchProfileConversations, createProfileConversation, selectConversation, and deleteConversation to features/profile/api.ts. Export defaultProfileApi as an object containing those functions so workspaceState.ts has one injectable transport contract. Add fetchConversationHistory(conversationId, query, signal) and streamConversationTurn(conversationId, request, callbacks, signal) to lib/api/chat.ts; preserve SSE parsing/event names and streamChatResume(runId, action, callbacks, signal). Every path segment uses encodeURIComponent; no client request sends profile JSON or attachment ownership.

- [x] Step 5: Run transport/static gates and commit

~~~powershell
npm test -- --run src/test/profile-api.test.ts src/test/conversation-api.test.ts src/test/saved-jobs-api.test.ts src/test/cv-sidebar.test.tsx
npm run lint
npm run typecheck
Set-Location ..
git add frontend/src/features/profile/types.ts frontend/src/features/profile/conversationTypes.ts frontend/src/features/profile/api.ts frontend/src/lib/api/chat.ts frontend/src/test/profile-api.test.ts frontend/src/test/conversation-api.test.ts frontend/src/test/saved-jobs-api.test.ts frontend/src/test/cv-sidebar.test.tsx
git commit -m "feat(frontend): add profile conversation transports"
~~~

---

### Task 11: Lift workspace selection and key the single ChatPage reducer by conversation

**Files:**
- Create: frontend/src/features/profile/workspaceState.ts
- Create: frontend/src/features/chat/model.ts
- Modify: frontend/src/app/App.tsx, frontend/src/features/chat/ChatPage.tsx, frontend/src/features/chat/reducer.ts, frontend/src/features/chat/history.ts
- Modify: frontend/src/features/observability/ObservabilitySidebar.tsx
- Test: frontend/src/test/profile-workspace-state.test.tsx, frontend/src/test/chat-page.test.tsx, frontend/src/app/App.test.tsx

- [x] Step 1: Add failing workspace and keyed-hydration tests

Use injected transports and deferred promises:

~~~tsx
it('aborts old history and resets before hydrating selected conversation', async () => {
  const first = deferred<HistoryPage>();
  const loadHistory = vi.fn()
    .mockImplementationOnce(() => first.promise)
    .mockResolvedValueOnce({
      items: [messageFrom(CONVERSATION_B)],
      next_cursor: null,
    });
  render(<App deps={{chat: {loadHistory}, sidebar: profileDeps}} />);
  await userEvent.click(screen.getByRole('button', {name: /Profile B/}));
  expect(loadHistory).toHaveBeenLastCalledWith(
    CONVERSATION_B,
    {limit: 50},
    expect.anything(),
  );
  expect(screen.queryByText('message from A')).not.toBeInTheDocument();
});

it('applies the server-selected conversation after create', async () => {
  const create = vi.fn().mockResolvedValue(selectedConversationResponse);
  const {result} = renderHook(() => useProfileWorkspaceState({
    createProfileConversation: create,
  }));
  await act(() => result.current.createConversation(PROFILE_A));
  expect(create).toHaveBeenCalledTimes(1);
  expect(result.current.state.selectedConversationId).toBe(
    selectedConversationResponse.conversation.id,
  );
});
~~~

Test that the workspace reducer applies server IDs after activation/create/delete, keeps stale data on failed reads, and disables mutations when interactionLocked is true.

- [x] Step 2: Run keyed-hydration tests to verify RED

~~~powershell
Set-Location frontend
npm test -- --run src/test/profile-workspace-state.test.tsx src/test/chat-page.test.tsx src/app/App.test.tsx
~~~

Expected: current ChatPage has no conversation ID prop and only calls the singleton history endpoint.

- [x] Step 3: Create the workspace state owner

Create workspaceState.ts with a reducer/hook shaped as follows:

~~~ts
export type ProfileWorkspaceState = {
  profiles: ProfileListItem[];
  activeProfileId: string | null;
  selectedConversationId: string | null;
  conversations: ConversationSummary[];
  pending: ReadonlySet<string>;
  error: string | null;
};

export type ProfileWorkspaceController = {
  state: ProfileWorkspaceState;
  adoptBootstrap: (bootstrap: PendingProfileBootstrap) => void;
  activate: (profileId: string) => Promise<void>;
  createConversation: (profileId: string) => Promise<void>;
  selectConversation: (conversationId: string) => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  reload: () => Promise<void>;
};

export type ProfileWorkspaceApi = Pick<
  typeof defaultProfileApi,
  | 'fetchProfiles'
  | 'fetchProfileConversations'
  | 'activateProfile'
  | 'createProfileConversation'
  | 'selectConversation'
  | 'deleteConversation'
>;

export type ProfileWorkspaceAction =
  | {type: 'profiles/loaded'; response: ProfileListResponse}
  | {type: 'conversations/loaded'; response: ConversationListResponse}
  | {type: 'workspace/bootstrapAdopted'; bootstrap: PendingProfileBootstrap}
  | {type: 'profile/activated'; response: SelectionResponse}
  | {type: 'conversation/created'; response: ConversationMutationResponse}
  | {type: 'conversation/selected'; response: ConversationMutationResponse}
  | {type: 'conversation/deleted'; response: ConversationDeleteResponse}
  | {type: 'mutation/started'; key: string}
  | {type: 'mutation/finished'; key: string}
  | {type: 'mutation/failed'; key: string; error: string};

export const initialProfileWorkspaceState: ProfileWorkspaceState = {
  profiles: [], activeProfileId: null, selectedConversationId: null,
  conversations: [], pending: new Set(), error: null,
};

export function profileWorkspaceReducer(
  state: ProfileWorkspaceState,
  action: ProfileWorkspaceAction,
): ProfileWorkspaceState {
  if (action.type === 'profiles/loaded') {
    return {...state, profiles: action.response.items,
      activeProfileId: action.response.active_profile_id, error: null};
  }
  if (action.type === 'conversations/loaded') {
    const selected = action.response.items.find((item) => item.is_selected) ?? null;
    return {...state, conversations: action.response.items,
      selectedConversationId: selected?.id ?? null, error: null};
  }
  if (action.type === 'workspace/bootstrapAdopted') {
    const {profile, conversation} = action.bootstrap;
    const profiles = [profile, ...state.profiles.filter((item) => item.id !== profile.id)];
    return {...state, profiles, activeProfileId: profile.id,
      selectedConversationId: conversation.id, conversations: [conversation],
      error: null};
  }
  if (action.type === 'profile/activated') {
    return {...state, activeProfileId: action.response.profile.id,
      selectedConversationId: action.response.conversation?.id ?? null,
      conversations: action.response.conversation ? [action.response.conversation] : [],
      error: action.response.warning?.summary ?? null};
  }
  if (action.type === 'conversation/created') {
    const selected = action.response.conversation;
    return {...state, selectedConversationId: selected.id,
      conversations: [selected, ...state.conversations.map((item) => ({
        ...item, is_selected: item.id === selected.id,
      }))]};
  }
  if (action.type === 'conversation/selected') {
    const selected = action.response.conversation;
    return {...state, selectedConversationId: selected.id,
      conversations: state.conversations.map((item) => (
        item.id === selected.id ? selected : {...item, is_selected: false}
      ))};
  }
  if (action.type === 'conversation/deleted') {
    const selected = action.response.selected_conversation;
    const remaining = state.conversations
      .filter((item) => item.id !== action.response.deleted_conversation_id)
      .map((item) => item.id === selected.id ? selected : {...item, is_selected: false});
    return {...state,
      selectedConversationId: selected.id,
      conversations: remaining.some((item) => item.id === selected.id)
        ? remaining : [selected, ...remaining]};
  }
  if (action.type === 'mutation/started') {
    return {...state, pending: new Set([...state.pending, action.key]), error: null};
  }
  if (action.type === 'mutation/finished') {
    const pending = new Set(state.pending); pending.delete(action.key);
    return {...state, pending};
  }
  return {...state, error: action.error};
}

export function useProfileWorkspaceState(
  api: ProfileWorkspaceApi = defaultProfileApi,
): ProfileWorkspaceController {
  const [state, dispatch] = useReducer(
    profileWorkspaceReducer, initialProfileWorkspaceState,
  );
  const pendingRef = useRef(new Set<string>());
  const requestRef = useRef(0);

  const mutate = useCallback(async <T,>(
    key: string,
    request: () => Promise<T>,
    action: (value: T) => ProfileWorkspaceAction,
  ) => {
    if (pendingRef.current.has(key)) return;
    pendingRef.current.add(key);
    dispatch({type: 'mutation/started', key});
    try {
      dispatch(action(await request()));
    } catch (error) {
      const summary = error instanceof Error ? error.message : 'Request failed';
      dispatch({type: 'mutation/failed', key, error: summary});
    } finally {
      pendingRef.current.delete(key);
      dispatch({type: 'mutation/finished', key});
    }
  }, []);

  const activate = useCallback(async (profileId: string) => {
    const key = 'activate:' + profileId;
    if (pendingRef.current.has(key)) return;
    pendingRef.current.add(key);
    dispatch({type: 'mutation/started', key});
    try {
      const response = await api.activateProfile(profileId);
      dispatch({type: 'profile/activated', response});
      const conversations = await api.fetchProfileConversations(
        profileId, {limit: 50},
      );
      dispatch({type: 'conversations/loaded', response: conversations});
    } catch (error) {
      const summary = error instanceof Error ? error.message : 'Request failed';
      dispatch({type: 'mutation/failed', key, error: summary});
    } finally {
      pendingRef.current.delete(key);
      dispatch({type: 'mutation/finished', key});
    }
  }, [api]);

  const createConversation = useCallback((profileId: string) => mutate(
    'create:' + profileId,
    () => api.createProfileConversation(profileId),
    (response) => ({type: 'conversation/created', response}),
  ), [api, mutate]);

  const selectConversation = useCallback((conversationId: string) => mutate(
    'select:' + conversationId,
    () => api.selectConversation(conversationId),
    (response) => ({type: 'conversation/selected', response}),
  ), [api, mutate]);

  const deleteConversation = useCallback((conversationId: string) => mutate(
    'delete:' + conversationId,
    () => api.deleteConversation(conversationId),
    (response) => ({type: 'conversation/deleted', response}),
  ), [api, mutate]);

  const reload = useCallback(async () => {
    const requestId = ++requestRef.current;
    const profiles = await api.fetchProfiles();
    if (requestId !== requestRef.current) return;
    dispatch({type: 'profiles/loaded', response: profiles});
    if (profiles.active_profile_id !== null) {
      const conversations = await api.fetchProfileConversations(
        profiles.active_profile_id, {limit: 50},
      );
      if (requestId !== requestRef.current) return;
      dispatch({type: 'conversations/loaded', response: conversations});
    }
  }, [api]);

  return {
    state,
    adoptBootstrap: (bootstrap) => dispatch({
      type: 'workspace/bootstrapAdopted', bootstrap,
    }),
    activate,
    createConversation,
    selectConversation,
    deleteConversation,
    reload,
  };
}
~~~

The implementation must include concrete actions for profiles loaded, conversations loaded, activation started/succeeded/failed, conversation created/selected/deleted, and reset error. Task 5 extends this completed ready-profile baseline with `workspace/bootstrapAdopted`; that action must apply only the server-returned pending profile and conversation IDs, and it must not issue an activation or conversation-create request. Apply only server response IDs; never optimistically invent a replacement conversation or active profile.

- [x] Step 4: Key ChatPage without creating a second chat store

Move client DTO interfaces used by history.ts/reducer.ts into features/chat/model.ts and keep type-only compatibility re-exports. Add conversationId: string | null to ChatPageProps. On ID change, abort the previous controller, dispatch history/reset with an empty page, and hydrate through fetchConversationHistory(conversationId, query, signal). The completed baseline disables the composer when ID is null. Task 5 replaces the ready-only profile gate with the frozen setup-state matrix: enable ordinary messages for ready profiles and pending `awaiting_approval` correction turns; disable them for pending `awaiting_extraction` and `extraction_failed`; still allow the sidebar-owned automatic extraction turn for an adopted bootstrap with `start_extraction=true`. Pass the same ID to turn/reprocess transports; keep automatic extraction, correction, approval resume, and all SSE events in `chatReducer`.

- [x] Step 5: Wire App and workspace-wide interaction lock

In App.tsx, render workspace state above ChatPage, pass selectedConversationId into ChatPage, and combine onInteractionLockChange with workspace pending state. Pass the resulting lock to every profile/conversation selector, menu, dialog, upload, re-extract, and observability mutation. A ready-profile switch first calls POST /api/profiles/{id}/activate, then replaces profile/conversation state from the response and bumps saved-job/observability invalidation keys. A Task 5 upload bootstrap instead dispatches `workspace/bootstrapAdopted` before setting the sidebar turn, uses the returned `start_extraction` flag, and never activates or creates an owner client-side.

- [x] Step 6: Run frontend state gates and commit

~~~powershell
npm test -- --run src/test/profile-workspace-state.test.tsx src/test/chat-page.test.tsx src/app/App.test.tsx src/test/sse-reducer.test.ts
npm run lint
npm run typecheck
Set-Location ..
git add frontend/src/features/profile/workspaceState.ts frontend/src/features/chat/model.ts frontend/src/app/App.tsx frontend/src/features/chat/ChatPage.tsx frontend/src/features/chat/reducer.ts frontend/src/features/chat/history.ts frontend/src/features/observability/ObservabilitySidebar.tsx frontend/src/test/profile-workspace-state.test.tsx frontend/src/test/chat-page.test.tsx frontend/src/app/App.test.tsx frontend/src/test/sse-reducer.test.ts
git commit -m "feat(frontend): key chat state by conversation"
~~~

---

### Task 12: Build Astryx profile/conversation navigation and confirmation dialogs

**Files:**
- Create: frontend/src/features/profile/ProfileConversationSidebar.tsx
- Create: frontend/src/features/profile/ProfileListPanel.tsx, ConversationListPanel.tsx
- Create: frontend/src/features/profile/ProfileRenameDialog.tsx, ProfileDeleteDialog.tsx, ConversationDeleteDialog.tsx
- Modify: frontend/src/features/profile/CvSidebar.tsx, ProfileOverviewPanel.tsx, frontend/src/features/observability/ObservabilitySidebar.tsx
- Test: frontend/src/test/profile-conversation-sidebar.test.tsx, profile-dialogs.test.tsx, cv-sidebar.test.tsx

- [x] Step 1: Re-run Astryx discovery before UI edits

From frontend/, run the installed CLI and retain its output in implementation notes:

~~~powershell
npx astryx build "CV profile switcher with location and skill tags, nested conversation history, new chat, rename and destructive confirmation dialogs" --detail compact
npx astryx search "profile list conversation history sidebar tags alert dialog" --detail compact
npx astryx component SideNav --detail compact
npx astryx component List --detail compact
npx astryx component Token --detail compact
npx astryx component DropdownMenu --detail compact
npx astryx component Dialog --detail compact
npx astryx component AlertDialog --detail compact
npx astryx component MobileNav --detail compact
~~~

Use installed props, not invented names. The confirmed AlertDialog props are isOpen, onOpenChange, title, description, actionLabel, onAction, optional cancelLabel, and isActionLoading.

- [x] Step 2: Write failing UI metadata and confirmation tests

~~~tsx
it('renders location, bounded skill tokens, and overflow without inference', () => {
  render(
    <ProfileListPanel
      profiles={[profileWithSkills, profileWithoutMetadata]}
      activeProfileId={profileWithSkills.id}
      isInteractionLocked={false}
      onActivate={vi.fn()}
      onRename={vi.fn()}
      onReextract={vi.fn()}
      onRetrySetup={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  expect(screen.getByText('Berlin')).toBeInTheDocument();
  expect(screen.getByText('Python')).toBeInTheDocument();
  expect(screen.getByText('+3')).toBeInTheDocument();
  expect(screen.getByText('Location unavailable')).toBeInTheDocument();
  expect(screen.getByText('No extracted skills')).toBeInTheDocument();
});

it('renders pending setup status and exposes retry/discard only', async () => {
  const retry = vi.fn();
  render(<ProfileListPanel
    profiles={[pendingProfile]}
    activeProfileId={pendingProfile.id}
    isInteractionLocked={false}
    onActivate={vi.fn()}
    onRename={vi.fn()}
    onReextract={vi.fn()}
    onRetrySetup={retry}
    onDelete={vi.fn()}
  />);
  expect(screen.getByText('Awaiting extraction')).toBeInTheDocument();
  expect(screen.queryByText('Location unavailable')).toBeInTheDocument();
  expect(screen.queryByRole('button', {name: /Rename/})).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name: /Re-extract/})).not.toBeInTheDocument();
  expect(screen.getByRole('button', {name: /Retry/})).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', {name: /Retry/}));
  expect(retry).toHaveBeenCalledWith(pendingProfile);
});

it('requires confirmation and performs one conversation delete request', async () => {
  const remove = vi.fn().mockResolvedValue(deleteResponse);
  render(
    <ConversationDeleteDialog
      conversation={conversation}
      isOpen
      isActionLoading={false}
      onOpenChange={vi.fn()}
      onConfirm={remove}
    />,
  );
  expect(remove).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', {name: /Delete permanently/}));
  expect(remove).toHaveBeenCalledTimes(1);
});
~~~

Cover profile rename (only display_name changes), profile delete warning naming CV/profile, pending retry/discard actions, conversation delete warning, cancel/no-request, loading/focus return, Escape, keyboard visibility, and mobile drawer rendering. A pending row must never offer rename or re-extract, and its setup status must be rendered from the server value without inferring approved metadata.

- [x] Step 3: Run UI tests to verify RED

~~~powershell
Set-Location frontend
npm test -- --run src/test/profile-conversation-sidebar.test.tsx src/test/profile-dialogs.test.tsx src/test/cv-sidebar.test.tsx
~~~

Expected: the new components and dialogs do not exist.

- [x] Step 4: Implement Astryx profile rows

Define the panel props before writing markup:

~~~tsx
type ProfileListPanelProps = {
  profiles: readonly ProfileListItem[];
  activeProfileId: string | null;
  isInteractionLocked: boolean;
  onActivate: (profileId: string) => void;
  onRename: (profile: ProfileListItem) => void;
  onReextract: (profile: ProfileListItem) => void;
  onRetrySetup: (profile: ProfileListItem) => void;
  onDelete: (profile: ProfileListItem) => void;
};
~~~

Use SideNavSection/SideNavItem for profile groups and List/ListItem for dense rows. A profile row displays display_name, sanitized cv_filename, persisted location or the neutral text Location unavailable, and at most four Token components followed by +N when skill_count exceeds the rendered tags. Show No extracted skills when skill_count is zero. Use the server skill_tags order; do not lowercase, deduplicate, or invent tags in React. Render the server setup_status for pending rows (`Awaiting extraction`, `Awaiting approval`, or `Extraction failed`) and keep their location/tags empty. Put row actions in an adjacent Astryx DropdownMenu rather than nesting interactive controls inside ListItem. Ready rows may rename, re-extract, or delete; pending rows may retry or discard only, and deleting a pending row is labeled as discarding setup. Retry opens the existing shared PDF picker and sends the selected `File` through `POST /api/attachments/cv`; it does not invent a retry endpoint. The response must be `retry_pending`, preserve the same bootstrap profile/conversation IDs, and set `start_extraction=true` before App schedules one extraction turn. Discard uses the normal profile-delete coordinator.

- [x] Step 5: Implement conversation rows and dialogs

Define the mutation components with explicit props:

~~~tsx
type ConversationListPanelProps = {
  profileId: string | null;
  conversations: readonly ConversationSummary[];
  selectedConversationId: string | null;
  isInteractionLocked: boolean;
  onCreate: (profileId: string) => void;
  onSelect: (conversationId: string) => void;
  onDelete: (conversation: ConversationSummary) => void;
};

type ConversationDeleteDialogProps = {
  conversation: ConversationSummary | null;
  isOpen: boolean;
  isActionLoading: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (conversationId: string) => Promise<void>;
};
~~~

Render a Chat mới action above the selected ready profile’s conversation list. Conversation rows show server title, localized last activity, selected state, and a delete menu. A pending profile exposes only its bootstrap conversation; it cannot create/select/delete conversations, while the correction composer is governed by Task 5’s setup-state matrix. ProfileRenameDialog uses Astryx Dialog/TextInput and sends exactly one PATCH; ProfileDeleteDialog and ConversationDeleteDialog use AlertDialog with the target name, irreversible warning, loading lock, cancel/no-op, and focus restoration. Disable all selection/create/delete/re-extract controls when isInteractionLocked is true, and disable rename/re-extract for pending rows regardless of lock state.

- [x] Step 6: Preserve responsive shell and upload/observability seams

Refactor CvSidebar to compose the new profile/conversation panels while keeping AppShell/SideNav collapse and the mobile render branch. Change the active-state upload label from Replace CV to Upload new CV so the action clearly creates another profile; explicit Re-extract CV remains a separate selected-profile menu action. Keep upload and approval presentation in the existing ChatPage path. Pass selected profile ID to observability/CV manager panels; do not add a second SSE/reducer owner or a second design system.

- [x] Step 7: Run UI/static gates and commit

~~~powershell
npm test -- --run src/test/profile-conversation-sidebar.test.tsx src/test/profile-dialogs.test.tsx src/test/cv-sidebar.test.tsx src/test/observability-sidebar.test.tsx
npm run lint
npm run typecheck
npm run build
Set-Location ..
git add frontend/src/features/profile/ProfileConversationSidebar.tsx frontend/src/features/profile/ProfileListPanel.tsx frontend/src/features/profile/ConversationListPanel.tsx frontend/src/features/profile/ProfileRenameDialog.tsx frontend/src/features/profile/ProfileDeleteDialog.tsx frontend/src/features/profile/ConversationDeleteDialog.tsx frontend/src/features/profile/CvSidebar.tsx frontend/src/features/profile/ProfileOverviewPanel.tsx frontend/src/features/observability/ObservabilitySidebar.tsx frontend/src/test/profile-conversation-sidebar.test.tsx frontend/src/test/profile-dialogs.test.tsx frontend/src/test/cv-sidebar.test.tsx frontend/src/test/observability-sidebar.test.tsx
git commit -m "feat(frontend): add Astryx profile chat navigation"
~~~

---

### Task 13: Re-scope observability, CV actions, and Saved Job invalidation to the selected profile

**Files:**
- Modify: frontend/src/features/observability/api.ts, state.ts, types.ts, ObservabilitySidebar.tsx, CvManagerPanel.tsx, CvDeleteDialog.tsx
- Modify: frontend/src/features/jobs/savedJobsState.ts, SavedJobsPanel.tsx, SavedJobDetail.tsx
- Modify: frontend/src/features/profile/api.ts, CvSidebar.tsx, App.tsx
- Test: frontend/src/test/observability-api.test.ts, observability-state.test.tsx, observability-sidebar.test.tsx, cv-manager.test.tsx, saved-jobs-state.test.tsx, saved-jobs-panel.test.tsx

- [ ] Step 1: Add failing stale-cache/profile-scope tests

~~~tsx
it('drops profile A observability data when profile B becomes active', async () => {
  const state = renderWithProfileSwitch(PROFILE_A, PROFILE_B);
  await state.activate(PROFILE_B);
  expect(screen.queryByText('A-only chunk')).not.toBeInTheDocument();
  expect(state.graphRequest).toHaveBeenLastCalledWith(PROFILE_B, expect.anything());
});

it('marks evaluations stale on profile switch without evaluating', async () => {
  await switchProfile(PROFILE_B);
  expect(evaluateJob).not.toHaveBeenCalled();
  expect(screen.getByText('Evaluation stale')).toBeInTheDocument();
});

it('renders a pending profile safe state without observability or evaluation calls', async () => {
  const state = renderWithProfileSwitch(PENDING_PROFILE, PROFILE_A);
  await state.selectProfile(PENDING_PROFILE.id);
  expect(state.fetchChunks).not.toHaveBeenCalled();
  expect(state.fetchRuns).not.toHaveBeenCalled();
  expect(state.fetchGraph).not.toHaveBeenCalled();
  expect(state.fetchCurrentness).not.toHaveBeenCalled();
  expect(state.evaluateJob).not.toHaveBeenCalled();
  expect(screen.getByText('Profile setup in progress')).toBeInTheDocument();
});
~~~

- [ ] Step 2: Run focused tests to verify RED

~~~powershell
Set-Location frontend
npm test -- --run src/test/observability-api.test.ts src/test/observability-state.test.tsx src/test/observability-sidebar.test.tsx src/test/cv-manager.test.tsx src/test/saved-jobs-state.test.tsx src/test/saved-jobs-panel.test.tsx
~~~

Expected: observability calls still use global/active attachment state and saved-job currentness has no profile key.

- [ ] Step 3: Parameterize observability and CV manager clients

Add profileId to profile-owned observability requests and cache keys. On profile activation, abort/invalidate CV/chunk/run/graph requests before applying the new server response. If the selected profile is pending, abort in-flight ready-profile requests, clear all cached CV/chunk/run/graph detail before render, show the safe setup state, and make zero profile-owned observability, graph, currentness, or evaluation requests; global Saved Job rows may remain visible, but no scorer runs. Re-extract/delete actions use profile IDs and the selected profile attachment only after the backend ownership check. Keep global Saved Job list/detail data in one useSavedJobsState owner, but include active ready profile ID in currentness lookup and call invalidateCurrentness after profile/revision changes.

- [ ] Step 4: Run profile-switch regressions and commit

~~~powershell
npm test -- --run src/test/observability-api.test.ts src/test/observability-state.test.tsx src/test/observability-sidebar.test.tsx src/test/cv-manager.test.tsx src/test/saved-jobs-state.test.tsx src/test/saved-jobs-panel.test.tsx
npm run lint
npm run typecheck
Set-Location ..
git add frontend/src/features/observability/api.ts frontend/src/features/observability/state.ts frontend/src/features/observability/types.ts frontend/src/features/observability/ObservabilitySidebar.tsx frontend/src/features/observability/CvManagerPanel.tsx frontend/src/features/observability/CvDeleteDialog.tsx frontend/src/features/jobs/savedJobsState.ts frontend/src/features/jobs/SavedJobsPanel.tsx frontend/src/features/jobs/SavedJobDetail.tsx frontend/src/features/profile/api.ts frontend/src/features/profile/CvSidebar.tsx frontend/src/app/App.tsx frontend/src/test/observability-api.test.ts frontend/src/test/observability-state.test.tsx frontend/src/test/observability-sidebar.test.tsx frontend/src/test/cv-manager.test.tsx frontend/src/test/saved-jobs-state.test.tsx frontend/src/test/saved-jobs-panel.test.tsx
git commit -m "fix(frontend): invalidate profile-scoped caches"
~~~

---

### Task 14: Document destructive rollout, run integrated gates, and perform browser acceptance

**Files:**
- Create: docs/operations/cv-profile-multi-conversation-rollout.md
- Create: docs/acceptance/cv-profile-multi-conversation-checklist.md
- Modify: README.md
- Modify: backend/tests/e2e/test_demo_flow.py, backend/tests/integration/test_compose_runtime.py, backend/tests/integration/test_health.py, frontend/src/test/setup.ts

- [ ] Step 1: Add explicit reset runbook and acceptance matrix

Document that legacy SQLite rows, retained files, Saved Jobs, evaluations, checkpoints, and Neo4j data are intentionally discarded. Use a disposable Compose project name and these exact commands:

~~~powershell
$project = 'jobagent-cv-profile-reset-smoke'
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project down -v --remove-orphans
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project exec -T backend python -m app.graph.rebuild
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project down -v --remove-orphans
~~~

The checklist must record migration head 0005_cv_profiles_multi_conversation, zero profile/conversation/job rows before smoke data, no retained files from the prior volume, only static graph seed data, and a safe warning before every destructive command. Add a browser matrix for a new upload creating one pending profile and one bootstrap conversation before exactly one extraction turn, approval promoting the same profile/conversation IDs, failed exact-hash retry preserving those IDs without duplicate rows, Request Changes correction in the same conversation, pending discard restoring the ready fallback, upload blocking for a different file while setup is pending, upload/approval of two CVs, profile switch with zero provider calls, location/skill tags, new chat/select/reload, cancel/confirm conversation deletion, profile deletion fallback, and no pending candidate/evaluation/graph leakage.

- [ ] Step 2: Update e2e fixtures and controllable browser-test shims

Replace test_demo_flow.py singleton setup with two profile fixtures and selected conversation IDs. In frontend/src/test/setup.ts, add a controllable matchMedia helper and stub window.scrollTo so Astryx dialog focus/cleanup tests can assert behavior without existing jsdom warnings.

- [ ] Step 3: Run backend full gates

~~~powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q
~~~

Expected: all backend unit, integration, and e2e tests pass; no test references singleton table names or conversation='main' except the workspace-state seed contract.

- [ ] Step 4: Run frontend full gates

~~~powershell
Set-Location ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
~~~

Expected: all Vitest tests pass, strict TypeScript/lint/build pass, and the only chat stream/reducer owner remains ChatPage.

- [ ] Step 5: Run fresh Compose and migration verification

~~~powershell
Set-Location ..
docker compose --env-file .env -f infrastructure/docker-compose.yml config --services
docker compose --env-file .env -f infrastructure/docker-compose.yml config
~~~

Expected services are exactly neo4j, backend, and frontend; backend startup runs Alembic through 0005 before Uvicorn, and no startup code calls provider extraction or metadata create_all.

- [ ] Step 6: Execute the in-app browser smoke test and record evidence

Use the browser skill against the running Compose project. Upload CV A and record the returned pending profile and bootstrap conversation IDs; verify the automatic extraction turn uses those IDs, approve it, and confirm the same IDs are now ready/approved. Exercise Request Changes and correction on that bootstrap conversation, retry the same failed hash without duplicates, and verify a different-file upload is blocked while setup is pending. Upload CV B, approve it, discard a pending setup once, and verify the ready fallback is restored. Switch A -> B -> A while observing network/provider diagnostics remain idle; create two chats for a ready profile, send distinct messages, switch/reload, delete one with cancel then confirm, delete the last and verify replacement; delete profile B and verify profile A/global Saved Jobs remain. Check keyboard focus, Escape, focus restoration, mobile drawer, disabled controls during a streaming/approval state, and absence of pending candidate/evaluation/graph leakage or cross-profile history/evaluation. Record routes/statuses and screenshots in docs/acceptance/cv-profile-multi-conversation-checklist.md without storing CV text, secrets, or provider payloads.

- [ ] Step 7: Review scope and commit release documentation

~~~powershell
Set-Location ..
rg -n "candidate_profile|job_preferences|conversation\s*=\s*['\"]main['\"]|CONVERSATION_ID|AGENT_CONVERSATION_ID" backend/app frontend/src backend/tests frontend/src/test
git diff --check
git status --short
git add README.md docs/operations/cv-profile-multi-conversation-rollout.md docs/acceptance/cv-profile-multi-conversation-checklist.md backend/tests/e2e/test_demo_flow.py backend/tests/integration/test_compose_runtime.py backend/tests/integration/test_health.py frontend/src/test/setup.ts
git commit -m "docs: document multi-profile rollout and acceptance"
~~~

Expected: the search returns only intentional workspace seed/compatibility comments and no runtime singleton ownership; only planned paths are staged.

---

## Final self-review checklist

- [ ] Every approved spec section maps to a task: data model (1–2), pending bootstrap (5), persisted extraction/approval (6), APIs/activity gate (3–5), deletion (7), evaluations (8), graph (9), Astryx UI (10–13), rollout/tests (14).
- [ ] No task introduces a second chat reducer/SSE store, a client-owned profile extraction, automatic evaluation, LLM conversation titles, soft delete, or legacy-data backfill.
- [ ] A new upload has one durable pending profile/bootstrap conversation, and approval promotes that same profile and conversation identity; no nullable onboarding owner, parallel onboarding store, fake ready profile, or default profile JSON exists.
- [ ] Pending rows expose only server-derived setup status and safe empty metadata; pending data never enters candidate context, matching/evaluation, observability, or graph projection.
- [ ] profile_id, conversation_id, attachment_id, source_hash, and extraction_version names remain identical across ORM, repository, service, API, and TypeScript contracts.
- [ ] Every destructive action has both a backend activity/ownership check and a named Astryx confirmation dialog; cancellation has zero network mutation.
- [ ] Selection paths are proven with fake extractor/LLM/embedder/scorer call counters at backend and browser smoke levels.
- [ ] git diff --check, Ruff, Mypy, Vitest, ESLint, TypeScript, production build, fresh Alembic/Compose, and browser smoke are all run before claiming completion.
