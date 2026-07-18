# Full Functional Test Matrix

Fresh functional QA contract for the complete JobAgent product on the current
repository HEAD. This matrix consolidates and reuses the implemented coverage in
`local_release_checklist.md`, `manual_jd_checklist.md`,
`observability_sidebar_checklist.md`, `cv_manager_checklist.md`, and
`saved_jd_evaluation_checklist.md`.

## Scope

- Cover all tracked backend and frontend product behavior, migrations, public
  routes, service orchestration, local Compose runtime, and user-visible states.
- Use the complete backend unit/integration/E2E suites and frontend Vitest suite
  for internal branches that are unsafe or impractical to force through a live UI.
- Use only tracked synthetic CV fixtures and ephemeral synthetic JD text for live
  cases.
- Record only failures in `full_functional_failure_report.md`.
- Exclude security, penetration, authorization, injection, credential, secret-
  scanning, and abuse testing. Existing safe response shapes are checked only as
  functional API contracts.

## Execution Environments

| Environment | Purpose |
|---|---|
| Host backend | Full pytest, Ruff, and mypy gates with fake/disposable dependencies |
| Host frontend | Full Vitest, ESLint, TypeScript, and production build gates |
| Isolated Compose project | Real frontend, backend, SQLite/files, Neo4j, and configured provider flow |
| In-app browser | Desktop and narrow-viewport user interaction, visible errors, network failures, and console observations |

## Test Cases

### Runtime and full-suite gates

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| RT-001 | Compose configuration | CLI | Exactly `frontend`, `backend`, and `neo4j` configure successfully. |
| RT-002 | Backend startup and health | Compose/API | All three containers become healthy; `/api/health` reports overall, SQLite, filesystem, and Neo4j available. |
| RT-003 | Frontend startup | Browser/network | Shell and production JS/CSS assets load without a blank page or relevant console error. |
| RT-004 | Backend internal behavior | Full pytest | Every backend unit, integration, and E2E test passes; optional environment skips are identified. |
| RT-005 | Backend static contracts | Ruff/mypy | Product and test code pass lint; backend application passes type checking. |
| RT-006 | Frontend internal behavior | Full Vitest | Every frontend component, parser, state, transport, and interaction test passes. |
| RT-007 | Frontend static/build contracts | ESLint/tsc/Vite | Lint, typecheck, and production build complete successfully. |
| RT-008 | Provider compatibility | Diagnostic/live chat | Sanitized provider diagnostic passes and a normal general chat turn completes. |
| RT-009 | Persistence across restart | Compose/API/browser | Approved profile, chat history, saved Jobs, and current evaluation state rehydrate after backend restart. |
| RT-010 | Provider-free graph rebuild | Compose CLI/API | Choice-C rebuild completes from stored SQLite artifacts and graph reads return a consistent ready state. |

### Application shell, navigation, and responsive behavior

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| FE-001 | Application shell | Browser | CV/profile sidebar and chat page render together at desktop width. |
| FE-002 | Sidebar resize/layout | Browser/Vitest | Rail/sidebar/chat proportions remain usable; titles and actions do not overlap. |
| FE-003 | Sidebar collapse/expand | Browser | Collapse control updates expanded state; compact profile/CV status remains visible. |
| FE-004 | Tab navigation | Browser | Tabs appear in order: Overview, CV Manager, LLM chunks, Neo4j graph, Agent runs, JD đã lưu. |
| FE-005 | Keyboard tab navigation | Browser/Vitest | Tabs and action controls are keyboard reachable with visible focus and correct selected panel. |
| FE-006 | Narrow/mobile layout | Browser/Vitest | Sidebar uses the responsive drawer/topbar behavior without hiding or trapping the chat composer. |
| FE-007 | Cached refresh state | Browser/Vitest | Refresh controls do not erase successful list/detail content while refreshing or after a failed refresh. |
| FE-008 | Loading/empty/error panels | Browser/Vitest | Each sidebar panel presents a distinct truthful loading, empty, and error state. |

