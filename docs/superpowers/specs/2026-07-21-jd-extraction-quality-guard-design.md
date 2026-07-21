# JD Extraction Quality Guard and Safe Re-extraction Design

## Status

Approved in conversation by the user on 2026-07-21. The approved change type is
`bugfix`: improve semantic reliability inside the existing `JobPostExtraction`
contract, expose the structured facts already returned by the backend, and add a
safe user-triggered repair path for retained JDs.

This design is the authority for the next incremental portfolio phase. It does
not itself authorize product implementation, task writing, or execution.

## Problem

The JD pipeline is structurally strict but semantically permissive. The provider
must return the configured JSON shape, yet valid-looking output can still lose an
explicit title, merge several technologies into one skill, place a mandatory
skill under `preferred_skills`, or attach evidence that is not grounded in the
source. The deterministic normalizer then treats a compound free-text label as
one unknown canonical key, and exact/seed-related matching cannot recover the
atomic skills inside it.

The running local stack confirmed the impact: all six retained JDs were
`partial`, five lacked a title, 15 of 33 extracted skills were outside the seed
taxonomy, and ten labels were obvious compounds such as `Python, C/C++` or
`FastAPI/Flask/Django`. Existing tests prove schema, retry, persistence, and
scoring mechanics, but use provider fakes with already-correct semantic output.
They do not establish extraction accuracy on English/Vietnamese JD forms.

The saved-JD UI magnifies the problem. Its parser retains responsibilities,
required/preferred skills, experience bounds, confidence, and evidence, while
the detail view renders only basic metadata and raw source text. Users therefore
cannot inspect most of the structured result or repair a retained extraction.

## Goals

1. Preserve the current `JobPostExtraction` public field set and the locked
   `gpt-4o-mini` provider/model configuration.
2. Require source-grounded facts and atomic skill labels before an extraction is
   classified, embedded, persisted, synchronized, or scored.
3. Reuse the existing one-repair limit and deterministic `SkillNormalizer`
   rather than add another model, parser, or taxonomy owner.
4. Let a user safely re-extract one retained JD in place without changing its
   identity, raw source, or automatically evaluating it.
5. Render all useful fields already present in the saved-job detail contract.
6. Establish deterministic regression coverage plus a bounded live-provider
   synthetic acceptance check for semantic extraction quality.

## Non-goals

- No new generic JD section/document model.
- No fields for education, qualifications, benefits, languages, compensation,
  employment type, or hiring stages in this phase.
- No model comparison, model upgrade, scoring-weight change, or broad taxonomy
  expansion.
- No blind delimiter-based skill splitting.
- No automatic bulk re-extraction, background migration, or automatic
  evaluation after re-extraction.
- No persistence or display of provider prompts/responses beyond the existing
  validated extraction and bounded source/evidence contracts.

## Options considered

### A — Prompt-only correction

Strengthen the system prompt and leave the rest of the pipeline unchanged. This
is small, but still accepts semantically invalid output whenever it satisfies
the Pydantic shape. It does not provide an executable invariant or regression
boundary and cannot safely protect downstream matching.

### B — Guarded single-pass extraction (selected)

Keep the current structured provider call, strict schema, one provider retry,
and one repair attempt. Add a deterministic semantic guard between structured
output and normalization. The guard either accepts an output or returns bounded
issue codes that drive the one existing repair call. Only a fully accepted
result reaches normalization, quality classification, embedding, persistence,
and graph synchronization.

This option addresses the root cause without changing the stored extraction
shape or adding a second extraction system. It also supports a staged in-place
re-extraction path that preserves the previous truth on pre-commit failures.

### C — Document-first multi-pass JD extraction

Segment a JD into sections, extract batches, and consolidate them as the CV
pipeline does. This may help very long or layout-heavy JDs, but adds provider
calls, latency, intermediate models, and persistence/observability decisions
that the current JD schema cannot exploit. It is deliberately deferred until a
measured corpus demonstrates that guarded single-pass extraction is insufficient.

## Selected architecture

The canonical flow becomes:

