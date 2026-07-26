# Source-Grounded CV Tailoring and Fixed LaTeX Rendering Design

**Date:** 2026-07-26
**Status:** Approved; amended for controlled multi-agent governance
**Scope:** Create versioned, editable derivative CVs from an approved active CV,
an optional selected saved JD, and a user instruction without modifying the
approved CV or allowing an LLM to emit LaTeX.

## 1. Context

JobAgent currently owns approved PDF CVs, document-first `CVDocument` records,
approved Candidate Profiles, saved JDs, deterministic matching, one
conversation Agent, and bounded active-CV reads. It has no LaTeX template,
tailoring artifact, PDF compilation path, CV section editor, or transport from
the sidebar's selected saved JD into a chat turn.

The user supplied a LaTeX CV as a visual-format reference. Its personal and
domain-specific values are not product requirements and must never be copied
into prompts, fixtures, logs, generated defaults, or documentation. The locked
contract is the presentation system: document preamble, page geometry, section
typography, entry/list patterns, and contact-row composition. The actual
sections, headings, order, and facts come from the approved CV.

This design deliberately creates derivative artifacts. It does not edit the
retained PDF, approved `CVDocument`, Candidate Profile, archived CVs, saved JD,
matching data, or Neo4j projection in place.

## 2. Approved Product Decisions

1. Every successful generation or save creates an immutable version with both
   `.tex` and PDF artifacts.
2. A session can start from **Tạo CV theo JD** on the selected saved JD or from
   a natural-language chat request. Both entry points use one backend
   coordinator.
3. The LLM may read the selected JD extraction and only the active-CV sections
   selected for that request. It never receives the reference template or the
   bodies of unrelated sections.
4. Tailoring may select, reorder within a section, and truthfully rephrase
   source-supported facts. It may not invent employers, roles, skills,
   education, metrics, dates, links, or achievements. Missing JD requirements
   are shown as gaps outside the CV, never inserted as candidate facts.
5. The editor supports direct structured edits and AI edits scoped to selected
   sections. Every save creates a version; no version is mutated in place.
6. Contact facts are extracted during normal CV processing, shown in profile
   approval, and reused across derivative CVs. GitHub and every non-name contact
   field are optional.
7. Plan 17 adds one bounded CV Tailoring Agent beside the existing Main Agent.
   This phase adds no third Agent or open-ended handoff topology, but JobAgent has
   no permanent global Agent-count ceiling; future Agents require an approved,
   coordinator-owned contract under the controlled multi-agent governance design.
8. The frontend uses Astryx and the repository's neutral theme. It does not
   introduce Tailwind, a second component system, raw color values, or guessed
   Astryx props.
9. The LaTeX presentation contract is fixed, but the source CV owns the section
   list, headings, and order. `Experience`, `Awards`, unknown sections, and
   other profession-specific content therefore remain representable.

## 3. Goals

- Produce a source-grounded CV derivative for one ready profile, optionally
  tailored to one processed saved JD.
- Preserve one authoritative approved CV while allowing multiple independent
  tailoring sessions and immutable versions.
- Keep the reference template out of every LLM context and make the backend the
  sole LaTeX owner.
- Let users inspect evidence, edit sections, request a scoped AI revision,
  preview PDF, and download exact version artifacts.
- Extract and approve the header facts needed for rendering without exposing
  them in ordinary profile lists, Agent status events, or logs.
- Preserve the current three-service Compose deployment, SQLite authority,
  rebuildable Neo4j model, explicit saved-JD evaluation, and multi-profile
  ownership boundaries.

## 4. Non-Goals

- No mutation of approved or archived CV content.
- No arbitrary LaTeX editor, uploaded `.tex`, user-selected package, custom
  command, image, font, page geometry, or template variant.
- No cover-letter generation, auto-apply, job discovery, OCR, DOCX, or public
  deployment.
- No unsupported fact insertion, even after an LLM suggestion. A user who needs
  to add or correct a source fact must use the profile correction and approval
  flow first.
