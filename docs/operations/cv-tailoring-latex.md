# CV tailoring and fixed LaTeX operations

This feature creates derivative, immutable CV versions from one ready approved
profile and either a selected scorable saved Job or a bounded instruction. It
does not modify the approved CV, Candidate Profile, saved Job, evaluation,
matching, or Neo4j projection.

## Runtime contract

- The backend image includes `texlive-latex-base`,
  `texlive-latex-recommended`, `texlive-latex-extra`,
  `texlive-fonts-recommended`, and `texlive-lang-other`.
- Alembic head is `0007_add_cv_tailoring`. The container runs
  `alembic upgrade head` before Uvicorn; FastAPI startup does not migrate the
  SQLite schema.
- Compose remains exactly `neo4j`, `backend`, and `frontend`. Compilation runs
  in the existing backend service and needs no runtime network dependency.
- `latex-cv-v1` is the only presentation template. User and provider text is
  escaped before interpolation. The LLM never receives or emits LaTeX.
- Source-owned section IDs, headings, kinds, order, and attribute names remain
  fixed. AI and manual versions pass the same source-grounding guard.

## Settings

| Variable | Default | Bound |
|---|---:|---|
| `CV_TAILOR_MAX_INSTRUCTION_CHARS` | `4000` | User/Agent instruction length |
| `CV_TAILOR_MAX_SECTIONS` | `20` | Sections accepted by projection and rendering |
| `CV_TAILOR_MAX_ITEMS_PER_SECTION` | `30` | Items accepted per source section |
| `CV_TAILOR_MAX_TEX_CHARS` | `100000` | Generated TeX source size |
| `CV_TAILOR_COMPILE_TIMEOUT_SECONDS` | `15` | Per compiler invocation timeout |
| `CV_TAILOR_MAX_PDF_MB` | `5` | Compiled PDF size |

Keep the same values in the root environment template, Compose interpolation,
and backend Settings. Do not print the local environment file.

## App-data ownership

SQLite owns tailoring sessions, immutable versions, provenance, run state, and
artifact metadata. The server-owned files area conceptually contains:

```text
cv-tailoring/<profile UUID>/<session UUID>/<version UUID>/resume.tex
cv-tailoring/<profile UUID>/<session UUID>/<version UUID>/resume.pdf
```

These are conceptual relative paths only. Clients provide no path or filename,
and public responses expose no server path. A successful initial generation,
AI revision, or manual save promotes both artifacts before the version CAS is
committed.

## Currentness and editing

A session becomes stale when its approved profile revision, active CV source
hash, selected Job revision, or template version changes. Existing versions
stay readable and downloadable. AI and manual writes are blocked until the user
explicitly creates a new session from current sources.

For stale-session recovery, reuse the retained instruction. Reuse the currently
selected Job only when it still exists, is `processed`, and has `full` or
`partial` quality. Otherwise use instruction-only recovery only when the
retained instruction is non-empty; never substitute another Job.

Old profiles have nullable phone, email, and GitHub fields. Contacts appear in
tailored CVs only after explicit CV re-extraction, review, and **Save Profile**.
GitHub is optional. Missing optional contacts and their separators are omitted.

## Health, migration, and smoke

Run from the repository root without printing configuration:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config --services
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build -d --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/api/health
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T backend python -m app.services.cv_tailoring_smoke
```

Expected service names are exactly `neo4j`, `backend`, and `frontend`. Health
must report SQLite, filesystem, and Neo4j as available. The smoke command
compiles a repository-authored synthetic bilingual CV twice with
`-no-shell-escape`; it persists no compiler log or user data.

## Downloads and recovery

- The source endpoint downloads the exact selected immutable `.tex` artifact.
- The PDF endpoint previews or downloads the exact selected immutable PDF. A
  read never recompiles on demand.
- `TAILORING_PARENT_CONFLICT` leaves the local draft intact. Reload the latest
  parent, then reapply the draft before saving again.
- `TAILORING_GROUNDING_FAILED` and `TAILORING_COMPILE_FAILED` create no version
  and preserve the draft and previous PDF.
- Deleting a saved Job preserves existing derivative artifacts and its bounded
  label. New JD-based work requires another selected scorable Job.
- Session deletion removes only that session's runs, checkpoints, metadata, and
  UUID-scoped artifacts. A partial failure remains retryable.
- Profile deletion warns about and removes all owned tailored-CV sessions and
  artifacts through the profile deletion coordinator.

Stable safe codes are:

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

Record only the code, HTTP status, command exit code, and a sanitized summary.
Never record raw CV/JD text, contact values, prompts, provider payloads, TeX
source, compiler output, storage paths, checkpoints, credentials, or complete
container logs.