```text
raw JD
→ strict structured provider output
→ deterministic source/atomicity guard
→ existing SkillNormalizer
→ deterministic JD quality classifier
→ existing versioned embedding builder/provider
→ SQLite source-of-truth write
→ existing Neo4j Job synchronization for scorable output
```

Responsibilities remain separated by module boundary:

- `jd_extraction.py` owns the prompt, structured provider invocation, retry, one
  repair, and orchestration of validation before normalization.
- A focused validation module owns pure source normalization, grounding checks,
  atomic-skill checks, and duplicate/cross-group checks. It has no provider,
  database, embedding, graph, logging, or UI behavior.
- `skill_normalization.py` remains the sole canonical identity, alias, category,
  and approved-relationship owner. The guard may inspect its approved taxonomy,
  but may not create aliases or relationships.
- `jd_ingestion.py` continues to own new/retry ingestion and uses the guarded
  extractor without a fork.
- A focused Job re-extraction service coordinates snapshot read, guarded
  extraction, quality, embedding, compare-and-swap persistence, and post-commit
  graph synchronization.
- The Job repository owns the atomic compare-and-swap replacement. It does not
  call providers or graph services.
- The saved-Job API and frontend own the explicit re-extraction command and its
  presentation state; they never accept replacement raw JD content.

No persistent draft table is introduced. Provider and embedding work occur
outside a transaction and the existing Job row is not moved into `processing`.
Until the final compare-and-swap succeeds, the current extraction remains the
only durable truth.

## Extraction prompt contract

The provider instructions must make the following rules explicit:

1. `title`, `company`, and `location` are extracted only when directly supported
   by the source; no inference from general role content.
2. Responsibilities are concise verbatim source facts, not rewritten marketing
   summaries.
3. Every `JobSkill.name` is one atomic capability or technology. Lists and
   alternatives such as `Python, FastAPI`, `FastAPI/Flask/Django`, and
   `Git/Docker/Kubernetes` become separate rows that may share the same evidence.
4. Technical names containing punctuation, including `C/C++`, `.NET`, `Node.js`,
   and `CI/CD`, remain single labels.
5. Mandatory or neutrally listed qualifications are required. A skill is
   preferred only when the source explicitly marks it optional, preferred,
   advantageous, or equivalent wording.
6. A canonical skill may occur at most once and never in both required and
   preferred groups.
7. Skill evidence is a short verbatim source snippet. The model does not produce
   aliases, canonical keys, categories, relationships, or `jd_quality`.

Repair instructions include only bounded issue codes and field paths. They must
not echo the raw JD, invalid provider payload, evidence bodies, or secrets into
logs or durable state. The complete raw JD is already present in the transient
provider messages used by the current extraction call.

## Deterministic quality guard

### Source normalization

Containment uses one pure comparison representation:

```text
Unicode NFKC → collapse whitespace → Unicode casefold
```

It does not remove punctuation or transliterate text. This preserves meaningful
technical tokens while tolerating layout and case differences.

### Grounding rules

- Every non-blank skill evidence snippet must occur in the normalized raw JD.
- Every non-blank responsibility must occur in the normalized raw JD.
- Non-null title, company, and location must occur in the normalized raw JD.
- Summary remains a model-authored concise synthesis and is not required to be a
  verbatim substring.
- Seniority, work mode, and experience bounds remain schema-constrained model
  facts in this phase; their English/Vietnamese accuracy is covered by golden
  and live acceptance cases rather than a second heuristic inference engine.

Failure to ground a guarded field rejects the whole attempt. The guard does not
drop only the failing field because silent partial acceptance would hide the
provider defect and could change quality/scoring without user visibility.

### Atomic-skill rules

An exact approved taxonomy display name or alias is atomic. An unknown label is
rejected as compound when either of these conditions holds:

- it contains two or more standalone approved skill names/aliases; or
- it contains an approved skill name/alias plus additional qualifier words and
  does not exactly resolve through the normalizer; or
- it uses an enumeration delimiter to join distinct skill-like terms.