- No automatic CV generation after selecting or re-extracting a JD, changing a
  profile, or switching profiles.
- No automatic JD evaluation or matching-score recomputation.
- No Neo4j node, relationship, embedding, or vector index for tailored CVs.
- No background worker, queue, fourth Compose service, or unbounded Agent loop.
- No silent migration or provider backfill of contact data for existing
  profiles.

## 5. Architecture and Ownership

```text
Selected saved JD or chat instruction
  -> Main Agent tool or direct tailoring API
  -> TailoringCoordinator
  -> CV Tailoring Agent: select section IDs from outline
  -> server loads only those approved section bodies
  -> CV Tailoring Agent: emit structured edits + source_fact_ids
  -> grounding guard (one bounded repair at most)
  -> deterministic TailoredCVContent assembly
  -> fixed LaTeX renderer
  -> bounded pdflatex compiler
  -> immutable SQLite version + app_data artifacts
```

Ownership is explicit:

- Approved `CVDocument`, approved Candidate Profile, profile contact facts, and
  saved `JobPostExtraction` remain source records.
- `TailoringCoordinator` owns generation orchestration, revision checks, file
  staging, compare-and-swap, and version creation.
- The CV Tailoring Agent owns section selection and structured rewriting only.
- The grounding guard owns fact/provenance acceptance. The renderer does not
  infer facts, and the frontend does not classify grounding.
- `latex-cv-v1` is the sole visual-template owner. Neither Agent sees or edits
  it.
- SQLite owns sessions, versions, source revisions, provenance, and artifact
  metadata. The `app_data` volume owns immutable `.tex` and PDF files.
- The frontend owns unsaved local form state only. Server versions are the
  durable truth.

## 6. Agent Topology

### 6.1 Main Agent

The existing chat Agent remains the conversation and intent owner. Its
production registry gains one tool, `create_tailored_cv`, increasing the
top-level tool count from seven to eight. The tool accepts a bounded instruction
but not raw CV text, raw JD text, a template, LaTeX, a filesystem path, or an
arbitrary Job ID.

The backend injects the validated optional `selected_job_id` into graph state.
The tool resolves that state server-side and calls `TailoringCoordinator`. Its
safe result contains `session_id`, `version_id`, currentness, and a short status
only. The resulting assistant row exposes **Mở CV editor** and does not inline
the CV, contact details, `.tex`, or PDF bytes.

### 6.2 CV Tailoring Agent

The Plan 17 specialist Agent is a separate bounded LangGraph workflow, not a peer chat
Agent and not an open ToolNode loop. It has a fixed sequence:

1. Select target section IDs from the approved CV outline, structured saved-JD
   extraction when present, and the bounded user instruction. No section body
   is available at this step.
2. Receive only the server-loaded target section bodies and their source-fact
   bank.
3. Emit strict structured replacements for those sections. Every output item
   cites one or more input `source_fact_ids`.
4. Pass the result to the grounding guard. One sanitized repair is allowed for
   schema or grounding rejection; a second rejection is terminal.

The workflow never receives profile contact values, unrelated section bodies,
the reference template, raw PDF bytes, raw retained JD, embeddings, Neo4j data,
storage paths, or provider secrets. It cannot invoke the Main Agent or spawn
another Agent.

### 6.3 Durable run ownership

`agent_runs` becomes a dual-owner run table:

- `run_kind` is `chat` or `cv_tailoring`.
- A chat run has non-null `user_message_id` and null
  `tailoring_session_id`.
- A tailoring run has null `user_message_id` and non-null
  `tailoring_session_id`.
- `parent_run_id` is nullable and may point from a chat-initiated tailoring run
  to its Main Agent run. Direct button generation has no parent.
- Database checks enforce the owner XOR and valid parent relationship.

Existing `agent_activities`, checkpoints, safe status projection, and terminal
state rules are reused. The workspace activity gate treats a child tailoring
run as owned work of its parent and blocks unrelated concurrent profile,
conversation, CV, Job, or tailoring mutations.

