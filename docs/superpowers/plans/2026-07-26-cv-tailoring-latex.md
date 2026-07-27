# CV Tailoring and Fixed LaTeX Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add source-grounded, versioned CV tailoring from a selected saved JD or a natural-language request, with structured editing and deterministic `latex-cv-v1` `.tex`/PDF artifacts, while leaving approved CV/Profile/JD records unchanged.

**Architecture:** A single `TailoringCoordinator` resolves one ready profile, its approved `CVDocument`, an optional processed saved JD, and a bounded instruction. Plan 17 adds one bounded CV Tailoring Agent beside the Main Agent; its fixed section-selection/rewrite/grounding graph never receives the reference template, contact facts, raw PDF/JD, or unrelated section bodies. This phase adds no other Agent, while the project-level controlled multi-agent policy permits future coordinator-owned Agents through separately approved plans. SQLite owns immutable tailoring sessions/versions and dual-owner Agent runs, a UUID-scoped artifact store owns `.tex`/PDF files, and backend-only renderer/compiler adapters own LaTeX and `pdflatex`. React lifts the sole saved-JD controller to `App`, keeps chat and tailored-CV workspace state separate, and renders the editor exclusively with Astryx.

**Tech Stack:** Python 3.11+/3.13 container, FastAPI, Pydantic v2, SQLAlchemy/aiosqlite, Alembic, LangGraph, `pypdf`, TeX Live/`pdflatex`, Pytest, Ruff, Mypy, React 19, TypeScript 5.9, Vite, Vitest, Astryx 0.1.4, Docker Compose.

---

## Authority, prerequisite, and scope

- The approved authority is `docs/superpowers/specs/2026-07-26-cv-tailoring-latex-design.md`. The supplied reference CV contributes presentation rules only. Its people, contacts, schools, skills, projects, links, metrics, and profession-specific values must not appear in production prompts, defaults, fixtures, logs, documentation examples, or generated artifacts.
- This plan does not itself authorize changes to `docs/plans/Master_plan.md`, `docs/plans/Plan_16.md`, or a new `docs/plans/Plan_17.md`. Implementation begins only after the repository planning gate explicitly authorizes Master Version 2.3, converts Plan 16's terminal contract into a handoff, and approves Plan 17 as the new terminal plan.
- The feature remains one implementation plan because persistence ownership, Agent-run ownership, source currentness, file promotion, API contracts, and strict frontend parsers must land in dependency order to avoid orphaned artifacts or cross-profile data. Each task is independently testable and committed; no public tailoring entry point is enabled before its backend contract exists.
- Plan 17 implements the existing Main Agent plus one fixed CV Tailoring Agent, and changes the Main Agent registry from seven to eight tools. This phase adds no other Agent, peer handoff mesh, new worker, queue, service, or unbounded ToolNode loop. It does not impose a permanent project-wide Agent-count ceiling; future Agents require a separately approved, coordinator-owned, finite contract under `docs/superpowers/specs/2026-07-26-controlled-multi-agent-governance-design.md`.
- Approved/archived CVs, approved Candidate Profiles, saved Jobs, evaluations, matching, and Neo4j projections are read-only inputs. Tailoring creates derivative SQLite/app-data records only.
- The provider never emits LaTeX. The frontend never accepts or edits LaTeX. `latex-cv-v1` is the sole renderer owner and user/provider text is escaped before interpolation. The frontend keeps the installed Astryx neutral theme and adds no second design system.
- GitHub is optional. `full_name` is the only required header fact for tailoring; location, phone, email, and GitHub are independently nullable and omitted with their separators when absent.

## Frozen cross-layer contracts

Define these names once and reuse them unchanged across ORM, repositories, services, routes, tests, and TypeScript parsers:

```python
# backend/app/schemas/cv_tailoring.py and backend/app/db/models/cv_tailoring.py
TAILORING_TEMPLATE_VERSION = "latex-cv-v1"
TAILORING_SESSION_STATE_GENERATING = "generating"
TAILORING_SESSION_STATE_READY = "ready"
TAILORING_SESSION_STATE_FAILED = "failed"
TAILORING_SESSION_STATE_DELETING = "deleting"
TAILORING_SESSION_STATES = frozenset({
    TAILORING_SESSION_STATE_GENERATING,
    TAILORING_SESSION_STATE_READY,
    TAILORING_SESSION_STATE_FAILED,
    TAILORING_SESSION_STATE_DELETING,
})
TAILORING_CREATED_BY_AI = "ai"
TAILORING_CREATED_BY_USER = "user"
TAILORING_CREATED_BY_VALUES = frozenset({
    TAILORING_CREATED_BY_AI,
    TAILORING_CREATED_BY_USER,
})
TAILORING_CURRENT = "current"
TAILORING_STALE = "stale"
CV_TAILORING_SESSION_HEADER = "X-CV-Tailoring-Session-Id"

# backend/app/db/models/chat.py
AGENT_RUN_KIND_CHAT = "chat"
AGENT_RUN_KIND_CV_TAILORING = "cv_tailoring"
AGENT_RUN_KINDS = frozenset({AGENT_RUN_KIND_CHAT, AGENT_RUN_KIND_CV_TAILORING})
```

Stable safe error codes are defined in `backend/app/services/cv_tailoring.py` and mirrored as a closed TypeScript union:

```text
PROFILE_NOT_READY
TAILORING_CONTACT_REQUIRED
JOB_NOT_SCORABLE
TAILORING_SESSION_NOT_FOUND
TAILORING_VERSION_NOT_FOUND
TAILORING_SOURCE_STALE
TAILORING_PARENT_CONFLICT
TAILORING_GROUNDING_FAILED
TAILORING_COMPILE_FAILED
TAILORING_ARTIFACT_UNAVAILABLE
TAILORING_DELETE_FAILED
```

The missing `TailoredAttribute` contract is resolved here. Attribute names are copied from approved source keys and cannot be introduced or renamed by the Agent or editor. A scalar source attribute becomes one value; a list source attribute becomes ordered values. Each value carries independent provenance:

```python
from typing import Literal

from app.schemas.agent_activity import AgentActivityPayload
from app.schemas.common import AwareUtcDatetime, StrictModelConfig, UuidStr
from app.schemas.cv_document import CVSectionKind
from pydantic import BaseModel, Field, field_validator, model_validator


class SourceBoundText(BaseModel):
    model_config = StrictModelConfig

    text: str = Field(max_length=4_000)
    source_fact_ids: list[str] = Field(max_length=64)

    @field_validator("source_fact_ids")
    @classmethod
    def fact_ids_are_unique(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("source_fact_ids entries must be non-empty")
        if len(value) != len(set(value)):
            raise ValueError("source_fact_ids must be unique")
        return value


class TailoredAttribute(BaseModel):
    model_config = StrictModelConfig

    name: str = Field(min_length=1, max_length=120)
    values: list[SourceBoundText] = Field(min_length=1, max_length=30)


class TailoredItem(BaseModel):
    model_config = StrictModelConfig

    id: str = Field(min_length=1, max_length=200)
    source_entry_id: str | None = Field(default=None, max_length=200)
    title: SourceBoundText | None = None
    subtitle: SourceBoundText | None = None
    date_text: SourceBoundText | None = None
    location: SourceBoundText | None = None
    body: SourceBoundText
    bullets: list[SourceBoundText] = Field(max_length=30)
    attributes: list[TailoredAttribute] = Field(max_length=30)


class TailoredSection(BaseModel):
    model_config = StrictModelConfig

    id: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(ge=0)
    heading: str = Field(min_length=1, max_length=200)
    kind: CVSectionKind
    items: list[TailoredItem] = Field(max_length=30)


class TailoredHeaderSnapshot(BaseModel):
    model_config = StrictModelConfig

    full_name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=254)
    github_url: str | None = Field(default=None, max_length=500)


class TailoredCVContent(BaseModel):
    model_config = StrictModelConfig

    header: TailoredHeaderSnapshot
    sections: list[TailoredSection] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def section_order_and_identity(self) -> "TailoredCVContent":
        if [section.ordinal for section in self.sections] != list(range(len(self.sections))):
            raise ValueError("sections must have contiguous ordinals")
        ids = [section.id for section in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("section ids must be unique")
        return self
```

Fact identity and persisted evidence use one deterministic owner:

```python
# backend/app/services/cv_tailoring_projection.py
def source_fact_id(
    *, source_hash: str, section_id: str, entry_id: str, field_path: str
) -> str:
    material = "\0".join((source_hash, section_id, entry_id, field_path))
    return "sf_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


class TailoredFactEvidence(BaseModel):
    model_config = StrictModelConfig

    fact_id: str = Field(min_length=1, max_length=35)
    section_id: str = Field(min_length=1, max_length=200)
    source_entry_id: str = Field(min_length=1, max_length=200)
    field_path: str = Field(min_length=1, max_length=200)
    source_text: str = Field(max_length=4_000)


class TailoringProvenance(BaseModel):
    model_config = StrictModelConfig

    targeted_section_ids: list[str] = Field(max_length=20)
    facts: list[TailoredFactEvidence] = Field(max_length=20_000)
```

Provider-facing patch models omit immutable section metadata and server-owned item IDs. They are separate from durable content:

```python
class TailoredItemPatch(BaseModel):
    model_config = StrictModelConfig

    source_entry_id: str | None
    title: SourceBoundText | None
    subtitle: SourceBoundText | None
    date_text: SourceBoundText | None
    location: SourceBoundText | None
    body: SourceBoundText
    bullets: list[SourceBoundText]
    attributes: list[TailoredAttribute]


class TailoredSectionPatch(BaseModel):
    model_config = StrictModelConfig

    section_id: str
    items: list[TailoredItemPatch]


class TailoredPatchSet(BaseModel):
    model_config = StrictModelConfig

    sections: list[TailoredSectionPatch]
```

Public request/response shapes are fixed before routes or frontend parsers are written:

```python
class CreateTailoringSessionRequest(BaseModel):
    model_config = StrictModelConfig

    job_id: UuidStr | None = None
    instruction: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def has_source(self) -> "CreateTailoringSessionRequest":
        self.instruction = self.instruction.strip()
        if self.job_id is None and not self.instruction:
            raise ValueError("job_id or instruction is required")
        return self


class CreateTailoringAiVersionRequest(BaseModel):
    model_config = StrictModelConfig

    parent_version_id: UuidStr | None = None
    instruction: str = Field(default="", max_length=4_000)
    target_section_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def retry_or_scoped_edit(self) -> "CreateTailoringAiVersionRequest":
        if self.parent_version_id is None and self.target_section_ids:
            raise ValueError("initial retry selects sections from the outline")
        if self.parent_version_id is not None and not self.target_section_ids:
            raise ValueError("later AI version requires selected sections")
        if self.parent_version_id is not None and not self.instruction.strip():
            raise ValueError("later AI version requires an instruction")
        return self


class CreateTailoringManualVersionRequest(BaseModel):
    model_config = StrictModelConfig

    parent_version_id: UuidStr
    content: TailoredCVContent


class TailoringJobLabel(BaseModel):
    model_config = StrictModelConfig

    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=300)


class TailoringVersionSummary(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    version_number: int = Field(ge=1)
    parent_version_id: UuidStr | None
    created_by: Literal["ai", "user"]
    page_count: int = Field(ge=1)
    page_warning: str | None
    created_at: AwareUtcDatetime


class TailoringSessionSummary(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    profile_id: UuidStr
    job_label: TailoringJobLabel | None
    instruction: str
    template_version: Literal["latex-cv-v1"]
    state: Literal["generating", "ready", "failed", "deleting"]
    currentness: Literal["current", "stale"]
    latest_version_number: int = Field(ge=0)
    error_code: str | None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime


class TailoringSessionListResponse(BaseModel):
    model_config = StrictModelConfig

    items: list[TailoringSessionSummary]


class TailoringRunSummary(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    state: Literal["running", "interrupted", "completed", "failed"]
    error_code: str | None
    activities: list[AgentActivityPayload]


class TailoringSessionDetailResponse(BaseModel):
    model_config = StrictModelConfig

    session: TailoringSessionSummary
    versions: list[TailoringVersionSummary]
    selected_version: TailoringVersionSummary | None
    content: TailoredCVContent | None
    evidence: list[TailoredFactEvidence]
    latest_run: TailoringRunSummary | None
    source_available: bool
    pdf_available: bool


class TailoringVersionCreateResponse(BaseModel):
    model_config = StrictModelConfig

    session_id: UuidStr
    version_id: UuidStr
    version_number: int = Field(ge=1)
    currentness: Literal["current"] = "current"


class TailoringDeleteResponse(BaseModel):
    model_config = StrictModelConfig

    deleted_session_id: UuidStr
```

SSE session creation uses the existing seven event names. `POST /api/cv-tailoring/sessions` pre-creates the session/run, returns `X-CV-Tailoring-Session-Id`, and exposes that header through CORS. The frontend reads the header before consuming the body, then fetches session detail only after a validated `run_completed`. It never treats disconnect as success and never adds a session field to `run_started`.

## File map and ownership