The validator owns a small explicit punctuation-token exception set for
technical names such as `C/C++`, `.NET`, `Node.js`, and `CI/CD`. The exception
set prevents false splitting; it is not a second taxonomy and supplies no alias,
category, or relationship facts. Unknown atomic skills remain valid and receive
the normalizer's existing deterministic unknown key.

The guard never splits or rewrites a label. It reports the field path and issue
code, allowing the bounded provider repair to return supported atomic rows.

### Duplicate and requirement-group rules

After tentative normalization, canonical keys must be unique within each group
and disjoint across required/preferred groups. A conflict rejects the attempt;
the guard does not silently choose one group. The repair prompt restates the
mandatory/default-required and explicit-preference rule.

### Guard result

The pure validator returns either the accepted extraction or an ordered,
bounded list of stable issues. Issue reports contain only code, field path, and
safe structural metadata such as counts. They never contain raw source or
evidence text. A second invalid result after the existing one repair attempt
maps to `INVALID_STRUCTURED_OUTPUT`.

The internal issue vocabulary is exactly:

- `EVIDENCE_NOT_IN_SOURCE`
- `RESPONSIBILITY_NOT_IN_SOURCE`
- `METADATA_NOT_IN_SOURCE`
- `COMPOUND_SKILL_LABEL`
- `DUPLICATE_SKILL`
- `SKILL_GROUP_CONFLICT`

At most 20 ordered issues enter a repair instruction. Additional issue counts
may be reported as one safe integer; additional paths or source values are not
included.

## New-ingestion behavior

New text and URL ingestion retain the existing hash/deduplication and retry
branches. Only new or failed-retry processing invokes the guarded extractor.
An existing non-failed exact duplicate still returns without provider,
embedding, graph, or evaluation work.

Accepted `full` and `partial` results retain the current embedding and
post-commit graph behavior. Contact-only or otherwise insufficient source may
still produce a validated `unscorable` Job during ordinary ingestion; the
semantic guard validates truthfulness, while `jd_quality` continues to decide
scorability.

## Safe re-extraction contract

### Public command

Add `POST /api/jobs/{job_id}/reextract`. The request contains no raw JD,
extraction, embedding, quality, or evaluation fields. The server reloads the
exact retained Job and raw content by ID.

An HTTP 200 response validates as:

```text
ReextractJobResponse
- outcome: updated
- job: SavedJobListItem
- sync_ok: bool
- code: null | NEO4J_SYNC_FAILED
- rebuild_instruction: str | null
```

`sync_ok=true` requires `code=null` and `rebuild_instruction=null`.
Post-commit graph failure still returns HTTP 200 because SQLite replacement
succeeded; it requires `sync_ok=false`, `code=NEO4J_SYNC_FAILED`, and the
existing safe rebuild instruction. The frontend refreshes the returned Job and
shows a graph warning rather than presenting the extraction replacement as a
total failure.

Every pre-commit failure uses the existing safe HTTP error envelope
`detail={code, summary}` and returns no response model. Stable additions are
`JOB_REEXTRACT_CONFLICT` for compare-and-swap conflict and
`JD_SOURCE_NOT_RECOVERABLE` for missing retained source; existing provider,
embedding, `INVALID_STRUCTURED_OUTPUT`, `JOB_NOT_FOUND`, and
`JOB_NOT_SCORABLE` codes are reused. No raw source, extraction, provider payload,
embedding, prompt, or storage detail appears in either response shape.

The normal detail endpoint remains the owner of selected raw content and the
full validated extraction.

### Staged execution

1. Load the Job and capture its `updated_at` snapshot.
2. Require retained non-blank raw content; otherwise return a stable safe error.
3. Run guarded extraction, normalization, quality classification, and embedding
   outside a transaction without mutating the Job.
4. Accept a replacement only when the new quality is `full` or `partial`.
   `unscorable` never replaces an existing retained extraction.
5. Atomically update processing status, extraction, quality, embedding triplet,
   and `updated_at` only when the stored `updated_at` still equals the captured
   snapshot.
6. Preserve `job_id`, source type/URL, raw content/hash, and timestamps/identity
   fields not owned by the replacement transition.
7. After SQLite commit, synchronize the same Job identity to Neo4j using the
   existing idempotent Job sync path.

