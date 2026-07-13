# Phase 0 Feasibility Report

## Runtime facts

| Fact | Value |
|---|---|
| Report timestamp (local) | 2026-07-13T12:21:30+07:00 |
| Node.js | v24.11.0 |
| npm | 11.6.1 |
| OS | Windows |
| Frontend package manager | npm (`package-lock.json`) |
| Pinned Astryx core | `@astryxdesign/core@0.1.4` |
| Pinned Astryx CLI | `@astryxdesign/cli@0.1.4` |
| Pinned Astryx theme | `@astryxdesign/theme-neutral@0.1.4` |

Lockfile resolution: `frontend/package-lock.json` packages `node_modules/@astryxdesign/core`, `node_modules/@astryxdesign/cli`, and `node_modules/@astryxdesign/theme-neutral` each resolve to **0.1.4**. `npm ci` reproduces this install.

## Initialization

| Step | Command / action | Result |
|---|---|---|
| Discover CLI | `Set-Location frontend; npx --yes @astryxdesign/cli --help` then local `npx astryx --help` after install | Documentation syntax is `astryx component [name]` (also listed under Commands) |
| Init agent docs | `Set-Location frontend; npx --yes @astryxdesign/cli init --features agents --agent codex` | Installed `frontend/AGENTS.md` with Astryx v0.1.4 agent section |
| Pin packages | Exact versions in `frontend/package.json` + lockfile | `@astryxdesign/core@0.1.4`, `@astryxdesign/cli@0.1.4`, `@astryxdesign/theme-neutral@0.1.4` |
| Minimal render | `frontend/src/main.tsx` public imports only | Production build exit 0; headless DOM confirms all required class roots |

Documentation command syntax recorded from `npx astryx --help`:

```text
component [options] [name]        List components or print component docs
```

Exact per-component documentation commands used for every matrix row (also listed in the matrix Exact CLI documentation command column):

```text
npx astryx component AppShell
npx astryx component ChatLayout
npx astryx component ChatComposer
npx astryx component ChatToolCalls
npx astryx component ChatMessage
npx astryx component ButtonGroup
npx astryx component Card
npx astryx component Collapsible
npx astryx component ProgressBar
```

Optional machine-readable form (same data, append `--json` to any command above), for example: `npx astryx component AppShell --json`.

## Astryx component matrix

All components are **direct** public exports of the same pinned package `@astryxdesign/core@0.1.4`. No alternate design system. No internal package paths. Chat family components share public import `@astryxdesign/core/Chat`.

| Component | Package / version | Exact CLI documentation command | Public import | Required props / callbacks (from CLI docs) | Direct / composed | Status |
|---|---|---|---|---|---|---|
| AppShell | `@astryxdesign/core@0.1.4` | `npx astryx component AppShell` | `import { AppShell } from '@astryxdesign/core/AppShell'` | No required props. Optional slots: `children`, `topNav`, `sideNav`, `mobileNav`, `banner`; layout: `contentPadding`, `height`, `variant`. No required callbacks. | Direct | PASS |
| ChatLayout | `@astryxdesign/core@0.1.4` | `npx astryx component ChatLayout` | `import { ChatLayout } from '@astryxdesign/core/Chat'` | Required: `children` (ReactNode), `composer` (ReactNode). Optional: `emptyState`, `scrollButton`, `scrollRef`. No required callbacks. | Direct | PASS |
| ChatComposer | `@astryxdesign/core@0.1.4` | `npx astryx component ChatComposer` | `import { ChatComposer } from '@astryxdesign/core/Chat'` | Required callback: `onSubmit: (value: string) => void`. Optional callbacks: `onStop`, `onChange`. Optional: `placeholder`, `value`, `isDisabled`, `status`, etc. | Direct | PASS |
| ChatToolCalls | `@astryxdesign/core@0.1.4` | `npx astryx component ChatToolCalls` | `import { ChatToolCalls } from '@astryxdesign/core/Chat'` | Required: `calls: ChatToolCallItem[]` (`name`, optional `status` of `pending \| running \| complete \| error`, `target`, `duration`, …). Optional callback: `onExpandedChange`. | Direct | PASS |
| ChatMessage | `@astryxdesign/core@0.1.4` | `npx astryx component ChatMessage` | `import { ChatMessage } from '@astryxdesign/core/Chat'` | Required: `sender: 'user' \| 'assistant' \| 'system'`, `children: ReactNode`. Optional: `avatar`, `name`, `metadata`, `density`. No required callbacks. | Direct (children may use documented same-package `ChatMessageBubble` from `@astryxdesign/core/Chat`) | PASS |
| ButtonGroup | `@astryxdesign/core@0.1.4` | `npx astryx component ButtonGroup` | `import { ButtonGroup } from '@astryxdesign/core/ButtonGroup'` | Required: `children` (Button/IconButton), `label` (aria-label string). Optional: `orientation`, `size`, `isDisabled`. No required callbacks. Companion `Button` from `@astryxdesign/core/Button` with required `label`. | Direct | PASS |
| Card | `@astryxdesign/core@0.1.4` | `npx astryx component Card` | `import { Card } from '@astryxdesign/core/Card'` | No required props. Optional: `children`, `padding`, `variant`, size props. No required callbacks. | Direct | PASS |
| Collapsible | `@astryxdesign/core@0.1.4` | `npx astryx component Collapsible` | `import { Collapsible } from '@astryxdesign/core/Collapsible'` | Required: `trigger: ReactNode`. Optional: `children`, `defaultIsOpen`, controlled `isOpen`, callback `onOpenChange: (isOpen: boolean) => void`, group `value`. | Direct | PASS |
| ProgressBar | `@astryxdesign/core@0.1.4` | `npx astryx component ProgressBar` | `import { ProgressBar } from '@astryxdesign/core/ProgressBar'` | Required: `label: string`. Optional: `value`, `max`, `hasValueLabel`, `isIndeterminate`, `variant`, `formatValueLabel`. No required callbacks. | Direct | PASS |

