# CV profile and multi-conversation acceptance checklist

Status values: `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`. Evidence is sanitized:
IDs are abbreviated and no CV text, secrets, provider payloads, raw prompts,
storage paths, or database dumps are included.

## Run record

| Field | Value |
|---|---|
| Date | `2026-07-24` |
| Operator | Codex |
| Branch/SHA | `feat/cv-profile-multi-conversation` / `cc5f5d0` before this evidence update |
| Compose project | `jobagent-cv-profile-reset-smoke` |
| Backup decision recorded | PASS - disposable project only; no non-disposable volumes targeted |
| Final volume cleanup | PASS - warned exact-project cleanup removed the disposable containers, network, and volumes |

## Destructive reset safety gates

| Check | Status | Sanitized evidence |
|---|---|---|
| Warning before each `down -v --remove-orphans` | PASS | Warning emitted and exact project name hard-checked |
| Disposable project name verified exactly | PASS | `jobagent-cv-profile-reset-smoke` |
| Migration head is `0005_cv_profiles_multi_conversation` | PASS | Alembic reported the expected head |
| Pre-smoke profiles, conversations, and jobs are zero | PASS | Count-only check returned zero for each |
| Fresh retained-files volume has no prior files | PASS | Count-only check returned zero |
| Neo4j contains only static seed data before smoke data | PASS | Dynamic labels and edges were zero; static Skill/RELATED_TO seed remained |
| Compose services are exactly neo4j, backend, frontend | PASS | `config --services` returned the exact set |
| Backend health is available | PASS | SQLite, filesystem, and Neo4j reported available |
| Final warned volume deletion | PASS | Exact-project `down -v --remove-orphans` exited 0 |

## Browser acceptance matrix

| Scenario | Status | Sanitized evidence |
|---|---|---|
| Upload CV A | PASS | `new_pending`; profile `31a7abb0`, conversation `255928bb`; one extraction turn |
| Approve CV A | PASS | Approval promoted the same profile and conversation IDs |
| Failed exact-hash retry | PASS | `retry_pending`; profile `f82bf671`, conversation `b15fcbd6`; no duplicate rows |
| Request Changes | PASS | Correction stayed in the bootstrap conversation; stale approval defect repaired by `98cb3eb` and retested with a fresh draft |
| Pending discard | PASS | Pending setup was removed and the ready fallback restored |
| Upload while pending | PASS | Different-file upload remained disabled while setup was pending |
| Two ready CVs | PASS | Ready profiles rendered as `Ava Synthetic` and `Noah DemoCandidate` |
| Profile switch B -> A -> B | PASS | Only activation plus hydration requests occurred; no extraction/chat/provider request |
| Profile summaries | PASS | Location and bounded skill tags rendered for both ready profiles |
| Multiple chats | PASS | Distinct histories survived selection and reload |
| Conversation deletion cancel | PASS | Dialog cancel and Escape caused zero mutation and restored focus |
| Conversation deletion confirm | PASS | Confirm deleted the selected chat; deleting the last created and selected a replacement |
| Long conversation title | PASS | Overlap reproduced, repaired by `635d04c`, then selection and overflow deletion retested |
| Profile deletion | PASS | Deleting profile B fell back to A and preserved one global Saved Job |
| Pending data isolation | PASS | CV Manager, graph, and Saved Jobs showed only `Profile setup in progress` and no ready-profile detail |
| Dialog accessibility | PASS | Initial focus, Escape, and focus restoration passed |
| Mobile drawer | PASS | At 390x844 the drawer rendered profiles/conversations and Escape returned focus |
| Activity lock | PASS | Controls disabled during active runs; backend rejected discard while the run was active |
| Reload during extraction | PASS | Fresh retest: profile `e7293dc9`, conversation `2941b069`; reload produced `AGENT_EXECUTION_FAILED` and re-enabled Retry, Discard, and Upload within four seconds |

## Browser-found defects and repairs

| Defect | Repair | Verification |
|---|---|---|
| Concurrent proposal and commit could approve a stale draft | `98cb3eb` | Valid correction produced a fresh approval and saved successfully |
| Long title covered the selectable conversation row | `635d04c` | Desktop selection and overflow delete remained operable |
| Reload left a durable run in `running` | `5ff1912`, `4d556ef`, `e6b9789` | ASGI, callback-cancellation, durable chat-close regressions passed; real Chrome reload produced terminal failure and released the activity gate |
| Disconnected extraction left its attachment staged, so Retry raised an ownership alert | `cc5f5d0` | Profile `d7e9b9d2` became `extraction_failed`; exact-hash Retry preserved IDs, reached approval without the alert, and Save Profile promoted it to ready |

## Automated and runtime gates

| Gate | Status | Evidence |
|---|---|---|
| Backend focused SSE/runner Pytest | PASS | 28 tests passed after the disconnect repair |
| Backend focused Ruff | PASS | Changed production and test files passed |
| Backend focused Mypy | PASS | SSE, runner, and chat-turn services passed |
| Backend full Ruff | PASS | `app tests --no-cache` completed with no issues |
| Backend full Mypy | PASS | 153 source files completed with no issues |
| Backend full Pytest | PASS | Reached 100% with exit 0; 3 environment-dependent tests skipped |
| Frontend full Vitest | PASS | 35 files and 407 tests passed |
| Frontend ESLint | PASS | `eslint .` exited 0 |
| Frontend TypeScript | PASS | `tsc --noEmit` exited 0 |
| Frontend production build | PASS | 2,494 modules transformed; build exited 0 |
| Fresh Compose `up --build --wait` | PASS | All three disposable services healthy on `e6b9789` |
| Singleton ownership search | PASS | Runtime hits were schema/profile field names; `CONVERSATION_ID = "main"` remains only as the documented test-compatibility alias and has no runtime caller |
| `git diff --check` | PASS | Completed after browser evidence update |

## Browser evidence

| Evidence item | Result |
|---|---|
| Routes/statuses | Upload/extraction, activation/hydration, conversation mutation, deletion, and pending-isolation routes exercised successfully |
| Abbreviated IDs | Upload A `31a7abb0`/`255928bb`; retry `f82bf671`/`b15fcbd6`; reload regression `e7293dc9`/`2941b069`; disconnected-retry repair profile `d7e9b9d2` |
| Provider/scorer diagnostics | Profile switching and pending isolation issued no extraction, chat, evaluation, or scorer call |
| Screenshots | Inline synthetic-data captures recorded two ready profiles, the long-title defect, and the mobile drawer |
| Non-blocking warnings | Python/aiosqlite deprecations, Vite chunk advisory, and zero-count graph relationship notifications |