## 7. Contact Extraction and Approval

`CandidateProfile` gains backward-compatible nullable fields with defaults:

```text
phone: str | null
email: str | null
github_url: str | null
```

`full_name` and `location` remain their existing nullable fields. A separate
public profile-list projection does not expose phone, email, or GitHub.

The document extraction provider contract gains source-grounded contact rows:

```text
ExtractedContactFact
- kind: phone | email | github_url
- value: str
- evidence: str
- source_chunk_ordinal: int
```

Rules:

- `evidence` must occur in the referenced canonical chunk under the existing
  NFKC/whitespace comparison policy.
- The accepted `value` must be represented by that evidence after
  kind-specific normalization.
- At most one source-ordered value per kind is projected. Ambiguous competing
  values produce a warning and no automatic selection.
- Email and phone use bounded syntax checks. GitHub accepts only an absolute
  HTTP(S) `github.com` profile URL and is never inferred from profession,
  username-like text, or a repository mention.
- Contact facts appear in the existing profile approval/correction flow.
  Explicit user corrections become approved profile truth only after the same
  interrupt/resume approval contract.
- Existing profiles continue to parse with null contact fields. They obtain
  contact data only through **Re-extract CV** followed by **Save Profile**.

Tailoring requires a confirmed non-empty `full_name`. Location, phone, email,
and GitHub are independently optional. The renderer omits absent values and
their separators; it never renders blanks or placeholders.

## 8. Tailored Content and Provenance Contracts

The provider never emits LaTeX. The durable content contract is generic enough
for every validated source section:

```text
TailoredCVContent
- header: TailoredHeaderSnapshot
- sections: list[TailoredSection]

TailoredHeaderSnapshot
- full_name: str
- location: str | null
- phone: str | null
- email: str | null
- github_url: str | null

TailoredSection
- id: str
- ordinal: int
- heading: str
- kind: existing CVSectionKind
- items: list[TailoredItem]

TailoredItem
- id: str
- source_entry_id: str | null
- title: SourceBoundText | null
- subtitle: SourceBoundText | null
- date_text: SourceBoundText | null
- location: SourceBoundText | null
- body: SourceBoundText
- bullets: list[SourceBoundText]
- attributes: list[TailoredAttribute]

SourceBoundText
- text: str
- source_fact_ids: list[str]
```

The server derives the rendering layout from `CVSection.kind`; layout is not an
LLM field. Source section IDs, headings, kinds, and ordinals are immutable in a
session. Sections may not be added, removed, renamed, or reordered. Untargeted
sections are copied byte-for-byte at the structured text-field level and never
enter an LLM request. A targeted section may omit, reorder, or truthfully
rephrase its own items while preserving source provenance.

Before any Agent call, a deterministic baseline projector converts the complete
approved `CVDocument` into `TailoredCVContent` without changing source section
identity or text. The projector assigns server-owned layout and item IDs and
copies the approved profile header snapshot. Only the selected baseline
sections are serialized to the Tailoring Agent. Initial untargeted sections are
copied exactly from this baseline; later untargeted sections are copied exactly
from the parent tailored version.

Each source fact has a stable ID derived from the source revision, section ID,
entry ID, and field path. The grounding guard enforces:

- every cited fact exists in the target-section fact bank;
- every output item cites at least one fact unless it is an empty structural
  container;
- names, dates, numbers, URLs, employers, institutions, and canonical skills
  cannot appear unless supported by cited evidence;
- evidence from an unrelated section, another profile, another CV revision, or
  the reference template is invalid;
- duplicate IDs, out-of-order ordinals, unbounded text, and unknown fields are
  rejected;
- a semantic source-support check may approve paraphrasing but receives only
  the output item and its cited evidence.

Manual editor saves pass through the same schema, fact bank, and grounding
guard. Unsupported manual additions are rejected with section/item paths. A
new real-world fact must first enter the approved profile/CV correction flow.

## 9. Persistence and Artifact Lifecycle