### Same-package composition notes

| Need | Documented composition (same pinned package) |
|---|---|
| Chat shell | `AppShell` → `ChatLayout` with `children={ChatMessageList…}` and `composer={ChatComposer…}` |
| Message body | `ChatMessage` + documented `ChatMessageBubble` children (both from `@astryxdesign/core/Chat`) |
| Tool activity | `ChatToolCalls` inside an assistant `ChatMessage` |
| Approval actions | `ButtonGroup` + `Button` children |
| Score details | `Card` → `Collapsible` → `ProgressBar` |

No component required a cross-package or undocumented composition. Every matrix row’s CLI command was re-run successfully after pinning (`ALL_COMPONENT_DOCS=PASS`).

## Astryx gate result

| Gate | Result | Evidence |
|---|---|---|
| Stable pin + lockfile | PASS | `@astryxdesign/core@0.1.4` / `@astryxdesign/cli@0.1.4` / `@astryxdesign/theme-neutral@0.1.4` in lockfile; `npm ci` exit 0 |
| Public imports only | PASS | `frontend/src/main.tsx` uses only documented `@astryxdesign/core/*` and theme CSS entrypoints |
| Component matrix complete | PASS | All nine required components direct + documented props/callbacks + exact CLI command |
| Minimal build | PASS | `npm run build` exit 0 |
| Minimal local render | PASS | `npm run dev -- --host 127.0.0.1` + headless DOM shows `astryx-app-shell`, chat layout/message/tool-calls/composer, card, collapsible, progressbar, button-group |

**ASTRYX_COMPATIBILITY=PASS**

---

## pypdf extraction gate

| Fact | Value |
|---|---|
| Exact pypdf version | `6.14.2` (pinned in `backend/pyproject.toml` as `pypdf==6.14.2`) |
| Diagnostic command | `python infrastructure/scripts/verify_pdf_extraction.py` |
| Fixture directory | `backend/tests/fixtures/cv/` |
| Aggregate threshold | At least **4 of 5** digital fixtures must pass the meaningful-text rule |
| Allowed digital failures | **none** (observed **5/5** digital PASS) |
| Image-only expectation | Must be classified `NO_EXTRACTABLE_TEXT` (must not be accepted) |
| OCR | **Never** imported, subprocessed, or called; pypdf digital text only |

### Meaningful-text rule (owned by `infrastructure/scripts/verify_pdf_extraction.py`)

After whitespace normalization (collapse runs of whitespace, strip), text is **meaningful** when:

1. Non-whitespace character count is **>= 80**, and
2. The lowercased text contains at least one **identity** marker (`email`, `phone`, `@`, `name`), one **experience** marker (`experience`, `engineer`, `developer`, `analyst`, `worked`, `senior`, `staff`, `platform`), and one **skills** marker (`skills`, `python`, `typescript`, `sql`, `react`, `docker`, `fastapi`).

A digital fixture **PASS**es when **either** pypdf normal or layout extraction yields meaningful text. Text that fails the rule is treated as non-extractable. The image-only fixture must fail the rule in both modes and is reported as `NO_EXTRACTABLE_TEXT`. No OCR fallback is permitted.

### Per-fixture outcomes

Measurements: page count; non-whitespace character count after whitespace-only normalization for **normal** and **layout** extraction modes.

| Fixture | Kind | Pages | Normal non-ws | Layout non-ws | Normal meaningful | Layout meaningful | Result |
|---|---|---:|---:|---:|---|---|---|
| `digital_cv_01.pdf` | digital (classic single-column) | 1 | 421 | 421 | yes | yes | PASS |
| `digital_cv_02.pdf` | digital (data/product hybrid) | 1 | 422 | 422 | yes | yes | PASS |
| `digital_cv_03.pdf` | digital (split header / compact body) | 1 | 330 | 330 | yes | yes | PASS |
| `digital_cv_04.pdf` | digital (multi-role bullets) | 1 | 534 | 534 | yes | yes | PASS |
| `digital_cv_05.pdf` | digital (skills-first) | 1 | 340 | 340 | yes | yes | PASS |
| `image_only_cv.pdf` | image-only (full-page RGB JPEG XObject 1240×1754, no text layer) | 1 | 0 | 0 | no | no | `NO_EXTRACTABLE_TEXT` |

All five digital fixtures use synthetic identities only (no real personal data). The image-only fixture is a single letter-size page (`MediaBox [0 0 612 792]`) whose content stream only paints `/Im0 Do` (no `BT`/`Tj`/`TJ` text operators). The embedded DeviceRGB JPEG is a **visibly representative synthetic CV page** (1240×1754 px at generation time): dark header with synthetic name/contact, SUMMARY / EXPERIENCE / SKILLS / EDUCATION sections drawn as pixels only (`Jordan SampleCandidate`, placeholder roles and skills). pypdf extracts empty text in both modes. No real personal data; no OCR path.

### Aggregate and gate result

| Metric | Value |
|---|---|
| Digital successes | **5/5** (threshold >= 4/5) |
| Allowed digital failure named | none |
| Image-only | `NO_EXTRACTABLE_TEXT` (rejected as required) |
| Diagnostic exit code | `0` |
| Final marker | `PYPDF_COMPATIBILITY=PASS` |

**PYPDF_COMPATIBILITY=PASS**

---

Later Phase 0 gates (ShopAIKey, full dependency decision record) are intentionally omitted until their owning tasks complete.