### Chat, SSE, history, and tool activity

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| CHAT-001 | Empty conversation | Browser | Initial empty state and enabled composer are visible. |
| CHAT-002 | General conversation | Browser/API | Greeting streams to completion without unnecessary tool activity. |
| CHAT-003 | SSE lifecycle | Pytest/Vitest/live | Run, assistant, tool, text, interrupt, completion, and failure events preserve documented order and status vocabulary. |
| CHAT-004 | Composer lock | Browser | Composer and PDF controls disable while connecting/streaming and re-enable after terminal completion. |
| CHAT-005 | Tool activity | Browser | Friendly tool name, pending/running/completed/failed state, duration, and short outcome render once. |
| CHAT-006 | Event deduplication | Vitest | Repeated event IDs do not duplicate text, tools, cards, or terminal state. |
| CHAT-007 | Stream failure | Vitest/live observation | Failure is visible and never displayed as completed. |
| CHAT-008 | Disconnect behavior | Vitest/live observation | Disconnect remains nonterminal; running tools are not falsely marked completed. |
| CHAT-009 | Durable history hydration | Browser/API | Refresh reloads messages, runs, tools, approval cards, saved-job cards, and match cards exactly once. |
| CHAT-010 | Older history pagination | API/Vitest | Opaque cursor loads older messages in chronological order without duplicates. |
| CHAT-011 | Rapid terminal resume | Pytest/Vitest | Repeated resume attempts do not repeat tools or side effects. |
| CHAT-012 | Controlled tool-loop limit | Pytest | Loop overflow ends with the stable controlled failure rather than hanging. |

### CV upload, extraction, profile, and approval

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| CV-001 | Sidebar PDF upload | Browser | Valid synthetic digital PDF uploads once and starts the ID-only extraction turn. |
| CV-002 | Composer PDF attachment | Browser | Valid PDF becomes one removable token; submission sends only the attachment ID. |
| CV-003 | Upload validation | Pytest/Vitest | Unsupported, oversized, image-only/no-text, malformed, or excessive-page files fail with the documented functional error. |
| CV-004 | Duplicate CV identity | Pytest/live | Same file returns the existing eligible attachment outcome without creating a second identity. |
| CV-005 | Document-first extraction | Pytest/live | Every ordered section is extracted before profile projection; unknown headings are retained. |
| CV-006 | Atomic draft publication | Pytest | Failed parsing/extraction/consolidation publishes no partial chunks/document/profile draft. |
| CV-007 | Approval card | Browser | Draft renders one concise card with Save Profile and Request Changes. |
| CV-008 | Approval interaction lock | Browser | New turns and uploads remain blocked while approval is pending. |
| CV-009 | Request Changes | Browser/API | Original run completes, draft remains, active profile is unchanged, and composer regains focus. |
| CV-010 | Save Profile | Browser/API | Draft becomes approved active profile, pending draft clears, and sidebar refreshes. |
| CV-011 | Rapid approval clicks | Browser/Vitest | First action wins; buttons disable and only one resume request is sent. |
| CV-012 | Approved replacement | Browser/API | New approved CV becomes the sole active CV and previous active CV becomes archived. |
| CV-013 | Active profile read/download | Browser/API | Overview shows current title/name and View/download streams the active PDF. |
| CV-014 | Profile persistence | Restart/browser | Approved profile and active attachment remain after restart. |

### CV Manager and bounded active-CV access

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| CVM-001 | CV history | Browser/API | CV Manager lists active, archived, staged, and failed rows with one active badge. |
| CVM-002 | Active action matrix | Browser | Active row offers Open and Re-extract only. |
| CVM-003 | Archived action matrix | Browser | Archived row offers Open, Make active, and Delete. |
| CVM-004 | Active re-extract | Browser/API | Re-extract uses the sole chat SSE path and does not change active selection before approval. |
| CVM-005 | Archived Make active | Browser/API | Reprocess produces approval; activation occurs only after Save Profile. |
| CVM-006 | Reprocess failure/request changes | Browser/API | Active CV/profile/graph remain unchanged and recovery guidance remains visible. |
| CVM-007 | Active delete guard | Browser/API | Active deletion is refused without changing any row. |
| CVM-008 | Non-active delete confirmation | Browser | Dialog names the CV and deletion scope; cancel performs no request. |
| CVM-009 | Complete non-active deletion | Browser/API/Pytest | Confirmed delete removes only the selected CV-owned records/file/checkpoints/graph branch and then removes the row. |
| CVM-010 | Partial deletion retry | Pytest/Vitest | Partial failure retains a retryable row/error; retry completes without false success. |
| CVM-011 | Post-delete selection/cache | Browser/Vitest | UI selects a safe remaining row and refreshes only affected CV/chunk/run/graph projections. |
| CVM-012 | Bounded active-CV section read | Chat/Pytest | Agent can read an active section within item/character caps. |
| CVM-013 | Bounded active-CV search | Chat/Pytest | Agent can search active content with deterministic cursor/cap behavior. |
| CVM-014 | Bounded active-CV chunk read | Chat/Pytest | Agent can read a selected active chunk; archived IDs and stale cursors are refused. |