This permits repair of failed, unscorable, partial, or full retained rows when a
new scorable result is obtained. It never creates a second Job for the same raw
hash and never invokes evaluation.

### Evaluation currentness

A successful replacement changes the authoritative Job revision used by the
evaluation-context hash. Existing evaluations remain stored but project as
`stale`; no explicit delete and no automatic evaluation occur. Implementation
tests must prove the currentness derivation actually observes the replacement
revision rather than adding a second invalidation store.

### Failure semantics

- Provider, guard, normalization, quality, embedding, compare-and-swap, or
  SQLite failure leaves the durable Job and existing evaluation currentness
  unchanged.
- A concurrent snapshot mismatch returns a stable conflict and discards the
  completed candidate result; it never overwrites a newer Job revision.
- A new `unscorable` result is reported as not acceptable for replacement and
  leaves the prior row unchanged.
- A Neo4j failure after SQLite commit retains the new SQLite truth and returns
  `NEO4J_SYNC_FAILED` plus the existing rebuild instruction. It does not roll
  SQLite back to match a derived graph.
- Safe API errors do not expose raw JD, provider responses, SQL/Cypher details,
  storage paths, embeddings, or secrets.

## Saved-JD user experience

The selected detail view renders the existing extraction in four bounded areas:

1. Metadata: title, company, summary, seniority, experience range, location,
   work mode, and extraction confidence.
2. Responsibilities: an ordered list using backend order.
3. Required skills: canonical display labels, confidence, and expandable source
   evidence.
4. Preferred skills: the same presentation, kept visually distinct from
   required skills.

Evidence is collapsed by default to keep the sidebar usable. Empty lists render
a concise unavailable/none state rather than disappearing ambiguously. Raw
source remains in its existing bounded detail section.

The detail actions add **Re-extract JD** with a confirmation dialog that states:

- Job identity and retained raw JD are preserved.
- The existing extraction is preserved if pre-commit processing fails.
- A successful replacement makes an existing evaluation stale.
- Evaluation is not run automatically.

The action is disabled while the request is active. Success refreshes list and
detail from the server and shows the new currentness state. Failure keeps the
displayed extraction and presents the safe server error. The UI never performs
an optimistic extraction replacement.

## Test design

### Synthetic golden corpus

Add repository-owned synthetic English and Vietnamese fixtures with expected
facts/invariants for:

- one-line and multi-section JDs;
- explicit title/company/location;
- compound lists and alternatives (`Python, FastAPI`,
  `FastAPI/Flask/Django`, `Git/Docker/Kubernetes`);
- punctuation-bearing atomic names (`C/C++`, `.NET`, `Node.js`, `CI/CD`);
- mandatory, neutral, optional, and preferred wording;
- duplicated/cross-group skills;
- source-missing evidence and metadata;
- contact-only/insufficient unscorable content.

Fixtures contain no personal, production, or copied proprietary JD data.

### Unit tests

- Source comparison proves NFKC, whitespace collapse, and casefold behavior
  without punctuation stripping.
- Grounding accepts contained evidence/responsibilities/metadata and rejects
  missing source facts.
- Atomicity rejects compound/qualified taxonomy labels, preserves approved
  punctuation tokens, and accepts unknown atomic skills.
- Canonical duplicate and cross-group conflicts are deterministic and ordered.
- One invalid provider output triggers exactly one repair with sanitized issue
  metadata; a second invalid output returns `INVALID_STRUCTURED_OUTPUT`.
- Existing provider timeout/rate-limit hard caps and schema-repair limits remain
  unchanged.

### Integration tests

- New ingestion exercises the same guarded extractor for text and URL-acquired
  content while preserving exact dedupe behavior.
- Re-extraction success keeps Job/raw/source identity, replaces extraction and
  embedding, changes the revision, projects existing evaluation as stale, and
  never calls evaluation.
- Provider, validation, embedding, unscorable, transaction, and concurrency
  failures preserve the exact previous Job/evaluation state.
- Neo4j failure after commit returns the documented partial-success signal and
  leaves the new SQLite truth rebuildable.
