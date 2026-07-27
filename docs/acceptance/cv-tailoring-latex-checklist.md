# CV tailoring and fixed LaTeX acceptance checklist

Status values are `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`. Evidence must use
repository-authored synthetic profiles and Jobs. Do not record raw CV/JD text,
contact values, prompts, provider payloads, LaTeX/PDF bytes, server paths,
credentials, database dumps, or complete logs.

## Run record

| Field | Value |
|---|---|
| Date | `2026-07-27` |
| Operator | Local automated synthetic gate |
| Branch/SHA | `feature/cv-tailoring-latex` / `bbe45d7` |
| Compose project | Candidate project ran with temporary host-port override; standard host ports were occupied by an existing stack |
| Synthetic fixtures only | PASS |

## Automated gates

| Gate | Status | Sanitized evidence |
|---|---|---|
| Task 10 focused E2E/demo/health/compose/registry regression | PASS | Local synthetic Pytest completed: tailoring E2E, demo, health, compose-source, active-CV, Job, interrupt/resume, approval, chat, and agent-graph suites |
| Focused contact/schema/projection/guard tests | PASS | Plan 17 focused feature command completed with no failures |
| Focused Agent/coordinator/API/deletion/E2E tests | PASS | Plan 17 focused feature command completed with no failures |
| Backend Ruff | PASS | `ruff check app tests --no-cache` completed with no findings |
| Backend Mypy | PASS | `mypy app --no-incremental` completed with no issues in 172 source files |
| Backend full Pytest | PASS | `pytest -q` completed with no failures; existing FastAPI/SQLAlchemy warnings only |
| Migration upgrade/downgrade/re-upgrade on disposable DB | PASS | `tests/integration/test_migrations.py -q`: 11 passed |
| Frontend full Vitest | PASS | `npm test -- --run`: 41 files, 450 tests passed |
| Frontend ESLint | PASS | `npm run lint` completed successfully |
| Frontend TypeScript | PASS | `npm run typecheck` completed successfully |
| Frontend production build | PASS | `npm run build` completed; Vite emitted only the existing large-chunk advisory |
| Plan portfolio validator | PASS | Plans 1-17 validated with no errors; only Plan 17 is terminal |
| `git diff --check` and scope/secret review | PASS | No whitespace errors; review found only the Task 10 allowlist and synthetic test data. |

## Synthetic cross-layer matrix

| Scenario | Status | Sanitized evidence |
|---|---|---|
| Legacy profile parses with nullable contacts | PASS | Synthetic legacy JSON omits all optional-contact keys and `CandidateProfile` parses each as `None`. |
| Explicit re-extraction/approval with GitHub present | PASS | Synthetic E2E re-extracted a ready profile, reviewed its draft, and committed it; the approved GitHub value was then persisted. |
| Second approved profile with GitHub absent | PASS | A distinct synthetic profile was re-extracted, reviewed, and saved with no GitHub value. |
| Selected `full` Job creates initial session | PASS | Synthetic processed `full` Job created and completed an initial tailored-CV session. |
| Selected `partial` Job creates initial session | PASS | Synthetic processed `partial` Job created and completed an initial tailored-CV session. |
| Instruction-only Main-Agent tool creates initial session | PASS | The real `create_tailored_cv` Main-Agent tool was invoked with a durable run, profile state, and bounded instruction; its ToolResult identified the created session/version. |
| Tailoring Agent sees outline first and only selected section bodies later | PASS | Captured selection prompt contained the outline but no source body; the following rewrite prompt contained only the selected source body and excluded an unrelated body. |
| Initial AI version is grounded and owns TeX plus PDF | PASS | Synthetic coordinator E2E completed the initial AI version and read both immutable artifacts |
| Manual edit creates an immutable child version | PASS | Synthetic E2E asserted ordered `ai`, `ai`, `user` version chain |
| Section-scoped AI edit receives exactly one section ID | PASS | Synthetic E2E scoped the later AI revision to `summary` only |
| Stale profile/CV/Job revisions block writes and preserve reads | PASS | Separate profile, CV-document, and saved-Job revision changes each blocked a write while the existing immutable download remained readable. |
| CAS conflict preserves the draft and latest immutable version | PASS | A stale parent ID was rejected after the later AI and manual immutable versions; UI-local draft preservation is not claimed by this backend E2E. |
| Saved Job deletion preserves existing downloads | PASS | After real saved-Job deletion, the retained version's exact source and PDF downloads still matched their pre-delete bytes. |
| Session deletion cancel performs zero mutation | NOT RUN | Cancel is a frontend-only confirmation behavior and is not exercised by this backend E2E. |
| Session deletion failure stays retryable | PASS | Synthetic E2E forced one artifact-cleanup failure, then deleted successfully on retry |
| Profile deletion cleans owned sessions and artifacts | PASS | Profile deletion removed its tailored-CV session metadata and UUID-scoped artifacts after the session retry proof. |
| `latex-cv-v1` escaping and PDF page metadata are exact | PASS | Synthetic E2E asserted the fixed renderer's escaped source tokens and one-page PDF metadata for generated immutable artifacts. |
| Evaluations, matching, and Neo4j remain unchanged | PASS | Tailoring added no evaluations, did not write to an untouched fake graph, and retained the exact production registry containing the matching tool. |
| Main registry has exactly eight tools | PASS | Synthetic E2E asserted the exact eight-tool production order. |
| Reference-only sentinel is absent from prompts, results, SQLite, activities, errors, artifacts, and logs | PASS | Synthetic E2E asserted absence from captured prompts, ToolResult, SQLite JSON/bytes, activities/errors, TeX, PDF text, and captured application logs. The marker exists only in a local fake format-reference object. |