### Observability sidebar

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| OBS-001 | Lazy panel loading | Browser/network | CV, chunk, graph, and run endpoints load only when their tab/selection requires them. |
| OBS-002 | Retained CV open | Browser/API | Available retained CV opens as PDF; unavailable file produces the documented error state. |
| OBS-003 | Chunk list | Browser/API | Selected attachment shows ordered bounded previews without loading every full chunk. |
| OBS-004 | Chunk detail expansion | Browser/API | Expanding one row fetches/displays only that ordinal; collapsing retains the list. |
| OBS-005 | Run history | Browser/API | Durable runs show state, duration, and concise tool summaries; rows expand/collapse correctly. |
| OBS-006 | Graph ready state | Browser/API | Candidate/Job/Skill/CV/section/entry nodes and supported directed edges render with counts/truncation metadata. |
| OBS-007 | Graph stale state | Browser/API/Vitest | Stale warning and semantic fallback remain usable without pretending the graph is current. |
| OBS-008 | Graph unavailable state | Pytest/Vitest | Unavailable graph returns/render a safe empty typed state rather than crashing the sidebar. |
| OBS-009 | Graph node selection | Browser | Keyboard/click selection exposes the node's display-safe metadata. |
| OBS-010 | Graph pan/zoom/fit/reset | Browser/Vitest | Controls work repeatedly without losing nodes, labels, or viewport bounds. |
| OBS-011 | Parallel edge/label layout | Vitest | Parallel relationships and external labels remain readable and stable. |
| OBS-012 | Request-order protection | Vitest | Older list/detail responses cannot overwrite a newer refresh or selection. |

### JD ingestion, matching, and result cards

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| JD-001 | Raw-text JD save | Chat/API | Valid synthetic JD persists, extracts, classifies, embeds when scorable, and syncs graph. |
| JD-002 | Public URL JD save | Chat/API | Supported public HTTP(S) URL is fetched and persists a processed or failed Job truthfully. |
| JD-003 | Exact JD duplicate | Chat/API/Pytest | Exact content returns the existing nonfailed Job without reprocessing or new identity. |
| JD-004 | Failed JD retry | Pytest | Same failed content retries the existing row and can reach processed state. |
| JD-005 | JD quality classes | Pytest/live | Representative full, partial, and unscorable inputs receive the correct class and embedding behavior. |
| JD-006 | Save-job card | Browser | Durable card shows concise processing/quality/outcome without duplicate rendering. |
| JD-007 | Match without active profile | Pytest/API | Matching returns the documented active-profile requirement before external scoring. |
| JD-008 | Top-N matching | Chat/API | Consistent graph returns backend-ordered results within the requested cap. |
| JD-009 | Match card | Browser | Title/company/location/work mode/score and source render; missing optional fields remain graceful. |
| JD-010 | Score breakdown | Browser | Expandable components, effective weights, quality multiplier, matched/related/missing skills agree with the result. |
| JD-011 | Exact-Job scoring | Pytest | Explicit evaluation scores the exact Job even when outside vector top 50 and reuses the shared formula/explanation path. |
| JD-012 | Neo4j unavailable/stale matching | Pytest/live API | Returns the documented unavailable/rebuild-required result with no partial ranking. |
| JD-013 | Provider/extraction failure | Pytest/live API | Durable failure remains visible and neither tool nor assistant claims a successful save/match. |
| JD-014 | Deterministic ordering/ties | Pytest/Vitest | Sorting and displayed order remain backend authoritative and stable across hydration. |