### 9.1 `cv_tailoring_sessions`

```text
id: UUID primary key
profile_id: ready-profile FK, ON DELETE CASCADE
source_attachment_id: approved attachment FK
source_hash: canonical CV revision
profile_updated_at: approved profile revision
job_id: nullable saved-Job FK, ON DELETE SET NULL
job_updated_at: nullable selected-JD revision
job_label_json: nullable bounded title/company snapshot
instruction: bounded user instruction
template_version: latex-cv-v1
state: generating | ready | failed | deleting
latest_version_number: non-negative integer
error_code: nullable safe terminal code
created_at / updated_at: aware timestamps
```

At least one of `job_id` or a non-empty instruction is required at creation.
Only `full` or `partial` processed Jobs are accepted. The row stores no raw JD,
provider payload, LaTeX log, or template source.

### 9.2 `cv_tailoring_versions`

```text
id: UUID primary key
session_id: FK, ON DELETE CASCADE
version_number: positive integer, unique per session
parent_version_id: nullable same-session FK
created_by: ai | user
content_json: validated TailoredCVContent
provenance_json: validated fact/source map
source_revision_json: profile/CV/JD/template revisions
tex_relative_path / pdf_relative_path: server-owned artifact paths
tex_sha256 / pdf_sha256: artifact hashes
page_count: positive integer
page_warning: nullable over-two-page warning
created_at: aware timestamp
```

Versions are immutable. A new save includes `parent_version_id`; the session's
`latest_version_number` is compare-and-swapped in the same transaction. A stale
parent returns `TAILORING_PARENT_CONFLICT` and never overwrites newer work.

Artifacts live under a UUID-derived server path:

```text
FILES_DIR/cv-tailoring/<profile_id>/<session_id>/<version_id>/resume.tex
FILES_DIR/cv-tailoring/<profile_id>/<session_id>/<version_id>/resume.pdf
```

Paths are never accepted from or exposed to clients. Rendering and compilation
complete in a temporary staging directory. Final files are promoted to the
unique version path before the short CAS transaction; transaction failure
removes only those newly promoted files. A version row is therefore never
committed with missing initial artifacts.

### 9.3 Currentness and deletion

A session becomes stale when its profile revision, CV source hash, selected Job
revision, or template version differs from current authoritative state. Old
versions remain readable and downloadable. New AI or manual versions are
blocked with `TAILORING_SOURCE_STALE`; the UI offers an explicit new session
from current sources and never rewrites an old session automatically.

Deleting a saved Job sets `job_id` to null and preserves its bounded label and
all artifacts. Existing versions remain downloadable; new JD-based revisions
require a new selected Job or an instruction-only session. Profile deletion
warns that its tailored CV sessions and artifacts are owned data, then removes
them through the profile deletion coordinator. Session deletion is explicit,
retryable, and removes only that session's runs, checkpoints, metadata, and
UUID-scoped artifacts.

## 10. Public API and Transport

### 10.1 Selection propagation

The sole `useSavedJobsState` instance moves from `ObservabilitySidebar` to
`App`. `App` passes the same state/actions back to the sidebar and passes only
`selectedJobId` into `ChatPage`. No second saved-JD cache or selector is
introduced.

`ChatTurnRequest` gains nullable `selected_job_id`. The backend validates the
UUID, reloads the global saved Job, separately requires one active ready
profile, verifies that the Job is `full` or `partial`, and injects only validated
state into the graph. The client cannot attach replacement JD content.

### 10.2 Endpoints

```text
POST   /api/cv-tailoring/sessions
GET    /api/cv-tailoring/sessions
GET    /api/cv-tailoring/sessions/{session_id}
POST   /api/cv-tailoring/sessions/{session_id}/ai-versions
POST   /api/cv-tailoring/sessions/{session_id}/manual-versions
GET    /api/cv-tailoring/versions/{version_id}/source
GET    /api/cv-tailoring/versions/{version_id}/pdf
DELETE /api/cv-tailoring/sessions/{session_id}
```