## Compose and compiler candidate

| Check | Status | Sanitized evidence |
|---|---|---|
| Services are exactly Neo4j/backend/frontend | PASS | `docker compose config --services` returned exactly `neo4j`, `backend`, `frontend` |
| Startup reaches migration `0007_add_cv_tailoring` before Uvicorn | PASS | Candidate backend reached healthy state after image `alembic upgrade head && exec uvicorn` startup path |
| Health reports all components available | PASS | Candidate `GET /api/health`: overall/sqlite/filesystem/neo4j all `available` |
| Image-build compiler smoke passes | PASS | `docker compose up --build` completed backend `cv_tailoring_smoke` after TeX installation |
| Running-container compiler smoke passes | PASS | Candidate `docker compose exec backend python -m app.services.cv_tailoring_smoke` exited 0 |
| Compiler runs two argv-only passes with `-no-shell-escape` | PASS | Real candidate smoke completed two compiler passes; unit argv/no-shell-escape tests passed |
| No fourth service, worker, queue, or runtime compile network | PASS | Compose service inventory remained three services; compiler runs inside backend |

## Browser acceptance

Record sanitized routes/statuses and screenshots only.

| Scenario | Status | Sanitized evidence |
|---|---|---|
| Selected-JD **Tạo CV theo JD** entry | NOT RUN | |
| Natural-language Main-Agent entry and **Mở CV editor** | NOT RUN | |
| GitHub-present and GitHub-absent header separators | NOT RUN | |
| Experience, Awards, and unknown headings stay in source order | NOT RUN | |
| Desktop 60/40 editor/PDF split | NOT RUN | |
| Mobile **Nội dung** / **Xem trước** tabs | NOT RUN | |
| Manual version and one-section AI version | NOT RUN | |
| Evidence disclosure shows only selected-version source text | NOT RUN | |
| `.tex` download and PDF preview/download | NOT RUN | |
| Two-page warning and page count | NOT RUN | |
| Stale state creates a new session from allowed current inputs | NOT RUN | |
| CAS, grounding, and compile recovery preserve local work/previous PDF | NOT RUN | |
| Saved Job deletion preserves old downloads | NOT RUN | |
| Session deletion cancel/confirm and focus restoration | NOT RUN | |
| Profile deletion warning includes derivative artifacts | NOT RUN | |
| Keyboard order, labels, live state, Escape, and reduced motion | NOT RUN | |
| No UUID primary label, raw template/source/JD, path, secret, overlap, console error, automatic evaluation, or tailoring Neo4j data | NOT RUN | |