| Area | Files to create or modify | Single responsibility |
| --- | --- | --- |
| Contact facts | new `schemas/contact.py`; `schemas/profile.py`, `services/cv_contact_contracts.py`, `services/cv_document_extraction.py`, `services/cv_document_projection.py`, `services/profile_extraction.py`, `services/profile_drafts.py` | One contact syntax/normalization owner, strict extraction evidence, deterministic ambiguity handling, approved correction |
| Tailored contracts | new `schemas/cv_tailoring.py`, `services/cv_tailoring_projection.py`, `services/cv_tailoring_guard.py` | Durable content, fact bank, baseline projection, immutable section identity, grounding |
| Persistence | new `db/models/cv_tailoring.py`, `repositories/cv_tailoring.py`, migration `0007_add_cv_tailoring.py`; modify chat models/repos/gates | Sessions, immutable versions, dual-owner runs, CAS/currentness metadata |
| Artifacts | new `storage/cv_tailoring.py`, `services/cv_tailoring_renderer.py`, `services/cv_tailoring_compiler.py` | UUID-safe paths, deterministic LaTeX, bounded `pdflatex`, hashes/page counts |
| Tailoring Agent | new `agent/tailoring_graph.py`, `services/cv_tailoring.py` | Fixed selection/load/rewrite/guard/one-repair graph and coordinator |
| Backend surface | new `tools/cv_tailoring.py`, `api/cv_tailoring.py`, `services/cv_tailoring_deletion.py`; modify registry/chat/API/dependencies/main/deletion | Eighth tool, selected JD propagation, seven endpoints, safe downloads/deletion |
| Frontend contracts | new `features/cv-tailoring/types.ts`, `api.ts`, `state.ts`; modify chat/job/App/sidebar owners | Strict DTO/SSE parsing, one saved-JD controller, session/editor state |
| Frontend UI | new tailoring Astryx components and token CSS; modify saved-JD/chat/navigation components | Two entry points, list/editor/preview/version/evidence/delete experience |
| Runtime/docs | Dockerfile, Compose settings, README, operations/acceptance docs and test suites | TeX dependency, exact three-service rollout, synthetic evidence |

---

### Task 1: Extract and approve optional contact facts

**Files:**
- Create: `backend/app/schemas/contact.py`
- Modify: `backend/app/schemas/profile.py`
- Create: `backend/app/services/cv_contact_contracts.py`
- Modify: `backend/app/services/cv_document_extraction.py`
- Modify: `backend/app/services/cv_document_projection.py`
- Modify: `backend/app/services/profile_extraction.py`
- Modify: `backend/app/services/profile_drafts.py`
- Test: `backend/tests/unit/test_profile_schemas.py`
- Create: `backend/tests/unit/test_contact_schemas.py`
- Create: `backend/tests/unit/test_cv_contact_contracts.py`
- Modify: `backend/tests/unit/test_cv_document_extraction.py`
- Modify: `backend/tests/unit/test_profile_extraction.py`
- Modify: `backend/tests/integration/test_profile_approval.py`
- Modify: `backend/tests/integration/test_profile_reextraction.py`

- [x] **Step 1: Write failing backward-compatibility and contact-grounding tests**

Add strict schema tests proving old payloads parse with all three new fields set to `None`, valid fields round-trip, invalid/blank contact values fail, and unknown fields still fail. Add this source-order/ambiguity matrix to `test_cv_contact_contracts.py`:

```python
def test_projects_source_ordered_contacts_and_omits_ambiguous_kind() -> None:
    chunks = (
        CanonicalChunk(ordinal=0, text="Ada Example | ada@example.test | +84 900 000 001"),
        CanonicalChunk(ordinal=1, text="https://github.com/ada-example"),
        CanonicalChunk(ordinal=2, text="alternate@example.test"),
    )
    facts = (
        ExtractedContactFact(kind="phone", value="+84 900 000 001", evidence="+84 900 000 001", source_chunk_ordinal=0),
        ExtractedContactFact(kind="email", value="ada@example.test", evidence="ada@example.test", source_chunk_ordinal=0),
        ExtractedContactFact(kind="github_url", value="https://github.com/ada-example", evidence="https://github.com/ada-example", source_chunk_ordinal=1),
        ExtractedContactFact(kind="email", value="alternate@example.test", evidence="alternate@example.test", source_chunk_ordinal=2),
    )

    result = validate_and_project_contact_facts(facts, chunks=chunks)

    assert result.phone == "+84 900 000 001"
    assert result.email is None
    assert result.github_url == "https://github.com/ada-example"
    assert result.warnings == ("ambiguous_contact:email",)
```

Also cover evidence absent from the referenced chunk, invalid ordinal, malformed email, phone outside 7–15 normalized digits, GitHub repository paths, non-GitHub hosts, username-like inference, duplicate equivalent values, and no-contact CVs.

- [x] **Step 2: Run the focused tests to verify RED**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_contact_schemas.py tests/unit/test_profile_schemas.py tests/unit/test_cv_contact_contracts.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py -q
```

Expected: collection fails for `cv_contact_contracts`, and schema/extraction assertions fail because contact fields and provider rows do not exist.

- [x] **Step 3: Extend `CandidateProfile` without breaking stored JSON**

Insert nullable fields after `location`; defaults are required so every already-approved profile remains valid without a migration or provider backfill:

```python
class CandidateProfile(BaseModel):
    model_config = StrictModelConfig

    full_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=254)
    github_url: str | None = Field(default=None, max_length=500)
    summary: str
    current_title: str | None
    total_experience_years: float | None
    skills: list[CandidateSkill]
    experiences: list[ExperienceItem]
    education: list[EducationItem]
    languages: list[LanguageItem]
    extraction_confidence: float = Field(ge=0.0, le=1.0)
```

Create `schemas/contact.py` as the sole syntax/normalization owner with `normalize_phone(value)`, `normalize_email(value)`, and `normalize_github_profile_url(value)`, each returning a normalized string or raising `ValueError`. CandidateProfile field validators call these helpers after trimming and reject blank-as-present; `cv_contact_contracts` calls the same helpers before evidence comparison. Phone requires 7–15 normalized digits, email uses bounded local/domain syntax, and GitHub requires the absolute single-profile URL contract. Explicit corrections may change these values only through draft approval. Do not add duplicate SQL columns to `profiles`; `profile_json` remains the only detailed profile-fact owner. Keep `ProfileListItem` unchanged so list endpoints do not expose contacts.

- [x] **Step 4: Implement the pure contact contract**

Create `cv_contact_contracts.py` with these public shapes and one pure projection function:

```python
ContactKind = Literal["phone", "email", "github_url"]


class ExtractedContactFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ContactKind
    value: str
    evidence: str
    source_chunk_ordinal: int


@dataclass(frozen=True, slots=True)
class AcceptedContacts:
    phone: str | None
    email: str | None
    github_url: str | None
    warnings: Sequence[str]


def validate_and_project_contact_facts(
    facts: Sequence[ExtractedContactFact],
    *,
    chunks: Sequence[CanonicalChunk],
) -> AcceptedContacts:
    by_ordinal = {chunk.ordinal: chunk.text for chunk in chunks}
    accepted: dict[str, dict[str, str]] = {
        "phone": {}, "email": {}, "github_url": {},
    }
    for fact in facts:
        source = by_ordinal.get(fact.source_chunk_ordinal)
        if source is None:
            continue
        if normalize_assertion_text(fact.evidence) not in normalize_assertion_text(source):
            continue
        normalized = normalize_contact_value(fact.kind, fact.value, fact.evidence)
        if normalized is not None:
            accepted[fact.kind].setdefault(normalized, fact.value.strip())

    projected: dict[str, str | None] = {}
    warnings: list[str] = []
    for kind in ("phone", "email", "github_url"):
        values = accepted[kind]
        projected[kind] = next(iter(values.values())) if len(values) == 1 else None
        if len(values) > 1:
            warnings.append(f"ambiguous_contact:{kind}")
    return AcceptedContacts(**projected, warnings=warnings)
```

The implementation must reuse `normalize_assertion_text()` for NFKC/casefold/whitespace evidence containment; validate the exact ordinal; compare email after casefold, phone after retaining an optional leading `+` and 7–15 digits, and GitHub after `urllib.parse.urlsplit`. A GitHub value is accepted only for `http|https`, host `github.com|www.github.com`, exactly one path segment matching a bounded ASCII GitHub-profile username (`A–Z`, `a–z`, digits, internal hyphens), and no query/fragment. Deduplicate normalized equivalents; if more than one distinct accepted value remains for a kind, return `None` for that kind and append exactly `ambiguous_contact:<kind>`. Never infer a contact from a filename, profession, username, repository mention, or another field.

Define the private `normalize_contact_value(kind, value, evidence) -> str | None` in the same module. It delegates syntax/canonicalization to `schemas.contact`, then returns the comparison key only when that normalized value is represented by normalized evidence; otherwise it returns null. No other module reimplements contact normalization.

- [x] **Step 5: Carry contact rows through bounded CV extraction**

Add `contacts: list[ExtractedContactFact]` to `ExtractedBatchDocument`. Add `contact_facts: Sequence[ExtractedContactFact]` to `CVDocumentExtractionOutcome`. Update `_BATCH_SYSTEM` so each row must cite evidence and a batch-local ordinal. Clamp/drop rows with an ordinal outside the current batch, accumulate them in batch/source order, and return them in the outcome. Consolidation continues to receive section fragments only; it must not become a second contact selector.

Update `project_candidate_profile()` to accept `phone`, `email`, and `github_url` keyword arguments and put them into the validated payload. In both document-publication paths, call `validate_and_project_contact_facts(outcome.contact_facts, chunks=chunks)` before projection, append its ambiguity warnings to document extraction warnings, and pass only accepted values into the profile. Existing profiles acquire contacts only after explicit re-extraction and approval.

- [x] **Step 6: Permit explicit contact corrections through the existing approval owner**

Extend `_PROFILE_PATCH_KEYS` in `profile_drafts.py` to the exact set below; no direct active-profile write is added:

```python
_PROFILE_PATCH_KEYS = frozenset({
    "full_name",
    "location",
    "phone",
    "email",
    "github_url",
    "summary",
    "current_title",
    "total_experience_years",
    "experiences",
    "education",
    "languages",
    "extraction_confidence",
})
```

Pydantic validates corrections, `propose_profile_update` writes only `profile_drafts`, and `commit_approved_draft` remains the atomic approval boundary. Add integration tests proving Save Profile promotes corrected contacts, Request Changes does not, and re-extraction does not change approved contacts until approval.

- [x] **Step 7: Run contact/approval regressions and commit**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_contact_schemas.py tests/unit/test_profile_schemas.py tests/unit/test_cv_contact_contracts.py tests/unit/test_cv_document_extraction.py tests/unit/test_profile_extraction.py tests/integration/test_profile_approval.py tests/integration/test_profile_reextraction.py -q
Set-Location ..
git add backend/app/schemas/contact.py backend/app/schemas/profile.py backend/app/services/cv_contact_contracts.py backend/app/services/cv_document_extraction.py backend/app/services/cv_document_projection.py backend/app/services/profile_extraction.py backend/app/services/profile_drafts.py backend/tests/unit/test_contact_schemas.py backend/tests/unit/test_profile_schemas.py backend/tests/unit/test_cv_contact_contracts.py backend/tests/unit/test_cv_document_extraction.py backend/tests/unit/test_profile_extraction.py backend/tests/integration/test_profile_approval.py backend/tests/integration/test_profile_reextraction.py
git commit -m "feat(profile): extract approved CV contacts"
```

Expected: focused tests pass; no profile list response contains phone, email, or GitHub.

---

### Task 2: Define tailored content, baseline projection, and grounding

**Files:**
- Create: `backend/app/schemas/cv_tailoring.py`
- Create: `backend/app/services/cv_tailoring_projection.py`
- Create: `backend/app/services/cv_tailoring_guard.py`
- Create: `backend/tests/unit/test_cv_tailoring_schemas.py`
- Create: `backend/tests/unit/test_cv_tailoring_projection.py`
- Create: `backend/tests/unit/test_cv_tailoring_guard.py`

- [x] **Step 1: Write failing schema, projection, and fact-stability tests**

Use a synthetic `CVDocument` containing summary, experience, skills, awards, and an unknown `other` heading. Assert the projector keeps every section ID/heading/kind/ordinal and every source text value, maps scalar/list attributes into `TailoredAttribute.values`, copies approved header facts, and assigns stable fact IDs on repeated calls.

```python
def test_source_fact_ids_are_stable_and_revision_bound() -> None:
    first = source_fact_id(
        source_hash="revision-a",
        section_id="cv-document-v1:s0:summary",
        entry_id="cv-document-v1:s0:e0:summary",
        field_path="body",
    )
    assert first == source_fact_id(
        source_hash="revision-a",
        section_id="cv-document-v1:s0:summary",
        entry_id="cv-document-v1:s0:e0:summary",
        field_path="body",
    )
    assert first != source_fact_id(
        source_hash="revision-b",
        section_id="cv-document-v1:s0:summary",
        entry_id="cv-document-v1:s0:e0:summary",
        field_path="body",
    )
```

Add strict-model tests for duplicate section IDs, non-contiguous ordinals, duplicate/empty fact IDs, unbounded text/items, unknown fields, missing full name, and malformed GitHub header values.