- Session creation and AI-version creation return typed SSE because they run
  the Tailoring Agent and provider calls synchronously without a worker.
- Manual-version creation is a bounded JSON request and response.
- List/detail responses contain metadata, validated structured content,
  currentness, safe evidence projections, and download availability. They do
  not contain server paths, raw source chunks, raw JD, `.tex` in JSON, PDF bytes
  in JSON, checkpoints, or provider data.
- Source and PDF endpoints authorize through session/profile ownership, stream
  only the exact stored artifact, set safe content types and filenames, and
  never compile on read.
- SSE activity uses the existing safe activity vocabulary. Disconnect is not a
  success signal; session/run reads recover durable terminal state.

## 11. LaTeX Presentation Contract

`latex-cv-v1` preserves the reference's visual shell:

```text
document class: article, 11pt
packages: graphicx, hyperref, enumitem, inputenc utf8, fontenc T5/T1,
          babel Vietnamese/English, geometry, titlesec
paragraph indent: 0pt
geometry: left/right 1.06cm, top 1.2cm, bottom 1.0cm
section style: large, bold, uppercase, trailing title rule
section spacing: 10pt before, 5pt after
header: centered large bold name, conditional contact row
entry heading: bold left value with optional right-aligned date/link
lists: no item separation, top separation 2pt
entry separation: 5pt where multiple blocks require it
```

The actual section list and order exactly match the source `CVDocument`.
Section headings are escaped source headings and rendered through the same
`\section{...}` style. Renderer-owned kind mappings select paragraph,
skill-group, entry, project, or simple-list presentation. Unknown `other`
sections use the generic entry presentation. No profession name, heading
dictionary, or sample-specific skill group is hardcoded.

Contact order is location, phone, email, then GitHub. Only present values are
rendered, with `\textbullet` inserted between adjacent present values. GitHub
uses a validated HTTP(S) URL; when it is null, both link and separator are
absent.

The renderer escapes at least `#`, `$`, `%`, `&`, `_`, `{`, `}`, `~`, `^`, and
backslash in text contexts and uses a separate validated URL renderer for
`\href`. AI/user strings can never become commands, environments, comments,
package names, file includes, or preamble content.

The visual reference's T1 setup is extended to `\usepackage[T5,T1]{fontenc}`
plus Vietnamese/English Babel support. T5 is the official LaTeX Vietnamese font
encoding; this technical extension preserves the approved visual layout while
allowing the product's existing Vietnamese/English CV contract to compile
without stripping diacritics.

## 12. PDF Compilation

The existing backend image installs Debian Bookworm packages
`texlive-latex-base`, `texlive-latex-recommended`,
`texlive-latex-extra`, `texlive-fonts-recommended`, and
`texlive-lang-other`. This keeps the supported Compose topology at frontend,
backend, and Neo4j only. The image build performs one synthetic bilingual
template compilation smoke test.

The compiler adapter runs `pdflatex` twice with an argv array, never a shell
string:

```text
pdflatex -no-shell-escape -halt-on-error -interaction=nonstopmode
          -output-directory=<server-owned-temp> resume.tex
```

Bounds are owned by validated Settings:

```text
CV_TAILOR_MAX_INSTRUCTION_CHARS=4000
CV_TAILOR_MAX_SECTIONS=20
CV_TAILOR_MAX_ITEMS_PER_SECTION=30
CV_TAILOR_MAX_TEX_CHARS=100000
CV_TAILOR_COMPILE_TIMEOUT_SECONDS=15
CV_TAILOR_MAX_PDF_MB=5
```

Compilation has no runtime network need, shell escape, arbitrary working
directory, client filename, user package, user image, or user-provided TeX.
Only the fixed template and renderer output exist in the temporary directory.
Timeout, nonzero exit, missing PDF, oversized output, or invalid page count
returns `TAILORING_COMPILE_FAILED`; logs are reduced to a safe code and are not
persisted or sent to the client. A result over two pages is valid but receives
a concise warning; content is never silently removed to satisfy a page target.