- Graph sync replaces the same Job's metadata and required/preferred edges
  without deleting shared skills or unrelated Jobs.
- Saved-job API rejects client replacement bodies and returns bounded public
  response/error contracts.

### Frontend tests

- Detail parsing remains strict and all existing extraction fields render in
  their correct groups and backend order.
- Empty/partial extraction states remain usable.
- Re-extract confirmation copy, request lock, cancel, success refresh, stale
  evaluation projection, and failure preservation are covered.
- Raw JD and evidence are not copied into unrelated state, notifications,
  history, or logs.

### Live acceptance

Run a bounded, explicit diagnostic against the configured provider using only
the synthetic corpus. For each case, assert the expected title/metadata where
present, atomic skill identities, requirement group, grounded evidence, and
quality branch. This diagnostic is an acceptance command, not an ordinary
networked unit test or model benchmark.

Then use the browser to re-extract one retained synthetic JD. Verify the Job ID
and raw source remain stable, the detail renders the structured fields, an
existing evaluation becomes stale without an evaluate request, graph state
matches the accepted extraction, and no browser-console or sanitized-log leak
occurs.

## Verification gates

- Focused validator, extraction, normalization, quality, ingestion,
  re-extraction, saved-job API, graph, and frontend detail/action suites.
- Full backend Ruff, mypy, and pytest gates.
- Full frontend tests, lint, typecheck, and production build.
- Shared plan-structure validator and final changed-path/diff review.
- Docker rebuild/health and bounded browser/provider acceptance using synthetic
  content only.

Passing structural tests alone is not accepted as proof of semantic quality;
the synthetic live-provider diagnostic is mandatory release evidence for this
phase.

## Master and portfolio impact

This change requires an explicit Master amendment because it adds a public
saved-Job command/response and changes the documented JD extraction workflow.
The amendment must preserve the existing stored `JobPostExtraction` field set,
model/embedding configuration, quality vocabulary, SQLite source-of-truth rule,
and explicit-only evaluation contract while adding:

- deterministic guarded extraction and bounded repair semantics;
- safe in-place re-extraction with compare-and-swap preservation;
- `POST /api/jobs/{job_id}/reextract` and its bounded response/failure contract;
- complete saved-detail rendering of existing extraction fields; and
- mandatory synthetic semantic-quality acceptance evidence.

The next incremental portfolio phase is `Plan_15.md`. Under the
`incremental-plan-creator` contract, Plan 14's historical completion content is
preserved but its terminal `## Completion Contract` must become a normal handoff
with `Plan_15.md` as the next consumer. No earlier plan is repartitioned.

## Expected ownership boundaries

Likely product/test owners are bounded to:

- `backend/app/services/jd_extraction.py`
- a focused deterministic JD extraction validation module
- `backend/app/services/jd_ingestion.py`
- a focused Job re-extraction service
- `backend/app/repositories/jobs.py`
- `backend/app/services/saved_jobs.py`
- `backend/app/api/jobs.py`
- existing Job/graph/evaluation schemas and tests only where the public response
  or revision-currentness contract requires it
- `frontend/src/features/jobs/` detail, API, state, dialog, and focused tests
- synthetic fixtures and one bounded provider diagnostic

No unrelated Agent graph, CV extraction, profile, scoring formula, deployment,
or dependency refactor belongs to this change.

## Self-review

- The selected approach fixes the semantic acceptance boundary rather than
  masking bad extraction in matching or UI.
- The existing extraction schema, provider retry/repair caps, normalizer,
  embedding representation, quality owner, and SQLite/Neo4j authority order are
  reused.
- Compound detection never becomes a blind string splitter, and punctuation
  exceptions do not become a second taxonomy.
- Re-extraction cannot silently replace raw source, create a duplicate Job,
  overwrite a concurrent revision, or auto-evaluate.
- Pre-commit failures preserve the prior durable result; post-commit graph
  failure remains an explicit rebuildable derived-state failure.
- Scope is executable as one incremental phase and contains no placeholder,
  model-selection project, schema expansion, or speculative bulk migration.