- [x] **Step 2: Run the new tests to verify RED**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_schemas.py tests/unit/test_cv_tailoring_projection.py tests/unit/test_cv_tailoring_guard.py -q
```

Expected: collection fails because the new schema/projection/guard modules do not exist.

- [x] **Step 3: Implement the frozen durable/provider schemas**

Create `cv_tailoring.py` with the exact frozen models above plus `TailoringSourceRevision`, `TailoredFactEvidence`, `TailoringProvenance`, provider patch models, public DTOs, and parse helpers. `TailoringRunSummary.activities` reuses the existing safe `AgentActivityPayload`; it never exposes checkpoints or provider state:

```python
class TailoringSourceRevision(BaseModel):
    model_config = StrictModelConfig

    profile_updated_at: AwareUtcDatetime
    source_hash: str = Field(min_length=1, max_length=128)
    job_updated_at: AwareUtcDatetime | None
    template_version: Literal["latex-cv-v1"]


def parse_tailored_content(payload: Any) -> TailoredCVContent:
    return TailoredCVContent.model_validate(payload)


def parse_tailoring_provenance(payload: Any) -> TailoringProvenance:
    return TailoringProvenance.model_validate(payload)
```

`TailoredHeaderSnapshot` validates `github_url` with the same accepted profile-URL rule as Task 1. Source facts and public evidence never include chunk text, source ordinals, raw JD, provider payloads, filesystem paths, or contacts.

- [x] **Step 4: Build the deterministic baseline and fact bank**

Implement these public contracts in `cv_tailoring_projection.py`:

```text
TailoringBaseline(content: TailoredCVContent,
                  fact_bank: dict[str, TailoredFactEvidence],
                  approved_skill_labels: Sequence[str])
project_tailoring_baseline(document, *, profile, source_hash) -> TailoringBaseline
select_section_context(baseline, *, section_ids) -> (selected sections, selected fact bank)
```

Use field paths `title`, `subtitle`, `date_text`, `location`, `body`, `bullets[i]`, and `attributes.<escaped-key>[i]`. Empty structural text gets no fact ID; every non-empty copied value gets exactly its own fact. Preserve source attribute insertion order and section/entry order. `select_section_context` rejects unknown/duplicate IDs and returns only requested section bodies/facts, proving unrelated sections cannot enter the Agent request.

- [x] **Step 5: Implement deterministic and semantic grounding gates**

Create a guard whose pure validation runs before the optional semantic checker:

```python
class GroundingIssue(BaseModel):
    model_config = StrictModelConfig

    code: Literal[
        "UNKNOWN_FACT",
        "CROSS_SECTION_FACT",
        "UNSUPPORTED_ANCHOR",
        "EMPTY_PROVENANCE",
        "SECTION_IDENTITY_CHANGED",
        "ATTRIBUTE_IDENTITY_CHANGED",
        "CONTENT_BOUNDS_EXCEEDED",
    ]
    path: str


class SemanticSupportChecker(Protocol):
    def supports(self, *, output_text: str, cited_evidence: Sequence[str]) -> bool:
        pass


def guard_tailored_patch(
    patch: TailoredPatchSet,
    *,
    parent: TailoredCVContent,
    allowed_section_ids: Sequence[str],
    fact_bank: Mapping[str, TailoredFactEvidence],
    approved_skill_labels: Sequence[str],
    semantic_checker: SemanticSupportChecker | None,
) -> tuple[TailoredCVContent | None, Sequence[GroundingIssue]]:
    issues = validate_patch_structure_and_facts(
        patch,
        parent=parent,
        allowed_section_ids=allowed_section_ids,
        fact_bank=fact_bank,
        approved_skill_labels=approved_skill_labels,
        semantic_checker=semantic_checker,
    )
    if issues:
        return None, issues
    return assemble_guarded_content(patch, parent=parent), ()
```

Require exact targeted section coverage with immutable IDs/headings/kinds/ordinals; preserve every untargeted section by `model_copy(deep=True)` from the parent. Reject cross-section facts, unknown/duplicate fact IDs, empty provenance on non-empty output, changed attribute names/order, unknown source-entry IDs, and bounds violations. Deterministically require every number/date token, URL/email, and canonical approved skill occurring in output to occur in the cited evidence. Call the semantic checker only for changed non-empty text that is not a normalized substring of its evidence; it receives one output field plus cited evidence only. Server assigns/reuses item IDs after acceptance; the provider does not own them.

Keep both private helpers in this module: `validate_patch_structure_and_facts(patch, parent, allowed_section_ids, fact_bank, approved_skill_labels, semantic_checker) -> list[GroundingIssue]` owns every rejection above in deterministic path order, and `assemble_guarded_content(patch, *, parent) -> TailoredCVContent` copies untargeted sections, replaces accepted targeted items, reuses source item IDs where possible, and assigns `new_uuid()` only to accepted composite items. `project_tailoring_baseline` derives `approved_skill_labels` from non-excluded CandidateProfile skills; it never uses JD-required skills as candidate truth.

- [x] **Step 6: Prove AI and manual content cannot add unsupported facts**

Test reordering/omission/truthful paraphrase success; invented employer, metric, date, link, institution, skill, cross-section fact, attribute key, section, and heading failures. Run the same guard against a manually edited full content document by converting changed targeted sections into a patch; no editor bypass exists. Add a synthetic forbidden marker such as `REFERENCE_ONLY_SENTINEL_7429` to a fake format-reference input that is never passed to projection/guard, then assert it appears in no prompt serialization, output, evidence, or rendered input. Do not use any value from the user's reference CV in the test.

- [x] **Step 7: Run focused tests and commit**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_schemas.py tests/unit/test_cv_tailoring_projection.py tests/unit/test_cv_tailoring_guard.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
Set-Location ..
git add backend/app/schemas/cv_tailoring.py backend/app/services/cv_tailoring_projection.py backend/app/services/cv_tailoring_guard.py backend/tests/unit/test_cv_tailoring_schemas.py backend/tests/unit/test_cv_tailoring_projection.py backend/tests/unit/test_cv_tailoring_guard.py
git commit -m "feat(cv-tailoring): add grounded content contracts"
```

Expected: focused tests and Ruff pass; neither new service imports ORM, FastAPI, filesystem, renderer, or Neo4j code.

---

### Task 3: Add tailoring persistence and dual-owner Agent runs

**Files:**
- Create: `backend/app/db/models/cv_tailoring.py`
- Modify: `backend/app/db/models/chat.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/db/seed.py`
- Create: `backend/app/repositories/cv_tailoring.py`
- Modify: `backend/app/repositories/agent_runs.py`
- Modify: `backend/app/services/activity_gate.py`
- Create: `backend/migrations/versions/0007_add_cv_tailoring.py`
- Modify: `backend/tests/support/db_migration.py`
- Modify: `backend/tests/support/schema_parity.py`
- Create: `backend/tests/unit/test_cv_tailoring_models.py`
- Modify: `backend/tests/unit/test_chat_models.py`
- Create: `backend/tests/integration/test_cv_tailoring_repository.py`
- Modify: `backend/tests/integration/test_database_contract.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Modify: `backend/tests/unit/test_activity_gate.py`

- [x] **Step 1: Write failing model/repository tests**

Assert exact table columns, names, JSON/date types, FK actions, checks, indexes, and uniqueness. The required SQL shapes are:

```text
cv_tailoring_sessions:
  id, profile_id, source_attachment_id, source_hash, profile_updated_at,
  job_id, job_updated_at, job_label_json, instruction, template_version,
  state, latest_version_number, error_code, created_at, updated_at

cv_tailoring_versions:
  id, session_id, version_number, parent_version_id, created_by,
  content_json, provenance_json, source_revision_json,
  tex_relative_path, pdf_relative_path, tex_sha256, pdf_sha256,
  page_count, page_warning, created_at

agent_runs additions/changes:
  run_kind non-null default chat
  user_message_id nullable but still unique
  tailoring_session_id nullable
  parent_run_id nullable
```

Repository tests must prove: initial session has version number zero; first version CAS changes it to one; each later version requires the exact same-session parent/latest number; stale parents fail without a row; version rows are immutable; Job deletion sets `job_id` null while label/revision/version artifacts remain; profile deletion cascades session/version metadata.

- [x] **Step 2: Run persistence tests to verify RED**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_models.py tests/unit/test_chat_models.py tests/integration/test_cv_tailoring_repository.py tests/integration/test_database_contract.py tests/integration/test_migrations.py tests/unit/test_activity_gate.py -q
```

Expected: new modules/tables are missing and existing Agent-run expectations still require a non-null user message.

- [x] **Step 3: Add strict ORM models and constants**

Create `cv_tailoring.py` with `CVTailoringSession` and `CVTailoringVersion`. Use Text UUID primary keys with `new_uuid`, timezone-aware timestamps with `utc_now`, JSON columns for validated payloads, and these invariants:

```python
class CVTailoringSession(Base):
    __tablename__ = "cv_tailoring_sessions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('generating', 'ready', 'failed', 'deleting')",
            name="state",
        ),
        CheckConstraint(
            "latest_version_number >= 0",
            name="latest_version_non_negative",
        ),
        CheckConstraint(
            "state = 'failed' AND error_code IS NOT NULL "
            "OR state != 'failed' AND error_code IS NULL",
            name="error_coupling",
        ),
        Index("ix_cv_tailoring_sessions__profile_updated", "profile_id", "updated_at"),
        Index("ix_cv_tailoring_sessions__job_id", "job_id"),
        Index("ix_cv_tailoring_sessions__state", "state"),
    )


class CVTailoringVersion(Base):
    __tablename__ = "cv_tailoring_versions"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "version_number",
            name="uq_cv_tailoring_versions__session_version",
        ),
        UniqueConstraint(
            "session_id", "id",
            name="uq_cv_tailoring_versions__session_id_id",
        ),
        ForeignKeyConstraint(
            ["session_id", "parent_version_id"],
            ["cv_tailoring_versions.session_id", "cv_tailoring_versions.id"],
            name="fk_cv_tailoring_versions__session_parent",
            ondelete="CASCADE",
        ),
        CheckConstraint("version_number > 0", name="version_positive"),
        CheckConstraint("created_by IN ('ai', 'user')", name="created_by"),
        CheckConstraint("page_count > 0", name="page_count_positive"),
        CheckConstraint(
            "version_number = 1 AND parent_version_id IS NULL "
            "OR version_number > 1 AND parent_version_id IS NOT NULL",
            name="parent_coupling",
        ),
        Index("ix_cv_tailoring_versions__session_created", "session_id", "created_at"),
    )
```

`profile_id` uses `profiles.id ON DELETE CASCADE`; `source_attachment_id` uses `attachments.id ON DELETE CASCADE`; `job_id` uses `job_posts.id ON DELETE SET NULL`; version `session_id` uses `ON DELETE CASCADE`. Store relative paths only, never absolute paths.

- [x] **Step 4: Generalize `agent_runs` without breaking chat callers**

Add `run_kind`, nullable `tailoring_session_id`, and nullable `parent_run_id`; make `user_message_id` nullable. Add the tailoring-session FK with `ON DELETE CASCADE` and the parent-run self-FK with `ON DELETE SET NULL`, plus indexes for tailoring session/parent and these checks. Deleting a conversation therefore detaches historical parent linkage without deleting the session-owned tailoring run:

```sql
(run_kind = 'chat' AND user_message_id IS NOT NULL
 AND tailoring_session_id IS NULL AND parent_run_id IS NULL)
OR
(run_kind = 'cv_tailoring' AND user_message_id IS NULL
 AND tailoring_session_id IS NOT NULL)
```

```sql
run_kind IN ('chat', 'cv_tailoring')
```

Keep the unique user-message constraint; SQLite permits multiple null values. Change `create_run()` to this backward-compatible signature and validate the XOR before constructing the row:

```python
async def create_run(
    session: AsyncSession,
    *,
    user_message_id: str | None = None,
    run_kind: str = AGENT_RUN_KIND_CHAT,
    tailoring_session_id: str | None = None,
    parent_run_id: str | None = None,
    source_attachment_id: str | None = None,
) -> AgentRun:
    validate_run_owner_xor(
        run_kind=run_kind,
        user_message_id=user_message_id,
        tailoring_session_id=tailoring_session_id,
        parent_run_id=parent_run_id,
    )
    run = AgentRun(
        run_kind=run_kind,
        user_message_id=user_message_id,
        tailoring_session_id=tailoring_session_id,
        parent_run_id=parent_run_id,
        source_attachment_id=source_attachment_id,
        state=AGENT_RUN_STATE_RUNNING,
    )
    session.add(run)
    await session.flush()
    return run
```

Add `create_tailoring_run()`, `list_run_ids_for_tailoring_session()`, and `list_tailoring_run_ids_for_profile()` helpers. Keep `resolve_run_owner()` chat-only and make it explicitly return `None` for a tailoring run; tailoring services resolve their owner from the session instead.

- [x] **Step 5: Create migration 0007 with database-level ownership guards**

Use revision `0007_add_cv_tailoring`, down revision `0006_add_agent_activities`. Create sessions first, batch-alter `agent_runs`, then create versions. Add an insert-only `trg_cv_tailoring_sessions__job_or_instruction` trigger that rejects a new row when `job_id IS NULL AND trim(instruction) = ''`; do not apply this rule on update, because deleting a retained Job must be able to set a JD-only session's FK to null while preserving its label/artifacts. Add insert/update triggers that make SQLite enforce the two cross-row rules normal CHECK constraints cannot express:

```sql
CREATE TRIGGER trg_cv_tailoring_sessions__ready_profile_insert
BEFORE INSERT ON cv_tailoring_sessions
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM profiles p
    WHERE p.id = NEW.profile_id
      AND p.state = 'ready'
      AND p.attachment_id = NEW.source_attachment_id
      AND p.source_hash = NEW.source_hash
  ) THEN RAISE(ABORT, 'tailoring source profile is not ready/current') END;
END
```

Create an equivalent update trigger for changes to source ownership fields. Parent-run insert/update triggers require: the new row is `cv_tailoring`, the parent exists and is `chat`, the parent's `ChatMessage -> Conversation.profile_id` equals the tailoring session profile, and `NEW.id != NEW.parent_run_id`:

```sql
SELECT CASE WHEN NEW.parent_run_id IS NOT NULL AND NOT EXISTS (
  SELECT 1
  FROM agent_runs parent
  JOIN chat_messages message ON message.id = parent.user_message_id
  JOIN conversations conversation ON conversation.id = message.conversation_id
  JOIN cv_tailoring_sessions tailoring ON tailoring.id = NEW.tailoring_session_id
  WHERE parent.id = NEW.parent_run_id
    AND parent.run_kind = 'chat'
    AND conversation.profile_id = tailoring.profile_id
    AND parent.id != NEW.id
) THEN RAISE(ABORT, 'invalid tailoring parent run') END;
```

Migration code performs structural/data-preserving changes only. It does not scan files, call a provider, compile, backfill contacts, create Neo4j data, or alter approved CV/JD JSON. Downgrade drops triggers and version/session rows (cascading tailoring runs) before restoring chat-only non-null `user_message_id`.

- [x] **Step 6: Add flush-only repositories and atomic CAS**

Implement these repository boundaries; none opens a session, commits, compiles, writes files, or calls a provider:

```text
create_session(session, *, validated session fields) -> CVTailoringSession
get_session(session, session_id) -> CVTailoringSession | None
list_sessions_for_profile(session, profile_id) -> list[CVTailoringSession]
list_versions(session, session_id) -> list[CVTailoringVersion]
get_version(session, version_id) -> CVTailoringVersion | None
create_version_cas(session, *, session_id, expected_latest_version_number,
                   expected_parent_version_id, version: CVTailoringVersionWrite)
                   -> CVTailoringVersion
mark_session_failed(session, session_id, *, error_code) -> CVTailoringSession
mark_session_deleting(session, session_id) -> CVTailoringSession
delete_session(session, session_id) -> bool
```

Define `CVTailoringVersionWrite` as a frozen internal dataclass containing exactly: `id`, `parent_version_id`, `created_by`, validated `content_json`, validated `provenance_json`, validated `source_revision_json`, both relative paths, both SHA-256 hashes, positive page count, optional page warning, and aware `created_at`. It does not contain `session_id` or `version_number`; the CAS repository assigns both from authoritative state.

`create_version_cas` validates the parent belongs to the session and has the expected latest version, inserts version `expected + 1`, then performs `UPDATE cv_tailoring_sessions SET latest_version_number=:new, state='ready', error_code=NULL WHERE id=:id AND latest_version_number=:expected`. A row count other than one raises `TailoringParentConflict`; the caller's transaction rolls back both operations. `mark_session_deleting` also clears `error_code` in the same update so failed-session deletion satisfies the state/error coupling.

- [x] **Step 7: Extend activity gates for both run owners**

Replace the chat-only inner join with explicit chat and tailoring predicates combined by `union_all` or `exists`. `assert_workspace_idle` sees any running/interrupted run and any tailoring session in `generating` state (manual compilation has no Agent run). `assert_profile_idle` sees chat runs through conversations plus tailoring runs/generating sessions through session profile ownership. `assert_conversation_idle` sees its chat runs plus tailoring runs/generating sessions for the same profile, including direct button runs with no parent. Add `assert_tailoring_start_allowed(profile_id, parent_run_id=None)`: direct/manual starts require the profile idle; a parented start permits exactly the named running Main-Agent chat run owned by that profile and rejects any other active work. Add tests proving null `user_message_id` rows are not dropped, the one authorized child can start under its parent, and active Agent/manual work blocks profile switch, conversation mutation, CV/Job mutation, and further tailoring creation.

- [x] **Step 8: Update migration/table registries, run green, and commit**

Update model imports, seed cleanup table names, `MIGRATION_HEAD = "0007_add_cv_tailoring"`, application-table parity, and migration-head assertions in the shared test helpers.

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_models.py tests/unit/test_chat_models.py tests/integration/test_cv_tailoring_repository.py tests/integration/test_database_contract.py tests/integration/test_migrations.py tests/unit/test_activity_gate.py -q
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/db/models/cv_tailoring.py backend/app/db/models/chat.py backend/app/db/models/__init__.py backend/app/db/seed.py backend/app/repositories/cv_tailoring.py backend/app/repositories/agent_runs.py backend/app/services/activity_gate.py backend/migrations/versions/0007_add_cv_tailoring.py backend/tests/support/db_migration.py backend/tests/support/schema_parity.py backend/tests/unit/test_cv_tailoring_models.py backend/tests/unit/test_chat_models.py backend/tests/integration/test_cv_tailoring_repository.py backend/tests/integration/test_database_contract.py backend/tests/integration/test_migrations.py backend/tests/unit/test_activity_gate.py
git commit -m "feat(cv-tailoring): persist sessions versions and runs"
```

Expected: migration/model/repository/gate tests and Mypy pass; existing chat run creation and history ownership remain unchanged.

---

### Task 4: Add UUID-safe artifact storage and deterministic `latex-cv-v1` rendering

**Files:**
- Create: `backend/app/storage/cv_tailoring.py`
- Create: `backend/app/services/cv_tailoring_renderer.py`
- Create: `backend/tests/unit/test_cv_tailoring_storage.py`
- Create: `backend/tests/unit/test_cv_tailoring_renderer.py`

- [x] **Step 1: Write failing path-safety, escaping, and golden-render tests**

Storage tests must reject non-UUID components, absolute paths, `..`, separators, symlink escapes, unexpected filenames, and deletion outside `FILES_DIR/cv-tailoring`. They must prove staging/promotion is same-filesystem, version paths are unique, reads accept only `source|pdf`, and repeated delete is safe.

Renderer golden tests use synthetic cross-profession content with English and Vietnamese diacritics, `Experience`, `Awards`, one unknown section, GitHub present/absent, every optional contact combination, and every TeX metacharacter:

```python
@pytest.mark.parametrize("value, escaped", [
    ("#", r"\#"), ("$", r"\$"), ("%", r"\%"), ("&", r"\&"),
    ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
    ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ("\\", r"\textbackslash{}"),
])
def test_escape_latex_text(value: str, escaped: str) -> None:
    assert escape_latex_text(value) == escaped
```

Assert absent contacts create no blank bullet/separator; arbitrary strings containing `\\input`, `\\write18`, `%`, or environment closers are rendered only as escaped text.

- [x] **Step 2: Run renderer/storage tests to verify RED**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_storage.py tests/unit/test_cv_tailoring_renderer.py -q
```

Expected: collection fails because storage and renderer modules do not exist.

- [x] **Step 3: Implement a separate artifact-storage owner**

Do not weaken `AttachmentStorage`'s one-segment rule. Create `TailoringArtifactStorage` rooted at `Path(FILES_DIR).resolve() / "cv-tailoring"` with this public surface:

```text
TailoringArtifactPaths(tex_relative_path: str, pdf_relative_path: str)
create_staging_dir(*, version_id) -> Path
promote(*, profile_id, session_id, version_id, staged_tex, staged_pdf)
    -> TailoringArtifactPaths
open_artifact(*, relative_path) -> BinaryIO
resolve_artifact(*, relative_path) -> Path
delete_version(*, profile_id, session_id, version_id) -> bool
delete_session(*, profile_id, session_id) -> bool
```

Validate every ID with the existing UUID-v4 contract, derive filenames internally as `resume.tex` and `resume.pdf`, resolve/check every parent beneath the root before create/move/delete, use `os.replace` only within the same filesystem, reject existing final paths, and remove staging on all exits. Return POSIX relative paths under `cv-tailoring/<profile>/<session>/<version>`; never return absolute paths to routes or clients.

- [x] **Step 4: Implement text and URL escaping with one fixed template owner**

Expose only:

```text
escape_latex_text(value: str) -> str
render_latex_cv(content: TailoredCVContent) -> str
```

The renderer starts with this literal fixed shell; no provider/user string may alter it:

```latex
\documentclass[11pt]{article}
\usepackage{graphicx}
\setlength{\parindent}{0pt}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage[utf8]{inputenc}
\usepackage[T5,T1]{fontenc}
\usepackage[vietnamese,english]{babel}
\usepackage[left=1.06cm,top=1.2cm,right=1.06cm,bottom=1.0cm]{geometry}
\usepackage{titlesec}

\titleformat{\section}{\large\bfseries\uppercase}{}{0em}{}[\titlerule]
\titlespacing*{\section}{0pt}{10pt}{5pt}

\begin{document}
```

It ends with `\\end{document}` and one newline. Render the centered bold name and a conditional contact row ordered location, phone, email, GitHub. Insert `\\textbullet` only between adjacent present values. Validate GitHub again, reconstruct the URL from the whitelisted scheme/host/username components, and render it via `\\href{<validated-url>}{GitHub: <escaped-username>}`.

- [x] **Step 5: Render every source-owned section dynamically**

Iterate `content.sections` without a heading dictionary. Render escaped `\\section{heading}` in source order. The renderer owns kind-to-layout mapping:

- `summary`, `interests`, `references`: paragraph/simple-list presentation.
- `skills`, `languages`: compact labeled rows using title/body/attribute values.
- `experience`, `education`, `projects`, `certifications`, `awards`, `publications`, `volunteering`, `other`: generic entries with bold left title, optional right date or source-backed link, optional subtitle/location, body, compact bullets, and generic labeled attributes.

Use `[noitemsep, topsep=2pt, partopsep=0pt, parsep=0pt]` for item lists and `\\vspace{5pt}` only between multiple entry blocks. Never remove content for page count and never special-case a profession or sample heading.

For entry links, inspect attribute values generically rather than using profession/heading keys. The first value that is an absolute bounded HTTP(S) URL with host, no credentials/control characters, and safe normalized encoding may render as a right-aligned fixed `[Link]`; it remains source-grounded and is omitted from the later attribute rows. A dedicated `escape_latex_url` escapes TeX-significant URL characters only after URL validation; it is distinct from `escape_latex_text`. All other values render as escaped text. No unvalidated free-form value enters `\\href`.

The renderer emits no `\\includegraphics`, `\\input`, `\\include`, custom command, package, font, file reference, or user-controlled preamble fragment. `graphicx` remains loaded only because it is part of the locked visual shell.

- [x] **Step 6: Verify exact golden output and commit**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_storage.py tests/unit/test_cv_tailoring_renderer.py -q
Set-Location ..
git add backend/app/storage/cv_tailoring.py backend/app/services/cv_tailoring_renderer.py backend/tests/unit/test_cv_tailoring_storage.py backend/tests/unit/test_cv_tailoring_renderer.py
git commit -m "feat(cv-tailoring): render fixed LaTeX artifacts"
```

Expected: byte-for-byte golden `.tex`, metacharacter, bilingual, path traversal, and cleanup tests pass; renderer code contains no personal/example facts.

---

### Task 5: Compile bounded PDFs inside the existing backend service

**Files:**
- Modify: `backend/app/core/settings.py`
- Create: `backend/app/services/cv_tailoring_compiler.py`
- Create: `backend/app/services/cv_tailoring_smoke.py`
- Modify: `infrastructure/docker/backend.Dockerfile`
- Modify: `infrastructure/docker-compose.yml`
- Modify: `.env.example`
- Modify: `backend/tests/unit/test_settings.py`
- Create: `backend/tests/unit/test_cv_tailoring_compiler.py`
- Modify: `backend/tests/unit/test_dependency_manifest.py`
- Modify: `backend/tests/integration/test_compose_runtime.py`
- Create: `backend/tests/integration/test_cv_tailoring_compiler.py`

- [x] **Step 1: Write failing settings, argv, timeout, and PDF-bound tests**

Extend exact Settings field/default tests with:

```python
EXPECTED_DEFAULTS.update({
    "CV_TAILOR_MAX_INSTRUCTION_CHARS": 4_000,
    "CV_TAILOR_MAX_SECTIONS": 20,
    "CV_TAILOR_MAX_ITEMS_PER_SECTION": 30,
    "CV_TAILOR_MAX_TEX_CHARS": 100_000,
    "CV_TAILOR_COMPILE_TIMEOUT_SECONDS": 15,
    "CV_TAILOR_MAX_PDF_MB": 5,
})
```

Compiler tests inject a fake process factory and assert exactly two invocations with an argv array, no shell, `-no-shell-escape`, `-halt-on-error`, `-interaction=nonstopmode`, a server-owned output directory, and literal `resume.tex`. Cover timeout/kill, nonzero status, missing PDF, oversized TeX/PDF, invalid/zero page count, cleanup, SHA-256, and a valid over-two-page warning.

- [x] **Step 2: Run focused compiler/runtime tests to verify RED**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_settings.py tests/unit/test_cv_tailoring_compiler.py tests/unit/test_dependency_manifest.py tests/integration/test_compose_runtime.py -q
```

