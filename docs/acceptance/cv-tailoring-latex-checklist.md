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
| Branch/SHA | `feature/cv-tailoring-latex` (pre-commit) |
| Compose project | `NOT RUN` |
| Synthetic fixtures only | PASS |

## Automated gates

| Gate | Status | Sanitized evidence |
|---|---|---|
| Task 10 focused E2E/demo/health/compose/registry regression | PASS | Local synthetic Pytest completed: `test_cv_tailoring_flow`, `test_demo_flow`, health, compose-source, and exact-registry suites |
| Focused contact/schema/projection/guard tests | NOT RUN | Pending final gate |
| Focused Agent/coordinator/API/deletion/E2E tests | NOT RUN | Pending final gate |
| Backend Ruff | NOT RUN | Pending final gate |
| Backend Mypy | NOT RUN | Pending final gate |
| Backend full Pytest | NOT RUN | Pending final gate |
| Migration upgrade/downgrade/re-upgrade on disposable DB | NOT RUN | Never downgrade a configured user database |
| Frontend full Vitest | NOT RUN | Pending final gate |
| Frontend ESLint | NOT RUN | Pending final gate |
| Frontend TypeScript | NOT RUN | Pending final gate |
| Frontend production build | NOT RUN | Pending final gate |
| Plan portfolio validator | PASS | Plans 1-17 validated with no errors; only Plan 17 is terminal |
| `git diff --check` and scope/secret review | PASS | No whitespace errors; changed/untracked files are all within Task 10 allowlist and synthetic-only |

## Synthetic cross-layer matrix

| Scenario | Status | Sanitized evidence |
|---|---|---|
| Legacy profile parses with nullable contacts | PASS | Synthetic coordinator E2E projects an approved legacy header with all optional contacts absent |
| Explicit re-extraction/approval with GitHub present | PASS | Synthetic coordinator E2E renders the approved optional GitHub header |
| Second approved profile with GitHub absent | NOT RUN | |
| Selected `full` Job creates initial session | NOT RUN | |
| Selected `partial` Job creates initial session | NOT RUN | |
| Instruction-only Main-Agent tool creates initial session | PASS | Synthetic coordinator E2E created the initial session from a bounded instruction only |
| Tailoring Agent sees outline first and only selected section bodies later | PASS | Synthetic E2E captured provider messages and excluded an unrelated section body |
| Initial AI version is grounded and owns TeX plus PDF | PASS | Synthetic coordinator E2E completed the initial AI version and read both immutable artifacts |
| Manual edit creates an immutable child version | PASS | Synthetic E2E asserted ordered `ai`, `ai`, `user` version chain |
| Section-scoped AI edit receives exactly one section ID | PASS | Synthetic E2E scoped the later AI revision to `summary` only |
| Stale profile/CV/Job revisions block writes and preserve reads | PASS | Synthetic E2E made the profile stale, observed the safe block, and retained prior artifacts |
| CAS conflict preserves the draft and latest immutable version | PASS | Synthetic E2E rejected an old parent ID after version three |
| Saved Job deletion preserves existing downloads | NOT RUN | |
| Session deletion cancel performs zero mutation | NOT RUN | |
| Session deletion failure stays retryable | PASS | Synthetic E2E forced one artifact-cleanup failure, then deleted successfully on retry |
| Profile deletion cleans owned sessions and artifacts | NOT RUN | |
| `latex-cv-v1` escaping and PDF page metadata are exact | NOT RUN | Dedicated renderer/escaping gate not run in this Task 10 focused subset |
| Evaluations, matching, and Neo4j remain unchanged | NOT RUN | Dedicated cross-projection gate not run in this Task 10 focused subset |
| Main registry has exactly eight tools | PASS | Focused registry regression suite passed with the fixed eight-tool order |
| Reference-only sentinel is absent from prompts, results, SQLite, activities, errors, artifacts, and logs | PASS | Synthetic E2E asserted absence from captured prompts/events, ToolExecution/activity records, SQLite bytes, TeX, PDF-extracted text, and fake compiler output |

## Compose and compiler candidate

| Check | Status | Sanitized evidence |
|---|---|---|
| Services are exactly Neo4j/backend/frontend | NOT RUN | |
| Startup reaches migration `0007_add_cv_tailoring` before Uvicorn | NOT RUN | |
| Health reports all components available | NOT RUN | |
| Image-build compiler smoke passes | NOT RUN | |
| Running-container compiler smoke passes | NOT RUN | |
| Compiler runs two argv-only passes with `-no-shell-escape` | NOT RUN | |
| No fourth service, worker, queue, or runtime compile network | NOT RUN | |

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
