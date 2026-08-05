# Profile re-extraction operation acceptance evidence

Synthetic-data-only release evidence for `profile-reextract-operation`.

**Attempt:** `2026-08-02T03:32:00Z`
**Overall:** `FAILED`

| Case ID | Outcome | UTC | Artifact handle |
| --- | --- | --- | --- |
| migration-upgrade | PASS | 2026-08-02T03:32:00Z | clone-migration-smoke-a24 |
| downgrade-refusal | PASS | 2026-08-02T03:32:00Z | backend-pytest-a24 |
| duplicate-claim | PASS | 2026-08-02T03:32:00Z | backend-pytest-a24 |
| upload-race | PASS | 2026-08-02T03:32:00Z | backend-pytest-a24 |
| pool-cleanliness | PASS | 2026-08-02T03:32:00Z | backend-pytest-a24 |
| snapshot-sidecar-verify | PASS | 2026-08-02T03:32:00Z | verify-wal-shm-filter-a24 |
| clone-rehearsal | PASS | 2026-08-02T03:32:00Z | clone-migration-smoke-a24 |
| candidate-browser | FAIL | 2026-08-02T03:32:00Z | iab-running-lock-pass-reload-recovery-blocker-a24 |
| rollback | PASS | 2026-08-02T03:32:00Z | rollback-verify-graph-logs-a24 |

---

**Attempt:** `2026-08-05T04:25:26Z`
**Overall:** `PASS`

| Case ID | Outcome | UTC | Artifact handle |
| --- | --- | --- | --- |
| migration-upgrade | PASS | 2026-08-05T04:25:26Z | source-gates-20260805-pass |
| downgrade-refusal | PASS | 2026-08-05T04:25:26Z | backend-pytest-20260805-pass |
| duplicate-claim | PASS | 2026-08-05T04:25:26Z | backend-pytest-20260805-pass |
| upload-race | PASS | 2026-08-05T04:25:26Z | browser-409-review-action-20260805 |
| pool-cleanliness | PASS | 2026-08-05T04:25:26Z | backend-pytest-20260805-pass |
| snapshot-sidecar-verify | PASS | 2026-08-05T04:25:26Z | snapshot-contract-20260805-pass |
| clone-rehearsal | PASS | 2026-08-05T04:25:26Z | clone-smoke-20260805-pass |
| candidate-browser | PASS | 2026-08-05T04:25:26Z | browser-candidate-20260805-pass |
| browser-running-lock | PASS | 2026-08-05T04:25:26Z | browser-running-disabled-20260805 |
| browser-reload-operation | PASS | 2026-08-05T04:25:26Z | browser-exact-operation-recovery-20260805 |
| browser-stale-review | PASS | 2026-08-05T04:25:26Z | browser-stale-discard-20260805 |
| browser-retry | PASS | 2026-08-05T04:25:26Z | browser-interrupted-retry-20260805 |
| browser-approval | PASS | 2026-08-05T04:25:26Z | browser-review-approval-20260805 |
| browser-narrow-focus | PASS | 2026-08-05T04:25:26Z | browser-mobile-focus-20260805 |
| active-cv-lineage | PASS | 2026-08-05T04:25:26Z | browser-active-archived-lineage-20260805 |
| rollback | PASS | 2026-08-05T04:25:26Z | rollback-verified-20260805 |