Expected: settings/compiler assertions fail and the backend image contains no TeX packages.

- [x] **Step 3: Add bounded Settings as the sole runtime owner**

Append these positive integer fields to `Settings`; validate each is greater than zero with Pydantic `Field(gt=0)` while keeping its annotation `int`:

```python
CV_TAILOR_MAX_INSTRUCTION_CHARS: int = 4_000
CV_TAILOR_MAX_SECTIONS: int = 20
CV_TAILOR_MAX_ITEMS_PER_SECTION: int = 30
CV_TAILOR_MAX_TEX_CHARS: int = 100_000
CV_TAILOR_COMPILE_TIMEOUT_SECONDS: int = 15
CV_TAILOR_MAX_PDF_MB: int = 5
```

Expose the same optional overrides in Compose with default expansion and document them in `.env.example`; no secret is added. Schema limits remain at or below these runtime maxima.

- [x] **Step 4: Implement an async argv-only compiler adapter**

Create these exact public contracts:

```text
TailoringCompileResult(tex_path: Path, pdf_path: Path, tex_sha256: str,
                       pdf_sha256: str, page_count: int,
                       page_warning: str | None)
TailoringCompileError.code = "TAILORING_COMPILE_FAILED"
compile_latex_cv(tex_source, *, staging_dir, settings,
                 process_factory=asyncio.create_subprocess_exec)
                 -> TailoringCompileResult
```

Define `TailoringCompilerSettings` as a protocol containing only `CV_TAILOR_MAX_TEX_CHARS`, `CV_TAILOR_COMPILE_TIMEOUT_SECONDS`, and `CV_TAILOR_MAX_PDF_MB`; the production `Settings` object satisfies it and the smoke CLI supplies the same public defaults without loading environment data. Define `ProcessFactory` as the typed callable matching `asyncio.create_subprocess_exec` and a small `ProcessLike` protocol exposing only `returncode`, `wait()`, and `kill()`. Production always uses the standard-library factory.

Validate the resolved staging directory supplied by `TailoringArtifactStorage`, UTF-8 character bound, and exact fixed filenames. Write `resume.tex`, then execute twice:

```python
argv = (
    "pdflatex",
    "-no-shell-escape",
    "-halt-on-error",
    "-interaction=nonstopmode",
    f"-output-directory={staging_dir}",
    "resume.tex",
)
```

Use `asyncio.create_subprocess_exec(*argv, cwd=staging_dir, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)` and `asyncio.wait_for(process.wait(), timeout=settings.CV_TAILOR_COMPILE_TIMEOUT_SECONDS)`. On timeout, kill and await the process. Never construct a shell string, persist/send `.log` content, or include command output/path/contact/CV text in an exception. After the second pass, require a regular non-symlink PDF within the staging directory, enforce byte size, count pages with `pypdf.PdfReader`, hash exact files, and return warning `CV is <n> pages; review length` only when `n > 2`.

The staging directory contains only renderer-owned `resume.tex` and TeX-created temporary outputs; it accepts no client filename, package, image, auxiliary input, or network resource. Remove `.aux`, `.log`, `.out`, and all other staging files after promotion/failure.

- [x] **Step 5: Install TeX Live in the existing backend image**

