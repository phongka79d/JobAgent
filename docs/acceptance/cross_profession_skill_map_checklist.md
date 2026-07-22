# Cross-Profession Skill Map Checklist (Plan 16)

Synthetic-data-only acceptance procedure for profession-neutral CV/JD skill
extraction, exact SQLite/Neo4j relationship parity, and the selected-JD
compatibility map. This is not a benchmark or a task tracker. Do not record real
CV/JD text, local identifiers, provider payloads, prompts, screenshots, database
files, graph dumps, storage paths, or credentials.

## Candidate identity and safety

- Run every automated, Docker, diagnostic, and browser check on the same working
  tree candidate. Record only the commit or working-tree fingerprint, command
  outcome, safe status/error code, aggregate count, and UTC date.
- Use only repository-authored synthetic inputs. The finite live diagnostic owns
  exactly the six cases in
  `backend/tests/fixtures/skill_extraction_golden.json`.
- Never change `infrastructure/neo4j/skills_seed.yaml` to make a synthetic case
  pass. Unknown atomic labels must work without seed membership.
- A map read must never call evaluation, embedding, provider, graph sync, or graph
  rebuild. Do not repair SQLite JSON or Neo4j with direct edits.

## Automated and runtime gates

Run the Plan 16 focused suites, then the complete backend/frontend gates, plan
validator, diagnostic, Docker build, and health checks documented in `README.md`.
Acceptance requires all commands to exit zero on the same candidate. A missing
live-provider credential is a blocked diagnostic, not permission to weaken the
fixture or bypass the locked model.

The live diagnostic output may contain only:

- one approved synthetic case ID;
- `PASS|FAIL`;
- an aggregate skill count;
- a fixed safe code and final aggregate status.

It must not contain source/evidence text, exception text, provider responses,
prompts, keys, URLs with credentials, or runtime-store values.

## Browser procedure

Use the in-app browser at `http://localhost:5173` with the rebuilt three-service
Compose stack.

1. Through supported UI actions, approve one synthetic CV whose profession is
   absent from the production seed. Save or re-extract one synthetic JD from a
   different profession. Do not use a real local record for recorded evidence.
2. Select the saved JD and open the graph tab. Confirm the initial view is
   **Phù hợp CV–JD**, not the raw Neo4j canvas, and that the CV/JD anchors use
   source display labels rather than canonical keys.
3. Exercise all five count filters: **Khớp chính xác**, **Liên quan**,
   **Thiếu bắt buộc**, **Ưu tiên chưa có**, and **Kỹ năng bổ sung**. Counts must
   equal the visible backend-owned items; an empty filter has an explicit state.
4. Select representative rows and confirm separate CV and JD evidence is shown.
   Direct/related/missing/additional labels must agree with the API response.
   The default view must show no UUID, canonical key, raw relationship type, or
   unrelated global seed Skill.
5. Refresh while retaining safe cached data. Verify loading, empty, no-active-CV,
   no-selected-JD, stale/rebuild-required, unavailable, and request-error states
   are readable and keyboard accessible. A stale/unavailable response contains
   zero compatibility items and never claims readiness.
6. Switch to **Kỹ thuật**. Confirm the existing bounded canvas, semantic list,
   pan, zoom, fit, reset, truncation metadata, and raw technical identifiers are
   still available. Skill nodes use the backend `display_name` as their primary
   label; canonical keys remain technical metadata only.
7. Inspect network activity for the map flow. It may issue the read-only
   `GET /api/observability/skill-map?job_id=...`; it must not issue an evaluate,
   re-extract, sync, rebuild, embedding, or provider request. Confirm there are no
   relevant browser console errors.

## Existing-record rollout

Existing approved records are historical truth and are never silently rewritten.
Upgrade them only through supported actions, in this order:

1. In CV Manager, choose **Reprocess** or **Make active** for the intended CV,
   review the newly extracted draft, then explicitly **Save Profile**. Until that
   approval, the previous active profile remains authoritative.
2. For each retained JD that needs the new atomic extraction contract, choose
   **Re-extract JD** and confirm. The Job ID/raw source is preserved; a successful
   replacement changes its revision and prior evaluations become `stale` without
   an evaluation call.
3. If the selected map reports `NEO4J_REBUILD_REQUIRED`, restore Neo4j and run the
   documented provider-free rebuild command. Rebuild reads SQLite, does not modify
   it, and does not call the extraction provider.
4. Reload the selected map and inspect source labels/evidence. Only if a fresh
   score is wanted, explicitly choose **Evaluate** once; evaluation is never part
   of reprocess, re-extract, rebuild, or map loading.

The optional supplied-record regression may be exercised locally through these UI
actions, but its content, filename, hash, IDs, evidence, screenshots, and outputs
must remain uncommitted and absent from this checklist.

## Sanitized evidence record

Use append-only rows after an actual run; never pre-mark an unexecuted check PASS.

| Requirement | Evidence | Status | Date (UTC) |
|---|---|---|---|
| Full backend/frontend/static/build gates | Pending same-candidate execution | PENDING | — |
| Finite live cross-profession diagnostic | Pending configured-provider execution | PENDING | — |
| Docker build and all-component health | Pending candidate rebuild | PENDING | — |
| Default selected-JD map and five filters | Pending in-app browser observation | PENDING | — |
| Stale/unavailable withholding and no evaluate request | Pending controlled observation | PENDING | — |
| Technical graph regression and console cleanliness | Pending in-app browser observation | PENDING | — |
| Hardcode, scope, real-data, and secret audit | Pending final diff audit | PENDING | — |