### Saved-JD library, evaluations, and zero-result recovery

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| SJD-001 | Empty saved-JD panel | Browser | Empty state appears with no phantom detail or action. |
| SJD-002 | Saved-JD list pagination | API/Pytest | Stable newest-first cursor pages, limit bounds, compact metadata, evaluation state, and latest score. |
| SJD-003 | Saved-JD selection/detail | Browser/API | Selecting one row loads validated source/extraction and latest persisted MatchResult. |
| SJD-004 | None evaluation action | Browser | None state shows `Đánh giá với CV`. |
| SJD-005 | Current evaluation action | Browser | Current state shows score/evidence and no redundant evaluate button. |
| SJD-006 | Stale evaluation action | Browser | Stale row/banner shows `Cần đánh giá lại` and `Đánh giá lại`. |
| SJD-007 | Explicit evaluate | Browser/API | New current context creates one evaluation and updates list/detail/graph projections. |
| SJD-008 | Same-context reuse | API/Pytest | Repeated evaluate returns reused and performs no repeat provider/graph/explanation work. |
| SJD-009 | Context invalidation | API/Pytest | Active CV/profile/preferences/matching revision change derives stale without automatic recomputation. |
| SJD-010 | Evaluation context race/change | Pytest | Uniqueness race reloads winner; mid-computation context change persists nothing and returns retryable failure. |
| SJD-011 | Saved-JD pending/error state | Browser/Vitest | Duplicate actions disable while pending; prior successful list/detail remain after error. |
| SJD-012 | Job delete confirmation | Browser | `Xoá JD` opens a dialog naming the Job; cancel preserves state. |
| SJD-013 | Complete Job deletion | Browser/API/Pytest | Graph-first delete removes exact Job/evaluations only; list/detail update and repeat returns not found. |
| SJD-014 | Post-delete selection | Browser/Vitest | A deterministic remaining Job is selected or the empty state appears. |
| SJD-015 | Zero-result card gate | Browser/Vitest | Exactly one recovery card appears only for successful `match_jobs` with `count=0`. |
| SJD-016 | Zero-result exact copy | Browser | Card shows `Chưa có kết quả đánh giá` and `Lưu JD & đánh giá lại` once. |
| SJD-017 | Durable source binding | Browser/API/Pytest | Recovery submits only its initiating durable user-message ID; unbound ID is rejected. |
| SJD-018 | Recovery pending dedupe | Browser/Vitest | CTA disables immediately and rapid activation sends one request. |
| SJD-019 | Recovery success | Browser | Created/reused result replaces recovery state with existing MatchCard and invalidates the saved-JD panel. |
| SJD-020 | Recovery unavailable/error | Browser/Vitest | Card remains with one truthful retry/resubmit hint and no success claim. |
| SJD-021 | Invalid zero-result controls | Vitest | Failed, malformed, non-match, and nonzero tool results never show the recovery CTA. |

### Public API and persistence contracts

| ID | Function | Method | Expected behavior |
|---|---|---|---|
| API-001 | Public route inventory | Pytest | Every documented health/profile/chat/CV/Job/observability route exists with its expected method. |
| API-002 | Cursor and limit validation | Pytest/API | History, Job, CV, chunk, and run pagination accept valid cursors/bounds and reject malformed/out-of-range inputs. |
| API-003 | Migration chain | Pytest | Empty and existing databases upgrade through `0004`; existing rows/checkpoints survive and singleton seeds remain valid. |
| API-004 | Evaluation schema/cascades | Pytest | One Job/context row is enforced; Job or non-active CV deletion cascades only owned evaluations. |
| API-005 | Transaction boundaries | Pytest | Provider, URL, graph, file, and SSE work never requires an open SQLite transaction. |
| API-006 | Tool replay/idempotency | Pytest | Re-entering one durable tool call returns its stored result without repeating side effects. |
| API-007 | Job deletion retry | Pytest/API | Graph failure preserves SQLite Job/evaluations; retry completes after graph recovery. |
| API-008 | CV deletion retry | Pytest/API | Partial cleanup retains retry state and resumes idempotently to complete absence. |

## Failure Evidence Rules

For each failure record: test ID, severity by functional impact, exact observable
symptom, expected behavior, reproducible steps or command, relevant frontend
console/network evidence, relevant backend log excerpt, and affected feature.
Do not include passing cases, security findings, secrets, raw CV/JD bodies,
provider transcripts, storage paths, SQL, or Cypher.