Before Python package installation, add one noninteractive apt layer with exactly:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        texlive-latex-base \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-lang-other \
    && rm -rf /var/lib/apt/lists/*
```

Create `cv_tailoring_smoke.py` as a no-network CLI that builds a minimal synthetic `TailoredCVContent` with English/Vietnamese text, calls the real `latex-cv-v1` renderer and `compile_latex_cv` with an in-memory object carrying the approved public default bounds, verifies a non-empty PDF/page count, and removes the directory. It must not load process Settings, root `.env`, contacts, or user/reference facts, and it must not duplicate subprocess/compiler logic. Add `RUN python -m app.services.cv_tailoring_smoke` after application installation so the image build fails unless the real fixed template compiles. Assert the image still has one backend process and Compose still lists exactly `neo4j`, `backend`, `frontend`.

- [x] **Step 6: Add real-compiler container evidence and dependency guards**

The unit suite uses a fake process. The integration test skips only when `pdflatex` is absent on a non-container developer host; inside the candidate backend image it must render a synthetic `TailoredCVContent`, call the real renderer/compiler, verify Vietnamese text compiles, inspect one positive page count, and assert no `.log`/`.aux` artifact is promoted. Update dependency-manifest tests to prove no new Python package was added for compilation.

- [x] **Step 7: Run focused gates and commit**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_settings.py tests/unit/test_cv_tailoring_compiler.py tests/unit/test_dependency_manifest.py tests/integration/test_compose_runtime.py tests/integration/test_cv_tailoring_compiler.py -q
Set-Location ..
docker compose --env-file .env -f infrastructure/docker-compose.yml config --services
git add backend/app/core/settings.py backend/app/services/cv_tailoring_compiler.py backend/app/services/cv_tailoring_smoke.py infrastructure/docker/backend.Dockerfile infrastructure/docker-compose.yml .env.example backend/tests/unit/test_settings.py backend/tests/unit/test_cv_tailoring_compiler.py backend/tests/unit/test_dependency_manifest.py backend/tests/integration/test_compose_runtime.py backend/tests/integration/test_cv_tailoring_compiler.py
git commit -m "feat(runtime): compile bounded tailored CV PDFs"
```

Expected: focused tests pass; Compose prints exactly the existing three services; a real compile is mandatory in the rebuilt backend image even if it skipped on the host.

---

### Task 6: Build the fixed CV Tailoring Agent and coordinator

**Files:**
- Create: `backend/app/agent/tailoring_graph.py`
- Create: `backend/app/services/cv_tailoring.py`
- Modify: `backend/app/repositories/cv_tailoring.py`
- Modify: `backend/app/repositories/agent_runs.py`
- Create: `backend/tests/unit/test_cv_tailoring_agent.py`
- Create: `backend/tests/unit/test_cv_tailoring_coordinator.py`
- Create: `backend/tests/integration/test_cv_tailoring_coordinator.py`

- [x] **Step 1: Write failing Agent-topology and prompt-privacy tests**

Assert the tailoring graph has exactly these fixed nodes and no `ToolNode`, dynamic tool registry, Main-Agent call, or spawn edge:

```text
select_sections
load_selected_sections
rewrite_sections
ground_patch
repair_once
```

The first provider call receives only structured JD, bounded instruction, and section outline. The rewrite/repair calls receive only selected sections and their fact bank. Put distinct synthetic sentinels in contact fields, unrelated section bodies, raw Job text, storage paths, and a fake reference format; inspect every fake-model message and assert none appears. Assert one schema-or-grounding rejection invokes exactly one repair total and a second rejection returns `TAILORING_GROUNDING_FAILED`.

- [x] **Step 2: Run Agent/coordinator tests to verify RED**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_agent.py tests/unit/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_coordinator.py -q
```

Expected: collection fails because the graph and coordinator do not exist.

- [x] **Step 3: Define the bounded Agent state and provider seam**

Use a dedicated typed state; never reuse or expand the Main Agent's messages channel:

```python
class TailoringAgentState(TypedDict):
    run_id: str
    instruction: str
    job_context: dict[str, Any] | None
    outline: list[dict[str, Any]]
    requested_section_ids: list[str]
    selected_section_ids: list[str]
    selected_sections: list[dict[str, Any]]
    fact_bank: dict[str, dict[str, Any]]
    patch: dict[str, Any] | None
    repair_count: int
    issues: list[dict[str, str]]
    error: str | None


class TailoringStructuredInvoker(Protocol):
    def select_sections(self, messages: Sequence[Any]) -> TailoringSectionSelection:
        pass

    def rewrite_sections(
        self, messages: Sequence[Any], *, is_repair: bool
    ) -> TailoredPatchSet:
        pass

    def supports(self, *, output_text: str, cited_evidence: Sequence[str]) -> bool:
        pass
```

`TailoringSectionSelection.section_ids` is strict, unique, and bounded. The production invoker uses the existing ShopAIKey chat construction, strict structured output, and existing bounded provider retry owner. It exposes no generic handoff surface or unapproved child-Agent identity.

Define it in `tailoring_graph.py` as a strict Pydantic model with `section_ids: list[str] = Field(min_length=1, max_length=20)` plus a validator for non-empty unique IDs. Define `TailoringError(Exception)` in the coordinator with non-empty `code` and safe `message`; no provider exception or compiler log becomes its message.

- [x] **Step 4: Implement the fixed graph and one shared repair budget**

`select_sections` serializes only outline/JD extraction/instruction. If an editor request supplies `requested_section_ids`, require the selection to equal that validated scope; the provider cannot widen it. `load_selected_sections` calls an injected server loader after selection and puts only those bodies/facts into state. `rewrite_sections` emits `TailoredPatchSet`. `ground_patch` calls Task 2's guard. On schema or grounding failure, store only bounded issue code/path pairs and route to `repair_once` when `repair_count == 0`; otherwise set `TAILORING_GROUNDING_FAILED`. Repair receives the same selected context, prior structured patch, and sanitized issues. Successful grounding ends the graph. Compile with the existing SQLite checkpointer under the tailoring run ID and delete that thread only after durable terminal commit.

- [x] **Step 5: Resolve authoritative sources before any Agent call**

In `cv_tailoring.py`, define:

```python
@dataclass(frozen=True, slots=True)
class TailoringSourceSnapshot:
    profile_id: str
    attachment_id: str
    source_hash: str
    profile_updated_at: datetime
    profile: CandidateProfile
    document: CVDocument
    outline: list[dict[str, Any]]
    job_id: str | None
    job_updated_at: datetime | None
    job_label: TailoringJobLabel | None
    job_context: JobPostExtraction | None


@dataclass(frozen=True, slots=True)
class TailoringLaunch:
    session_id: str
    run_id: str
    profile_id: str
```

The resolver requires a ready profile, approved `cv_documents` row matching attachment/source hash, validated CandidateProfile with non-empty `full_name`, and optional Job with `processing_status='processed'`, `jd_quality in {'full','partial'}`, validated `JobPostExtraction`, and exact `updated_at`. It loads no raw Job content or Neo4j data. At least one of a selected Job or trimmed instruction is required.

- [x] **Step 6: Implement the coordinator's single orchestration surface**

Use one dependency-injected class with these exact call surfaces:

```text
prepare_session(*, profile_id, job_id, instruction, parent_run_id)
    -> TailoringLaunch
stream_initial_version(launch) -> AsyncIterator[SseEvent]
prepare_ai_version(*, session_id, parent_version_id, instruction,
                   target_section_ids) -> TailoringLaunch
create_manual_version(*, session_id, parent_version_id, content)
    -> TailoringVersionCreateResponse
```

`prepare_session` calls `assert_tailoring_start_allowed`: a direct start requires idle profile state, while a tool start may ignore only its verified running Main-Agent parent. It then runs one short transaction to create `generating` session plus `cv_tailoring` Agent run; an optional parent is the invoking Main-Agent run. `stream_initial_version` emits existing `run_started`/safe `assistant_status`/terminal events, runs the fixed graph, renders/compiles in staging without a DB transaction, promotes a unique artifact path, then opens `BEGIN IMMEDIATE`, rechecks all source revisions, inserts version 1 with CAS, marks session ready, and completes the tailoring run. A CAS/commit failure removes only the just-promoted version directory.

- [x] **Step 7: Implement later AI/manual versions, currentness, and failure truth**

For later AI versions, the existing latest version stays downloadable while the session is temporarily `generating`; failure restores `ready` and creates no version. Initial failure leaves durable session/run `failed` with one safe code. An explicit retry calls `prepare_ai_version` with `parent_version_id=None` and empty target IDs only when `latest_version_number == 0`; the coordinator reuses the session's stored instruction/Job identity (the retry body cannot replace them), clears the safe error, re-enters automatic section selection, and still creates version 1 with null parent. Manual save does no Agent run or repair: after the same start gate it marks the session `generating` in a short transaction, validates header/section identity against the parent, builds a patch from changed sections, runs the same grounding/semantic guard once, renders/compiles/promotes, and applies the same CAS; failure restores `ready` and releases the workspace gate.

Currentness compares current ready profile `updated_at`, approved source hash, current selected Job `updated_at` when retained, and `TAILORING_TEMPLATE_VERSION`. Any mismatch returns stale, blocks AI/manual generation with `TAILORING_SOURCE_STALE`, and leaves old reads/downloads available. If the Job FK has become null, old versions remain readable but a new JD-based revision is blocked; an explicit new instruction-only or selected-Job session is required.

- [x] **Step 8: Persist safe activities and cleanup checkpoint state**

Reuse `AgentActivityService` with assistant activities only and safe labels such as `Selecting relevant sections`, `Tailoring selected sections`, `Checking source support`, and `Generating PDF`. Do not use section text, contacts, JD labels, paths, prompts, or provider data as labels. Terminal completion/failure updates the run and activity before checkpoint deletion. Generator cancellation marks initial generation failed or restores a later session to ready; disconnect never marks success.

- [x] **Step 9: Run focused suites and commit**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_tailoring_agent.py tests/unit/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_coordinator.py tests/integration/test_agent_activities.py -q
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/agent/tailoring_graph.py backend/app/services/cv_tailoring.py backend/app/repositories/cv_tailoring.py backend/app/repositories/agent_runs.py backend/tests/unit/test_cv_tailoring_agent.py backend/tests/unit/test_cv_tailoring_coordinator.py backend/tests/integration/test_cv_tailoring_coordinator.py
git commit -m "feat(cv-tailoring): orchestrate grounded Agent versions"
```

Expected: topology/privacy/repair/currentness/CAS/failure/activity tests and Mypy pass; prompts contain no unrelated section or template/reference content.

---

### Task 7: Expose direct APIs, the eighth Main-Agent tool, and retryable deletion

**Files:**
- Create: `backend/app/tools/cv_tailoring.py`
- Modify: `backend/app/tools/registry.py`
- Modify: `backend/app/agent/prompt.py`
- Modify: `backend/app/agent/state.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/app/schemas/chat.py`
- Modify: `backend/app/services/chat_turns.py`
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/conversations.py`
- Modify: `backend/app/api/sse.py`
- Modify: `backend/app/api/dependencies.py`
- Create: `backend/app/api/cv_tailoring.py`
- Create: `backend/app/services/cv_tailoring_deletion.py`
- Modify: `backend/app/services/profile_deletion.py`
- Modify: `backend/app/services/saved_jobs.py`
- Modify: `backend/app/services/cv_manager.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/unit/test_agent_context.py`
- Modify: `backend/tests/unit/test_agent_graph.py`
- Modify: `backend/tests/unit/test_shopaikey_chat.py`
- Modify: `backend/tests/unit/test_sse_contract.py`
- Modify: `backend/tests/unit/test_api_sse.py`
- Modify: `backend/tests/integration/test_chat_api.py`
- Modify: `backend/tests/integration/test_agent_runner.py`
- Create: `backend/tests/integration/test_cv_tailoring_api.py`
- Create: `backend/tests/integration/test_cv_tailoring_deletion.py`
- Modify: `backend/tests/integration/test_profile_deletion.py`
- Modify: `backend/tests/integration/test_job_deletion.py`
- Modify: `backend/tests/integration/test_job_evaluations.py`
- Modify: `backend/tests/integration/test_job_reextraction.py`
- Modify: `backend/tests/integration/test_cv_manager_deletion.py`

- [x] **Step 1: Write failing transport/tool/API/deletion tests**

Add tests proving:

- `ChatTurnRequest` accepts nullable UUID `selected_job_id`, rejects malformed/extra/raw-JD fields, and both chat routes pass it unchanged to `stream_chat_turn`.
- Main `AgentState` has exactly twelve fields after adding `selected_job_id`; it contains an ID or null, never a JD extraction/body.
- production registry order has exactly eight names and the eighth is `create_tailored_cv`; an empty/test registry still exposes only injected names.
- the tool's provider-visible schema accepts only bounded `instruction`; `job_id`, profile/CV text, template, LaTeX, paths, and contacts are absent.
- direct and tool entry points call the same coordinator and produce the same durable session/version contract.
- all seven endpoints enforce strict bodies/UUIDs/current profile, safe errors, source/PDF types, filenames/content lengths, no paths/logs/raw JD, and no compile-on-read; a failed zero-version session can explicitly retry through `ai-versions` with null parent and empty target IDs.
- session/profile deletion is retryable; Job delete uses FK `SET NULL` and preserves artifacts.

- [x] **Step 2: Run focused API/tool tests to verify RED**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_context.py tests/unit/test_agent_graph.py tests/unit/test_shopaikey_chat.py tests/unit/test_sse_contract.py tests/unit/test_api_sse.py tests/integration/test_chat_api.py tests/integration/test_agent_runner.py tests/integration/test_cv_tailoring_api.py tests/integration/test_cv_tailoring_deletion.py tests/integration/test_profile_deletion.py tests/integration/test_job_deletion.py -q
```

Expected: state/tool/route modules and header/deletion behavior are missing.

- [x] **Step 3: Propagate only a validated selected Job ID through chat**

Add `selected_job_id: UuidStr | None = None` to `ChatTurnRequest`, `selected_job_id: str | None` to `AgentState`, `build_initial_agent_state()`, `AgentGraphState`, and `initial_graph_state()`. Add the keyword to `stream_chat_turn()` and both routes. Before graph execution, resolve the conversation/profile owner and, when present, require the exact saved Job to be processed with `full|partial` quality. Inject only its ID; do not add extraction content to candidate context/system prompt or client request.

The twelve state keys are exactly:

```python
AGENT_STATE_FIELDS = frozenset({
    "conversation_id", "profile_id", "run_id", "messages_for_this_turn",
    "recent_context", "candidate_context", "active_cv_context",
    "attachment_ids", "selected_job_id", "pending_approval",
    "tool_iteration_count", "error",
})
```

- [x] **Step 4: Add the compact replay-safe Main-Agent tool**

Create the constant and tool with this exact provider-visible call surface:

```text
CREATE_TAILORED_CV_NAME = "create_tailored_cv"
build_create_tailored_cv_tool(*, coordinator: TailoringCoordinator) -> BaseTool
create_tailored_cv_tool(hidden tool_call_id, hidden state, instruction: str = "")
    -> serialized ToolResult
```

Resolve `run_id`, `profile_id`, and nullable `selected_job_id` from injected state. Validate instruction against Settings; at least it or the selected Job must exist. Call `execute_tool()` with an arguments summary containing only instruction length and `selected_job_present`. In `_invoke`, call `prepare_session(profile_id=profile_id, job_id=selected_job_id, instruction=instruction, parent_run_id=run_id)`, consume the coordinator's existing SSE iterator to a durable terminal event without forwarding child text/contact data, and return this compact success only after `run_completed`:

```python
ToolResult(
    ok=True,
    code=None,
    summary="Tailored CV is ready",
    data={
        "session_id": session_id,
        "version_id": version_id,
        "status": "ready",
        "currentness": "current",
    },
)
```

On child failure return its stable safe code and no session contents/path. A replay returns the exact prior ToolResult and does not create a second session/version.

- [x] **Step 5: Register tool eight and update Main-Agent truthfulness policy**

Append the tool after `read_active_cv` in `production_registry`, add its name to `PRODUCTION_DOMAIN_TOOL_NAMES`, and update registry/dependency docstrings from seven to eight. The prompt says to use `create_tailored_cv` only for an explicit tailoring request; use server-selected JD state when present; pass only the user's bounded instruction; do not call `read_active_cv` or another Job/CV evidence tool to prepare a tailoring request because the bounded child Agent resolves its own sources; never request/provide raw CV/JD/template/LaTeX; and never claim success before a successful exact ToolResult. There is no forced-call heuristic or extra Main-Agent retry loop for tailoring.

- [x] **Step 6: Generalize SSE response headers without changing event names**

Change the helper to this exact call surface:

```text
open_sse_response(events, *, error_mapper,
                  error_types: Sequence[type[Exception]] = (ChatTurnError,),
                  headers: Mapping[str, str] | None = None)
                  -> EventSourceResponse
```

Prime before headers exactly as today, catch only `error_types`, and construct `ClosingEventSourceResponse(produce(), headers=dict(headers or {}))`. Existing chat behavior remains default. Tailoring creation passes `(TailoringError,)` and `{CV_TAILORING_SESSION_HEADER: launch.session_id}`. Add `expose_headers=[CV_TAILORING_SESSION_HEADER]` to restricted CORS in `main.py`; no wildcard origin or event type is added.

- [x] **Step 7: Implement the seven thin tailoring routes**

Create `CVTailoringDeps` in `api/dependencies.py` with one coordinator/artifact store/settings source. Construct provider/model dependencies lazily and reuse process session factory/FILES_DIR/checkpointer path. Add `api/cv_tailoring.py`:

```text
POST   /cv-tailoring/sessions
GET    /cv-tailoring/sessions
GET    /cv-tailoring/sessions/{session_id}?version_id=<optional UUID>
POST   /cv-tailoring/sessions/{session_id}/ai-versions
POST   /cv-tailoring/sessions/{session_id}/manual-versions
GET    /cv-tailoring/versions/{version_id}/source
GET    /cv-tailoring/versions/{version_id}/pdf
DELETE /cv-tailoring/sessions/{session_id}
```

Creation and AI routes use typed SSE; manual returns `TailoringVersionCreateResponse`; list/detail/delete return their frozen DTOs. Resolve the active ready profile for list/create and require session/version profile equality for every read/mutation/download. List returns at most 100 sessions ordered by `(updated_at DESC, id DESC)`; it does not silently mix another profile. Detail defaults to latest, optionally selects a same-session version, and projects the session's most recent tailoring run plus safe durable activities so a disconnected client can recover terminal truth. Before download, require the exact regular file and verify its stored SHA-256; mismatch/missing returns `TAILORING_ARTIFACT_UNAVAILABLE` and never regenerates. Stream stored source in 64 KiB chunks as `text/x-tex; charset=utf-8`, attachment filename `resume-v<n>.tex`; stream PDF as `application/pdf`, inline filename `resume-v<n>.pdf`. Set exact `Content-Length`, `X-Content-Type-Options: nosniff`, and never compile on GET.

Map stable errors to 400/404/409/422/500 without stack/path/log/provider detail. Include the router under `/api` in `main.py`.

- [x] **Step 8: Add retryable session and profile-owned deletion**

Implement mark → external cleanup → finalize through this exact call surface:

```text
delete_tailoring_session(*, session_id, session_factory, sqlite_path, storage)
    -> TailoringDeleteResponse
```

The mark transaction verifies ownership/no active run and sets `deleting`; external cleanup deletes only that session's tailoring run checkpoints and UUID session directory; finalize deletes the session row and cascading runs/versions. Missing checkpoints/files are success on retry. Any remaining file/checkpoint/DB failure keeps `deleting` and returns `TAILORING_DELETE_FAILED`.

Extend profile deletion inputs to include all tailoring session/run IDs. After the profile is marked deleting, remove their checkpoints and each verified session directory before graph/file finalization; only then let the existing profile cascade delete metadata. The UI warning is added later. Job deletion needs no new service call: test the database `SET NULL` behavior and preserved label/artifacts.

At the start of the public saved-Job mutation coordinators (`save_and_evaluate_from_source`, `evaluate_saved_job`, `delete_saved_job`, `reextract_saved_job`) and non-profile CV Manager deletion, call the generalized workspace gate in a short session before provider/graph/file work. Map an active child run to the existing stable blocked/retry presentation; do not add a new broad lock or hold a transaction across external work. Main-Agent `save_job`/`match_jobs` tools keep their existing parent-owned paths and do not call these public wrappers, so the gate does not block authorized tools inside their own run.

- [x] **Step 9: Run backend surface regressions and commit**

```powershell
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_agent_context.py tests/unit/test_agent_graph.py tests/unit/test_shopaikey_chat.py tests/unit/test_sse_contract.py tests/unit/test_api_sse.py tests/integration/test_chat_api.py tests/integration/test_agent_runner.py tests/integration/test_cv_tailoring_api.py tests/integration/test_cv_tailoring_deletion.py tests/integration/test_profile_deletion.py tests/integration/test_job_deletion.py tests/integration/test_job_evaluations.py tests/integration/test_job_reextraction.py tests/integration/test_cv_manager_deletion.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
Set-Location ..
git add backend/app/tools/cv_tailoring.py backend/app/tools/registry.py backend/app/agent/prompt.py backend/app/agent/state.py backend/app/agent/graph.py backend/app/schemas/chat.py backend/app/services/chat_turns.py backend/app/api/chat.py backend/app/api/conversations.py backend/app/api/sse.py backend/app/api/dependencies.py backend/app/api/cv_tailoring.py backend/app/services/cv_tailoring_deletion.py backend/app/services/profile_deletion.py backend/app/services/saved_jobs.py backend/app/services/cv_manager.py backend/app/main.py backend/tests/unit/test_agent_context.py backend/tests/unit/test_agent_graph.py backend/tests/unit/test_shopaikey_chat.py backend/tests/unit/test_sse_contract.py backend/tests/unit/test_api_sse.py backend/tests/integration/test_chat_api.py backend/tests/integration/test_agent_runner.py backend/tests/integration/test_cv_tailoring_api.py backend/tests/integration/test_cv_tailoring_deletion.py backend/tests/integration/test_profile_deletion.py backend/tests/integration/test_job_deletion.py backend/tests/integration/test_job_evaluations.py backend/tests/integration/test_job_reextraction.py backend/tests/integration/test_cv_manager_deletion.py
git commit -m "feat(cv-tailoring): expose API and Main Agent entry"
```

Expected: focused suites, Ruff, and Mypy pass; production has one Main graph, one bounded tailoring graph, and exactly eight Main-Agent tools.

---

### Task 8: Add strict frontend contracts, one saved-JD owner, and workspace state

**Files:**
- Create: `frontend/src/features/cv-tailoring/types.ts`
- Create: `frontend/src/features/cv-tailoring/api.ts`
- Create: `frontend/src/features/cv-tailoring/state.ts`
- Modify: `frontend/src/features/profile/types.ts`
- Modify: `frontend/src/features/profile/ApprovalCard.tsx`
- Modify: `frontend/src/lib/api/chat.ts`
- Modify: `frontend/src/features/chat/ChatPage.tsx`
- Modify: `frontend/src/features/chat/history.ts`
- Modify: `frontend/src/features/chat/components/ChatMessages.tsx`
- Modify: `frontend/src/features/chat/components/ChatMessageRow.tsx`
- Modify: `frontend/src/features/jobs/savedJobsState.ts`
- Modify: `frontend/src/features/jobs/SavedJobDetail.tsx`
- Modify: `frontend/src/features/jobs/SavedJobsPanel.tsx`
- Modify: `frontend/src/features/observability/ObservabilitySidebar.tsx`
- Modify: `frontend/src/features/profile/CvSidebar.tsx`
- Modify: `frontend/src/app/App.tsx`
- Create: `frontend/src/test/cv-tailoring-api.test.ts`
- Create: `frontend/src/test/cv-tailoring-state.test.tsx`
- Modify: `frontend/src/test/profile-api.test.ts`
- Modify: `frontend/src/test/approval-card.test.tsx`
- Modify: `frontend/src/test/chat-page.test.tsx`
- Modify: `frontend/src/test/assistant-response.test.tsx`
- Modify: `frontend/src/test/saved-jobs-state.test.tsx`
- Modify: `frontend/src/test/saved-jobs-panel.test.tsx`
- Modify: `frontend/src/test/observability-sidebar.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: Write failing strict parser and single-owner tests**

Parsers must accept exactly the frozen keys/types, reject extras/malformed UUIDs/timestamps/enums/non-finite bounds/server paths/raw JD/source chunks/LaTeX-in-JSON, and map backend safe errors only. SSE tests require the creation header before body consumption, reject missing/malformed header, and do not select/open a session on disconnect or `run_failed`.

Add a static/composition test proving production contains exactly one `useSavedJobsState(` call, in `App.tsx`; sidebar, graph, selected-JD button, and chat receive the same controller/selection. Add send tests proving both chat endpoints serialize `selected_job_id` as UUID/null and never serialize cached JD detail.

- [x] **Step 2: Run frontend contract tests to verify RED**

```powershell
Set-Location frontend
npm test -- --run src/test/cv-tailoring-api.test.ts src/test/cv-tailoring-state.test.tsx src/test/profile-api.test.ts src/test/approval-card.test.tsx src/test/chat-page.test.tsx src/test/assistant-response.test.tsx src/test/saved-jobs-state.test.tsx src/test/saved-jobs-panel.test.tsx src/test/observability-sidebar.test.tsx src/app/App.test.tsx
```

Expected: tailoring modules/types are absent and current chat/saved-JD composition has no selected-JD transport or App-level owner.

- [x] **Step 3: Implement strict tailoring/profile parsers**

Mirror the frozen backend models with readonly TypeScript types and explicit `exact` parsers. Define:

```typescript
export type TailoringErrorCode =
  | 'PROFILE_NOT_READY'
  | 'TAILORING_CONTACT_REQUIRED'
  | 'JOB_NOT_SCORABLE'
  | 'TAILORING_SESSION_NOT_FOUND'
  | 'TAILORING_VERSION_NOT_FOUND'
  | 'TAILORING_SOURCE_STALE'
  | 'TAILORING_PARENT_CONFLICT'
  | 'TAILORING_GROUNDING_FAILED'
  | 'TAILORING_COMPILE_FAILED'
  | 'TAILORING_ARTIFACT_UNAVAILABLE'
  | 'TAILORING_DELETE_FAILED';

export type TailoredAttribute = {
  name: string;
  values: readonly SourceBoundText[];
};
```

Keep `TailoredAttribute` identical to backend (`name` + `values`). Add nullable phone/email/GitHub to detailed `CandidateProfile` parsing. The existing profile ApprovalCard shows each present extracted contact for explicit confirmation, omits absent values/separators, and keeps Save Profile/Request Changes as the only commit actions; corrections still go through the existing chat proposal/draft approval flow. Do not add contacts to profile list items, run status, activity labels, or Saved Job DTOs.

- [x] **Step 4: Implement the fetch/SSE API client**

Create JSON functions for list/detail/manual/delete and URL helpers for source/PDF. Create streaming functions using the existing `consumeSseResponse` and chat event parser:

```typescript
export async function streamCreateTailoringSession(
  body: CreateTailoringSessionRequest,
  callbacks: StreamCallbacks & {onSessionId: (sessionId: string) => void},
  signal?: AbortSignal,
): Promise<void>;

export async function streamCreateTailoringAiVersion(
  sessionId: string,
  body: CreateTailoringAiVersionRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void>;
```

For create, validate `response.headers.get('X-CV-Tailoring-Session-Id')` as UUID before invoking `onSessionId` or consuming the stream. Reuse safe HTTP-body mapping; never parse `.tex`/PDF as JSON or infer completion from body end.

- [x] **Step 5: Add a profile-scoped tailoring state owner**

`useCvTailoringState({profileId, profileReady})` owns session list/detail/version selection, direct/AI stream phases, initial-failure retry, local structured draft, conflicts, and deletion. It uses `useLatestRequest`/AbortController patterns already used by saved jobs, drops stale-profile responses, recovers a disconnected stream from `detail.latest_run`/durable activities, preserves local draft on parent/grounding/compile failure, and clears server data when profile scope changes. Server versions are immutable; selecting a version replaces local draft only after confirmation when unsaved changes exist. Keystrokes never call API/compile.

- [x] **Step 6: Lift the sole saved-JD controller to `App`**

Export a named `SavedJobsController = ReturnType<typeof useSavedJobsState>`. Instantiate it once in `App` with active profile ID/readiness. Pass the same object through `CvSidebar` to `ObservabilitySidebar`; remove the sidebar hook call while retaining its lazy list/detail/map effects. Pass only `savedJobs.state.selectedJobId` to `ChatPage` and the direct tailoring action. Do not duplicate selection in tailoring state.

- [x] **Step 7: Add selected-JD chat transport and durable editor links**

Extend `TurnRequest` with `selected_job_id?: string | null`; both serializers always send the current UUID/null. `ChatPageProps.selectedJobId` is read at send time so later selection changes do not rewrite an in-flight turn.

Add strict parsing/projection for completed `create_tailored_cv` ToolResult data (`session_id`, `version_id`, `status='ready'`, `currentness='current'`) in `history.ts`. Thread `onOpenTailoringEditor(sessionId)` through ChatMessages/ChatMessageRow and render the action only for one completed, error-free, durable validated result. Malformed/failed results show no editor link.

- [x] **Step 8: Wire direct saved-JD creation and workspace mode**

SavedJobDetail exposes `Tạo CV theo JD` only when the selected Job is processed and `jd_quality` is `full|partial`, profile is ready, and mutations are unlocked. It calls the App tailoring state with the selected ID and empty instruction. After validated `run_completed`, fetch detail and set:

```typescript
type MainWorkspace =
  | {kind: 'chat'}
  | {kind: 'cv-tailoring'; sessionId: string};
```

`Quay lại chat` restores chat without remounting ChatPage, saved-job controller, or sidebars. A Main-Agent editor link sets the same workspace state after fetching/validating that session.

- [x] **Step 9: Run frontend contract/state gates and commit**

```powershell
npm test -- --run src/test/cv-tailoring-api.test.ts src/test/cv-tailoring-state.test.tsx src/test/profile-api.test.ts src/test/approval-card.test.tsx src/test/chat-page.test.tsx src/test/assistant-response.test.tsx src/test/saved-jobs-state.test.tsx src/test/saved-jobs-panel.test.tsx src/test/observability-sidebar.test.tsx src/app/App.test.tsx
npm run lint
npm run typecheck
Set-Location ..
git add frontend/src/features/cv-tailoring/types.ts frontend/src/features/cv-tailoring/api.ts frontend/src/features/cv-tailoring/state.ts frontend/src/features/profile/types.ts frontend/src/features/profile/ApprovalCard.tsx frontend/src/lib/api/chat.ts frontend/src/features/chat/ChatPage.tsx frontend/src/features/chat/history.ts frontend/src/features/chat/components/ChatMessages.tsx frontend/src/features/chat/components/ChatMessageRow.tsx frontend/src/features/jobs/savedJobsState.ts frontend/src/features/jobs/SavedJobDetail.tsx frontend/src/features/jobs/SavedJobsPanel.tsx frontend/src/features/observability/ObservabilitySidebar.tsx frontend/src/features/profile/CvSidebar.tsx frontend/src/app/App.tsx frontend/src/test/cv-tailoring-api.test.ts frontend/src/test/cv-tailoring-state.test.tsx frontend/src/test/profile-api.test.ts frontend/src/test/approval-card.test.tsx frontend/src/test/chat-page.test.tsx frontend/src/test/assistant-response.test.tsx frontend/src/test/saved-jobs-state.test.tsx frontend/src/test/saved-jobs-panel.test.tsx frontend/src/test/observability-sidebar.test.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): add tailored CV contracts and state"
```

Expected: focused tests, ESLint, and TypeScript pass; there is one saved-JD state instance and no duplicate chat stream/reducer.

---

### Task 9: Build the Astryx sessions list, structured editor, and PDF preview

**Files:**
- Create: `frontend/src/features/cv-tailoring/TailoringSessionsPanel.tsx`
- Create: `frontend/src/features/cv-tailoring/TailoringEditor.tsx`
- Create: `frontend/src/features/cv-tailoring/TailoredSectionEditor.tsx`
- Create: `frontend/src/features/cv-tailoring/TailoringPdfPreview.tsx`
- Create: `frontend/src/features/cv-tailoring/TailoringVersionActions.tsx`
- Create: `frontend/src/features/cv-tailoring/TailoringSessionDeleteDialog.tsx`
- Create: `frontend/src/features/cv-tailoring/cv-tailoring.css`
- Modify: `frontend/src/features/observability/observabilityTabs.ts`
- Modify: `frontend/src/features/observability/types.ts`
- Modify: `frontend/src/features/observability/ObservabilityTabList.tsx`
- Modify: `frontend/src/features/observability/ObservabilitySidebar.tsx`
- Modify: `frontend/src/app/App.tsx`
- Create: `frontend/src/test/cv-tailoring-sessions-panel.test.tsx`
- Create: `frontend/src/test/cv-tailoring-editor.test.tsx`
- Create: `frontend/src/test/cv-tailoring-accessibility.test.tsx`
- Modify: `frontend/src/test/observability-navigation.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: Run mandatory Astryx discovery before UI code**

Run from `frontend/` and save the named component choices in the implementation report:

```powershell
npx astryx build "accessible CV tailoring section editor with PDF preview, sessions list, version actions, and responsive mobile tabs"
npx astryx template editor --skeleton
npx astryx docs layout
npx astryx docs tokens
npx astryx component AppShell
npx astryx component Layout
npx astryx component SideNav
npx astryx component TabList
npx astryx component List
npx astryx component ListItem
npx astryx component AspectRatio
npx astryx component ButtonGroup
npx astryx component Toolbar
npx astryx component Dialog
npx astryx component AlertDialog
npx astryx component Banner
npx astryx component StatusDot
npx astryx component Token
npx astryx component TextInput
npx astryx component TextArea
npx astryx component Button
```

Query every additional component before using it. Copy installed prop names only. Do not introduce `<div>` layout, Tailwind/utility classes, StyleX, another component library, raw hex/px values, or root token overrides. Record desktop region budgets while following Astryx layout guidance; implement spacing/color/radius through Astryx props/tokens.

- [x] **Step 2: Write failing session/editor/accessibility tests**

Cover:

- session rows scoped to selected ready profile, current/stale/generating/failed labels, selected state, empty/error/retry, and no UUID as primary label;
- dynamic source section headings/order including Experience/Awards/unknown; read-only header; editable existing text/bullets/attribute values; remove/reorder actions without editing section identity/fact IDs;
- explicit manual save, selected-section AI dialog, version switch, unsaved-change confirmation, evidence disclosure, page warning, `.tex`/PDF actions, stale new-session action, conflict reload while preserving draft, compile/grounding error retention, and delete confirmation;
- desktop split view, mobile `Nội dung`/`Xem trước` tabs, keyboard order, labels, live stream state, Escape/focus restoration, reduced motion, and no overlap;
- no raw LaTeX, server path, source chunk, raw JD, contact in status/error, or malformed tool result rendered.

- [x] **Step 3: Run focused UI tests to verify RED**

```powershell
Set-Location frontend
npm test -- --run src/test/cv-tailoring-sessions-panel.test.tsx src/test/cv-tailoring-editor.test.tsx src/test/cv-tailoring-accessibility.test.tsx src/test/observability-navigation.test.tsx src/app/App.test.tsx
```

Expected: the new components/navigation/editor behavior do not exist, so the focused assertions fail before UI implementation.

- [x] **Step 4: Add the `CV đã chỉnh` navigation panel**

Add one tab ID and label through existing `observabilityTabs` ownership. `TailoringSessionsPanel` receives state/actions as props; it does not instantiate a second hook. Use edge-to-edge Astryx List/ListItem rows, `StatusDot`/`Token` for state, bounded Job title/company snapshot or instruction excerpt as label, localized timestamp/version count, and one selected row. Loading/error/empty states use existing neutral patterns. A failed zero-version row exposes explicit retry and delete actions. Opening calls App's shared workspace callback; deletion requires the dedicated AlertDialog.

- [x] **Step 5: Build the responsive editor shell**

`TailoringEditor` accepts the selected detail, local draft, versions, request phases, and callbacks. Desktop composes Astryx Layout with a structured section region and `AspectRatio` PDF region side by side. Mobile composes accessible TabList tabs. `Quay lại chat` changes workspace only; it does not reset session/saved-JD/chat state. The editor shows stale/current state, version selector, creator label, created time, page count/warning, and safe error banner.

- [x] **Step 6: Implement source-preserving structured field edits**

Render header name/location/phone/email/GitHub as read-only approved facts. `Sửa thông tin Profile` returns to chat and focuses the existing composer with a profile-correction affordance; it does not write profile JSON directly.

Render every section from `content.sections` in server order. `TailoredSectionEditor` may update text in existing `SourceBoundText`, reorder/remove items/bullets, and edit values under read-only attribute names. It carries existing `source_fact_ids`/IDs invisibly and cannot add/rename/reorder sections or add arbitrary provenance. `Nhờ AI chỉnh section này` opens an Astryx Dialog with bounded instruction and sends exactly that section ID plus latest parent version. Evidence uses an inspected Astryx disclosure/accordion component and shows only `TailoredFactEvidence.source_text` associated with the selected version.

- [x] **Step 7: Add explicit save/version/download/preview actions**

`Lưu version & tạo PDF` sends the full strict local content once; disable duplicate submit with a synchronous in-flight guard. A success selects/refetches the returned immutable version. A 409 parent conflict leaves local draft intact and offers `Tải version mới nhất`; grounding/compile failure leaves draft and previous PDF intact.

`TailoringPdfPreview` uses the exact selected version PDF URL inside an Astryx AspectRatio with a titled native PDF object/iframe and a fallback download link. It never fetches bytes into JSON or recompiles. Version actions use source/PDF URLs; `.tex` is download, PDF supports preview/download. Keystrokes and version selection never compile.

- [x] **Step 8: Implement retryable delete and stale recovery UX**

`TailoringSessionDeleteDialog` uses the inspected AlertDialog props, names the bounded session label, warns that all versions/downloads in that derivative session are removed, and issues zero request on cancel. Loading locks repeated action and focus returns after close. Profile deletion's existing warning is amended to state its tailored CV sessions/artifacts are also removed.

Stale sessions remain viewable/downloadable and disable AI/manual save. `Tạo phiên mới từ dữ liệu hiện tại` creates a new session using the retained instruction and currently selected Job only when still available/scorable; it never mutates the old session or silently substitutes another Job.

- [x] **Step 9: Add token-only styling and static UI guards**

`cv-tailoring.css` may use only Astryx token variables for grid/flex sizing gaps, borders, colors, radius, and motion. Add a test/source audit rejecting raw hex/rgb/hsl, hard-coded pixel declarations, Tailwind-like utility strings, and `<div` in the new feature. Respect `prefers-reduced-motion`; do not override `--color-*` at `:root`.

- [x] **Step 10: Run focused UI/static gates and commit**

```powershell
npm test -- --run src/test/cv-tailoring-sessions-panel.test.tsx src/test/cv-tailoring-editor.test.tsx src/test/cv-tailoring-accessibility.test.tsx src/test/observability-navigation.test.tsx src/app/App.test.tsx
npm run lint
npm run typecheck
npm run build
Set-Location ..
git add frontend/src/features/cv-tailoring/TailoringSessionsPanel.tsx frontend/src/features/cv-tailoring/TailoringEditor.tsx frontend/src/features/cv-tailoring/TailoredSectionEditor.tsx frontend/src/features/cv-tailoring/TailoringPdfPreview.tsx frontend/src/features/cv-tailoring/TailoringVersionActions.tsx frontend/src/features/cv-tailoring/TailoringSessionDeleteDialog.tsx frontend/src/features/cv-tailoring/cv-tailoring.css frontend/src/features/observability/observabilityTabs.ts frontend/src/features/observability/types.ts frontend/src/features/observability/ObservabilityTabList.tsx frontend/src/features/observability/ObservabilitySidebar.tsx frontend/src/app/App.tsx frontend/src/test/cv-tailoring-sessions-panel.test.tsx frontend/src/test/cv-tailoring-editor.test.tsx frontend/src/test/cv-tailoring-accessibility.test.tsx frontend/src/test/observability-navigation.test.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): add Astryx tailored CV editor"
```

Expected: focused tests, ESLint, TypeScript, and production build pass; new UI uses Astryx only and preserves chat/sidebar state across workspace switches.

---

### Task 10: Document operations and run full synthetic acceptance

**Files:**
- Modify: `README.md`
- Create: `docs/operations/cv-tailoring-latex.md`
- Create: `docs/acceptance/cv-tailoring-latex-checklist.md`
- Create: `backend/tests/e2e/test_cv_tailoring_flow.py`
- Modify: `backend/tests/e2e/test_demo_flow.py`
- Modify: `backend/tests/integration/test_health.py`
- Modify: `backend/tests/integration/test_compose_runtime.py`
- Modify: `frontend/src/test/setup.ts`

- [x] **Step 1: Write the operations and recovery contract**

Document TeX Live packages, six Settings, app-data layout as a conceptual server-owned path, migration head `0007_add_cv_tailoring`, health/startup commands, currentness rules, optional contact re-extraction/approval, source/PDF download behavior, session/profile deletion retry, and safe failure codes. State explicitly that the template is fixed, sections remain source-owned, the LLM never emits/sees LaTeX, and existing profiles get contacts only through explicit re-extraction + Save Profile. Do not include reference CV content, real CV/JD text, absolute local paths, logs, or secrets.

- [x] **Step 2: Add a synthetic cross-layer E2E flow**

Use fake structured providers and generated synthetic CV/JD data only. Exercise:

1. old CandidateProfile JSON with null contacts;
2. re-extraction/approval with GitHub present and a second profile with GitHub absent;
3. selected full/partial JD session creation and instruction-only chat-tool creation;
4. unrelated-section privacy and grounded initial version;
5. manual edit, section-scoped AI edit, immutable version/history/CAS conflict;
6. stale profile/CV/JD revisions blocking writes but preserving reads;
7. saved Job deletion preserving downloads;
8. session and profile deletion cleanup/retry;
9. exact `.tex` template/escaping and PDF metadata;
10. unchanged evaluations/Neo4j/matching records and exactly eight Main-Agent tools.

Inject `REFERENCE_ONLY_SENTINEL_7429` solely into a fake format-reference object that has no route to the coordinator; assert it is absent from captured prompts, ToolResults, SQLite JSON, activity/error text, `.tex`, PDF-extracted text, and logs.

- [x] **Step 3: Run focused backend feature gates**

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_cv_contact_contracts.py tests/unit/test_cv_tailoring_schemas.py tests/unit/test_cv_tailoring_projection.py tests/unit/test_cv_tailoring_guard.py tests/unit/test_cv_tailoring_models.py tests/unit/test_cv_tailoring_storage.py tests/unit/test_cv_tailoring_renderer.py tests/unit/test_cv_tailoring_compiler.py tests/unit/test_cv_tailoring_agent.py tests/unit/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_repository.py tests/integration/test_cv_tailoring_coordinator.py tests/integration/test_cv_tailoring_api.py tests/integration/test_cv_tailoring_deletion.py tests/e2e/test_cv_tailoring_flow.py -q
```

Expected: all feature unit/integration/E2E tests pass with fakes except the explicitly real compiler test.

- [x] **Step 4: Run full backend static/test/migration gates**

```powershell
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q
& '..\.venv\Scripts\python.exe' -m pytest tests/integration/test_migrations.py -q
```

Expected: Ruff/Mypy/full Pytest pass; migration tests use disposable databases to upgrade/downgrade/re-upgrade with head `0007_add_cv_tailoring`; no approved data is rewritten during upgrade. Never run a downgrade against the user's configured database.

- [x] **Step 5: Run full frontend gates**

```powershell
Set-Location ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: full Vitest, ESLint, strict TypeScript, and production build pass; one saved-JD controller and one ChatPage chat reducer remain.

- [x] **Step 6: Validate the approved planning portfolio**

After the separately authorized Master 2.3/Plan 16/Plan 17 changes exist, run:

```powershell
Set-Location ..
& '.\.venv\Scripts\python.exe' 'C:\Users\ACER\.codex\skills\plan-splitter\scripts\validate_plan_structure.py' 'docs/plans' --json
```

Expected: Plans 1–17 are contiguous; Plans 1–16 have normal handoffs; only Plan 17 is terminal. If portfolio authorization has not occurred, record this gate as blocked and do not start implementation.

- [x] **Step 7: Build and verify the real three-service candidate**

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config --services
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.services.cv_tailoring_smoke
```

Expected: service list is exactly Neo4j/backend/frontend; health is available; migration reaches 0007 before Uvicorn; both Docker build and running-container smoke compile the fixed bilingual template with shell escape disabled; no fourth service/runtime network compile dependency appears. The image intentionally contains neither tests nor Pytest.

- [ ] **Step 8: Execute browser acceptance with synthetic profiles**

Use the in-app browser against `http://localhost:5173`. Record sanitized route/status/screenshot evidence for: selected-JD button; natural-language Main-Agent creation; editor link; GitHub present/absent separators; Experience/Awards/unknown headings; desktop split/mobile tabs; manual and scoped AI versions; evidence disclosure; `.tex` download/PDF preview; two-page warning; stale state/new-session action; CAS conflict; grounding/compile failure preserving draft/previous PDF; saved Job deletion; cancel/confirm session deletion; profile delete warning/cleanup; keyboard/focus/reduced-motion behavior. Confirm no raw template/CV/JD, server path, UUID label, secret, console error, overlap, automatic evaluation, or Neo4j tailoring data.

- [x] **Step 9: Run final scope/data/secret review and commit documentation**

```powershell
Set-Location ..
rg -n "useSavedJobsState\(" frontend/src
rg -n "create_tailored_cv|PRODUCTION_DOMAIN_TOOL_NAMES|production_registry" backend/app backend/tests
rg -n "shell=True|create_subprocess_shell|write18|shell-escape" backend/app infrastructure/docker/backend.Dockerfile
rg -n "cv_tailoring|cv-tailoring" backend/app frontend/src infrastructure docs README.md
git diff --check
git status --short
git add README.md docs/operations/cv-tailoring-latex.md docs/acceptance/cv-tailoring-latex-checklist.md backend/tests/e2e/test_cv_tailoring_flow.py backend/tests/e2e/test_demo_flow.py backend/tests/integration/test_health.py backend/tests/integration/test_compose_runtime.py frontend/src/test/setup.ts
git commit -m "docs: document tailored CV operations and acceptance"
```

Expected: one production saved-JD hook call; exactly eight Main-Agent tools and one bounded tailoring graph; no shell-enabled compiler; only authorized paths are changed/staged; `git diff --check` is clean; no real/private runtime data or generated artifacts are tracked.

---

## Final self-review checklist

- [x] Every approved design section maps to a task: contacts (1), content/provenance/grounding (2), persistence/run ownership (3), artifact/template (4), compiler/runtime (5), bounded Agent/coordinator (6), API/tool/transport/deletion (7), frontend contracts/state (8), Astryx editor (9), rollout/acceptance (10).
- [x] `TailoredAttribute` is consistently `name + values`; section IDs/headings/kinds/ordinals and attribute names are immutable across schema, Agent patch, manual edit, renderer, API, and TypeScript.
- [x] Session creation exposes its durable ID through `X-CV-Tailoring-Session-Id`; the seven existing SSE event names remain unchanged and disconnect is never success.
- [x] The Tailoring Agent first sees outline/JD/instruction, then only selected bodies/facts; reference format, contacts, raw PDFs/JDs, unrelated bodies, paths, Neo4j, and secrets are absent.
- [x] Exactly one schema-or-grounding repair is shared; deterministic anchor checks and scoped semantic support apply to both AI and manual changes.
- [x] Every successful generation/save creates immutable `.tex` and PDF artifacts; promotion/CAS cleanup cannot commit missing files or overwrite a newer version.
- [x] Renderer owns one fixed preamble/layout and dynamic source-owned sections; absent optional contacts render no placeholders or stray separators.
- [x] `pdflatex` runs twice through argv-only async execution with `-no-shell-escape`, bounds, safe failures, no persisted logs, and a mandatory container smoke.
- [x] Main Agent and direct button use the same coordinator; the Plan 17 production path contains the Main Agent and bounded CV Tailoring Agent, eight Main tools, one saved-JD state owner, and no unapproved Agent topology or extra service/worker/queue. This phase does not create a project-wide Agent-count ceiling.
- [x] Approved CV/Profile/JD, evaluations, matching, and Neo4j remain unchanged; old versions survive source/Job staleness and Job deletion.
- [x] Frontend uses inspected Astryx components/tokens only, keeps ChatPage mounted, and covers responsive/accessibility/error/conflict/delete behavior.
- [ ] Full backend/frontend/migration/portfolio/Docker/compiler/browser/scope/data/secret gates are recorded before completion is claimed.