The flags and packages are grounded in the official TeX Live/CTAN and Debian
package contracts:

- https://tug.org/texlive/doc/texlive-en/texlive-en.pdf
- https://www.ctan.org/pkg/enumitem
- https://www.ctan.org/pkg/titlesec
- https://ctan.org/pkg/vntex
- https://packages.debian.org/bookworm/tex/texlive-lang-other
- https://packages.debian.org/texlive-latex-extra

## 13. Frontend Experience

All implementation follows `frontend/AGENTS.md`. Before UI code, the engineer
runs `npx astryx build` for a section editor with PDF preview, inspects the
named templates, and queries every component used with
`npx astryx component`. Astryx owns shell, layout, navigation, tabs, form
controls, buttons, dialogs, banners, status, loading, and typography. Custom CSS
uses Astryx tokens only.

### 13.1 Entry points and navigation

- Saved-JD detail gains **Tạo CV theo JD** for a selected `full` or `partial`
  Job.
- A successful Main Agent tailoring result renders **Mở CV editor**.
- The sidebar gains **CV đã chỉnh**, scoped to the selected ready profile, with
  compact session rows and current/stale state.
- Opening a session swaps the main workspace from chat to the CV editor while
  preserving sidebar state. **Quay lại chat** restores the conversation without
  remounting the saved-JD owner.

### 13.2 Editor

- Desktop uses a section editor and PDF preview side by side.
- Mobile uses accessible **Nội dung** and **Xem trước** tabs.
- Header values are read-only approved-profile facts. A dedicated profile
  correction action is used when they are wrong.
- Each source section is present in source order. It supports direct structured
  editing, **Nhờ AI chỉnh section này**, and collapsed evidence.
- No LaTeX source editor, rich-text HTML, arbitrary Markdown, or raw source
  chunk panel is added.
- **Lưu version & tạo PDF** validates and compiles explicitly. Keystrokes never
  trigger compilation.
- A version selector, created-by label, page warning, current/stale status,
  `.tex` download, PDF download, and session delete confirmation are available.
- A conflict keeps the local draft and offers reload; grounding/compile failure
  keeps the local draft and the previous server version.

## 14. Error and Recovery Policy

Stable safe codes include:

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

Errors expose a short summary and recovery action only. They never expose CV/JD
text, contact data, LaTeX logs, provider payloads, prompts, checkpoints, stack
traces, credentials, or paths.

- Provider timeout/rate-limit behavior reuses the existing bounded retry owner.
- Schema or grounding rejection shares one repair budget; it does not receive
  an additional independent retry loop.
- A failed initial generation leaves a durable failed session/run that can be
  explicitly retried or deleted.
- A failed later generation creates no version and preserves the latest
  version.
- Artifact read failure does not regenerate on demand; it reports unavailable
  and requires an explicit new version after storage recovery.
- Partial session deletion remains `deleting` and retryable. It never reports
  success while files, checkpoints, runs, or database rows remain.

## 15. Testing and Acceptance

### 15.1 Backend

- CandidateProfile backward compatibility and contact validation.
- Contact extraction evidence, ambiguity, correction, approval, re-extraction,
  and optional GitHub behavior.
- Dynamic section preservation across `summary`, `experience`, `education`,
  `skills`, `projects`, certifications, awards, and `other`.
- Section-selector privacy: no body before selection and no unrelated body
  after selection.
- Strict provider schemas, fact ID stability, grounding/repair limits, and
  manual-edit grounding.
- A sentinel reference-format fixture proving example-only values never enter
  prompts, outputs, persisted records, logs, or artifacts.
- Exact golden `.tex` rendering for dynamic sections, conditional contact
  separators, URLs, English/Vietnamese Unicode including T5 diacritics, and all
  LaTeX metacharacters.
- Compiler argv, timeout, shell-escape disabling, output bounds, page warning,
  staging cleanup, and a synthetic real-`pdflatex` container smoke test.
