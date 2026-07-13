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

Later Phase 0 gates (pypdf, ShopAIKey, full dependency decision record) are intentionally omitted until their owning tasks complete. Do not treat omitted sections as placeholders for unfinished Astryx work.
