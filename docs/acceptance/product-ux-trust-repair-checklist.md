# Product UX and Trust Repair Acceptance Checklist

Use synthetic CV and job data only. Record visible outcomes and safe error summaries; never copy identifiers, provider payloads, private paths, source-document content, secrets, or backend logs into this file.

## Workspace and navigation

- [x] Browser Back and Forward restored Profile A and Profile B with their own active CV, role, and conversation history. The inactive profile's content was absent after each restoration.
- [x] The product navigation exposed exactly **Overview**, **Saved Jobs**, and **Tailored CVs**.
- [x] A newly saved synthetic job produced clean assistant narration with no legacy identifier marker.
- [x] Saved Jobs used display labels and a human-readable **Why this score** explanation; no UUID prefix, raw score key, component weight, or internal unavailable label was visible.

## CV Manager and profile review

- [x] **Manage CVs** showed only server-projected actions. Profile-owned rows offered preview, download, re-extract, and activation as appropriate, and did not expose **Delete CV**.
- [x] Direct re-extraction visibly progressed through validation and extraction into a review of synthetic skill additions/removals.
- [x] **Discard review** closed the review without changing the approved profile.
- [x] A safe temporary-unavailable state exposed **Retry**; retry resumed after service recovery.
- [x] **Save profile** closed the manager and returned focus. The visible chat history and conversation list remained unchanged throughout re-extraction.
- [x] Profile deletion opened a confirmation explaining that the owned CV, profile data, evaluations, conversations, tailored sessions, and artifacts would be removed. The destructive label was **Delete profile and all data**; acceptance cancelled without deletion.

## Saved jobs and tailored CVs

- [x] A synthetic saved job created a ready tailored-CV session outside chat. Returning to chat preserved the prior conversation.
- [x] An unchanged AI request displayed **AI found no source-supported changes to apply.** and remained on Version 1.
- [x] Restoring the manual draft to its saved content displayed **There are no changes to save.** and remained on Version 1.
- [x] A safe grounding failure preserved the draft and exposed **Focus field**, **View source**, **Undo change**, and **Try again** without an internal path or code.
- [x] **Focus field** focused the exact invalid native field and exposed its safe accessible error description.
- [x] **View source** opened and focused the named evidence region on the first activation. **Undo change** remained field-scoped. **Try again** reopened the AI dialog with the prior synthetic instruction and did not submit automatically.
- [x] The unsupported synthetic draft text was restored to its source-supported value before handoff.
- [x] The embedded PDF visibly rendered **Professional Experience**, **Skills**, **Projects**, and **Education** once each, without repeated headings.
- [x] **Preview PDF**, **Download PDF**, and **Advanced → Download LaTeX source** were visible and activated while JobAgent stayed open. The browser runner emitted no download event, so this records control activation only and does not claim a filesystem download.

## Copy, privacy, and accessibility

- [x] Retained product chrome was English, including conversation dates and tailored-CV page counts. Source CV/job text and skill names were not treated as product chrome.
- [x] No UUID prefix, legacy saved-job marker, raw score internals, technical activity name/code/timing, or technical navigation label was visible.
- [x] Narrow layout used labeled **Content** and **Preview** tabs, one visible scroll owner, full-viewport Navigation/CV Manager drawers, named dialogs, initial dialog focus, Escape dismissal, and trigger-focus restoration.
- [x] Desktop layout used two visible scroll owners, one for **Content** and one for **Preview**, while the document body did not scroll. Editor mode reduced the product sidebar to its rail and restored the prior destination afterward.
- [x] Polite live regions announced re-extraction progress, safe errors, and no-change outcomes.
- [x] With reduced motion emulated, the tailored PDF frame matched the preference and had no transition; emulation was cleared afterward.
- [x] The explicit 1440×900 desktop viewport was reset to the browser's default narrow viewport after acceptance.

## Browser-runner diagnostic

The in-app browser's Enter/Space dispatch focused some Astryx/native button-like controls without activating them, while visible clicks activated the same controls and automated keyboard/focus tests passed. This matched the previously isolated browser-runner diagnostic; no separate product repair was inferred from it.

## Requirement-by-requirement audit

| Requirement | Evidence | Result |
| --- | --- | --- |
| Profile/conversation ownership and history restoration | Two synthetic profiles restored distinct CV and chat state through Back/Forward. | PASS |
| Direct re-extraction and review recovery | Progress, review, Discard, Retry, Save, focus return, and unchanged chat were visible. | PASS |
| Initial profile proposal visibility | The review showed approved and proposed synthetic profile values plus skill changes before Save. | PASS |
| Profile-review gate and prior-truth preservation | Approved values remained visible until Save; Discard preserved them and blocked conflicting profile work during review. | PASS |
| Server-owned CV action/deletion scope | Owned rows omitted CV deletion; profile deletion disclosed its full scope. | PASS |
| Three product destinations | Only Overview, Saved Jobs, and Tailored CVs were present. | PASS |
| Tailoring no-op contract and initial-version exception | AI and manual unchanged outcomes stayed on Version 1; initial generation still produced Version 1. | PASS |
| Safe grounding recovery | Field/source focus, Undo, and preserved Try again instruction were exercised. | PASS |
| PDF/LaTeX artifact controls | Preview and both download controls activated without navigating away. | PASS |
| Duplicate-heading suppression | Each visible PDF section heading appeared once. | PASS |
| Responsive/accessibility behavior | Narrow/desktop scroll, drawer, dialog, focus, live-region, and reduced-motion checks passed. | PASS |
| Human-readable labels, scores, and activity | Saved Job/session labels and score/activity explanations contained no raw identifier, weight, code, or timing. | PASS |
| English chrome and conversation titles | Conversation titles, dates, page counts, status, and actions were English while synthetic source text remained unchanged. | PASS |
| Explicit tailoring intent and durable success | Decision-path coverage required the tailoring tool for explicit intent; prose-only text produced no ToolResult or version. | PASS |
| Assistant-history privacy | Legacy saved-job markers were absent from new and retained assistant presentation. | PASS |
| Full gates and scope invariants | Backend/frontend suites, static checks, lint/typecheck/build, and diff checks passed with no migration, dependency, secret/runtime, backend-observability, or provider-payload change. | PASS |

## Automated evidence

- Review gate: the user-approved manual substitute and fresh spec review approved the privacy repair. The quality review's sole test-coverage finding was resolved with four malformed-marker regressions; the focused privacy/navigation suite then passed 34 of 34 tests with typecheck clean.
- Backend: 1,683 tests passed with 7 documented skips; Ruff passed; mypy passed for 177 source files.
- Frontend: 32 test files and 439 tests passed; lint and typecheck passed; production build passed with only the existing large-chunk warning.
- Browser acceptance: complete on the supported local stack with synthetic data only; viewport and reduced-motion emulation were reset.