- Migration preservation, run owner XOR, child-run linkage, CAS conflicts,
  currentness, Job `SET NULL`, profile/session deletion, and artifact failures.
- Direct API and chat-tool parity with no duplicate business-rule owner.

### 15.2 Frontend

- Strict request/response/SSE parsers reject extra or malformed fields.
- One `useSavedJobsState` instance serves sidebar, graph, button, and chat
  selection.
- Saved-JD action visibility, chat editor link, session list, dynamic sections,
  manual save, scoped AI edit, evidence, version switch, downloads, stale state,
  conflict recovery, compile error, and delete confirmation.
- Astryx component usage, keyboard order, focus restoration, labels, live status,
  desktop split layout, mobile tabs, reduced motion, and no overlapping content.
- No raw LaTeX, CV/JD source, contact leakage, UUID-as-label, or server path in
  user-facing error states.

### 15.3 Repository and runtime

- Backend Ruff, Mypy, focused/full Pytest, migration, and Docker image gates.
- Frontend Vitest, ESLint, TypeScript, build, and Astryx discovery evidence.
- Plan-set validator, `git diff --check`, tracked-data/secret inspection, and
  exact three-service Compose verification.
- Browser acceptance with synthetic profiles from multiple professions, an
  `Experience` CV, an unknown section, GitHub present, GitHub absent, selected
  JD creation, instruction-only creation, manual revision, AI revision, stale
  sources, `.tex` download, PDF preview, and mobile layout.

## 16. Rollout and Planning Impact

This is a Master-level feature and cannot be implemented under the current
Version 2.2 scope. After written-spec approval, planning requires explicit user
authorization to:

1. amend `docs/plans/Master_plan.md` to Version 2.3 for derivative CVs, contact
   extraction, one bounded Tailoring Agent, controlled multi-agent governance,
   eight Main Agent tools, schemas, APIs, TeX
   dependency, Astryx editor, failure policy, tests, and Definition of Done;
2. replace only `Plan_16.md`'s terminal `Completion Contract` with the canonical
   handoff to `Plan_17.md`, preserving all historical scope and evidence; and
3. append `docs/plans/Plan_17.md` as the new terminal phase after the complete
   existing plan portfolio passes validation and review.

The future implementation migration is expected to add tailoring tables and
generalize `agent_runs`; it does not rewrite approved CV/JD records. Existing
profiles keep working with nullable contact fields and require explicit
re-extraction/approval only when the user wants extracted contact data.

`README.md` must be realigned with the implemented Plan 16/current multi-profile
baseline and later document Plan 17 setup, TeX dependency, commands, recovery,
and synthetic acceptance. Task writing and implementation do not begin until
the amended portfolio is approved through the repository's planning gates.

## 17. Acceptance Criteria

The feature is complete only when all of the following are true:

1. Both a selected saved JD and an instruction-only chat request can create the
   same versioned derivative-CV contract.
2. The Tailoring Agent receives only the selected structured JD, instruction,
   outline, and target-section facts; the reference template and unrelated
   sections are absent.
3. Every tailored item is traceable to approved source facts, and unsupported
   AI or manual content cannot become a version.
4. Source sections and order survive across professions, including `Experience`
   and unknown headings.
5. The generated `.tex` follows `latex-cv-v1`, compiles English and Vietnamese
   text without shell escape, and produces a downloadable PDF.
6. Missing GitHub or other optional contact fields produces neither placeholder
   text nor stray separators.
7. Versions are immutable, CAS-safe, currentness-aware, recoverable after SSE
   disconnect, and downloadable after their Job is deleted.
8. Approved CV/Profile/JD records, matching, evaluations, and Neo4j remain
   unchanged by tailoring.
9. The frontend is Astryx-based, accessible, responsive, and uses one saved-JD
   selection owner.
10. Full backend, frontend, migration, plan, Docker, compiler, security, and
    synthetic browser gates pass without real CV/JD content, secrets, a fourth
    service, or an unapproved/unbounded Agent topology.
