# Observability Sidebar UI Refresh Design

- **Status:** Visual design approved; implementation pending
- **Baseline:** Plan 8 implementation at commit `508cbec`
- **Scope:** Frontend-only UI refresh; existing observability API contracts remain authoritative

## Objective

Make the existing observability sidebar faster to scan and more useful during
repeated local work while leaving chat behavior, backend read models, and data
safety unchanged.

The approved direction is a compact, resizable inspector built on the existing
`AppShell` and `SideNav`. The five Plan 8 views remain: Overview, CV history,
LLM chunks, Neo4j graph, and Agent runs.

## Scope Boundaries

### In Scope

- Replace the wrapped button tab strip with a vertical Astryx `TabList`.
- Improve hierarchy in all five existing panels.
- Add Astryx-owned resize, collapse, and mobile-drawer behavior.
- Replace the semantic-list-first graph with an interactive SVG node-link graph.
- Let users pan, zoom, fit, select, and drag graph nodes.
- Standardize loading, empty, refresh, stale, and error states.
- Verify each surface in the browser at desktop and mobile widths.

### Out of Scope

- Replacing `AppShell` or moving chat into a new multi-pane shell.
- Redesigning the chat message list or composer.
- Changing backend schemas, endpoint behavior, pagination, caps, or redaction.
- Adding graph mutations, arbitrary Cypher, authentication, sharing, or tenancy.
- Upgrading Astryx as part of this change.
- Adding another UI component or icon library.

## Component Policy

The repository-pinned `@astryxdesign/core@0.1.4` is the only rendered UI
component system. Production controls, navigation, status, typography, layout,
tooltips, banners, and empty/loading states must use Astryx components and
tokens.

The graph is a domain visualization, not a second UI system. It uses React SVG
elements for nodes, edges, labels, and arrow markers. `d3-force` supplies only
the force simulation and `d3-zoom` supplies only the SVG viewport transform.
Both are non-visual interaction/layout engines. This intentionally supersedes
the original Plan 8 constraint against visualization dependencies.

Do not add Heroicons, Lucide, a canvas graph package, or a graph component kit.
Use Astryx semantic `Icon` names where they fit. Use familiar text glyphs inside
Astryx `IconButton` only where Astryx 0.1.4 has no matching semantic icon, and
always provide a specific label and tooltip.

## Shell And Navigation

The existing ownership stays intact:

- `App` owns `AppShell` and chat/sidebar composition.
- `CvSidebar` owns profile fetch/upload state and the outer `SideNav`.
- `ObservabilitySidebar` owns selected view, cached resources, and view routing.
- Each panel owns only presentation and interactions for its resource.

Configure `SideNav` with its built-in `resizable` and `collapsible` APIs:

| State | Contract |
|---|---|
| Expanded default | 420px wide |
| Resize range | 360px minimum, 560px maximum |
| Persistence | Astryx `autoSaveId` stores the chosen width |
| Collapsed | Astryx compact rail; no custom width implementation |
| Mobile | `AppShell` automatic mobile navigation below `md` (768px) |

The expanded sidebar contains a vertical `TabList` and a flexible panel region.
Tabs use concise labels and Astryx icons. The selected panel scrolls independently
without forcing the chat column wider.

The collapsed rail keeps icon-only tabs with accessible labels and Astryx
tooltips. Selecting a tab while collapsed selects that view and expands the
sidebar. `SideNavCollapseButton` owns the collapse control. A compact, visibly
labeled profile status remains in the footer; color is never the only signal.

On mobile, `AppShell` owns the toggle, backdrop, focus handling, Escape behavior,
and drawer lifecycle. The drawer uses Astryx's default 320px width capped at
85vw. Tabs show full labels vertically. Selecting a tab keeps the drawer open so
the user can inspect its content; close, Escape, or backdrop returns to the
unchanged chat and composer. Resize and desktop collapse controls are hidden in
the mobile rendering context.

## View Hierarchy

### Overview

Keep existing profile/upload behavior. Present profile state and active CV as a
compact `MetadataList`, followed by the existing Astryx `FileInput` and the
view/download command. Existing load and upload errors remain persistent Astryx
`Banner` messages.

### CV History

Use an edge-to-edge Astryx `List` with dividers instead of repeated bordered
cards. Each `ListItem` shows filename, lifecycle status, compact timestamp, and
availability. Selecting one item reveals its metadata and safe open/download
action without nesting an interactive target inside another interactive item.

### LLM Chunks

Use a compact `List` ordered by chunk ordinal. A row shows ordinal, preview,
character count, and token estimate. At most one chunk is expanded. Full text
keeps the existing preformatted, bounded scroll area and is fetched only on
explicit expansion.

### Agent Runs

Use a divided `List` optimized for status scanning. Every row shows abbreviated
run ID, visible status text plus `StatusDot`, timestamp, tool count, and duration
when available. At most one run is expanded.

Expanded details use `MetadataList` for safe identifiers/timestamps and a compact
vertical tool timeline for name, status, duration, safe summary, and safe error
code. Prompts, arguments, checkpoints, stack traces, and provider metadata remain
forbidden.

## Neo4j Graph

### Rendering

`GraphPanel` makes the graph canvas the primary view when a ready or stale
snapshot contains nodes. The canvas is responsive SVG with a stable minimum
height and a token-based surface. It renders:

- Candidate, Job, and Skill nodes as colored circles using Astryx theme tokens.
- A short label inside or immediately beside each node.
- Directed edges with SVG arrow markers.
- Allowlisted relationship labels on edges.
- A legend with visible type names; color alone never carries meaning.
- Truncation/freshness metadata exactly as returned by the API.

Before simulation, nodes are sorted by type and stable identity; edges are
sorted by relationship type, source identity, and target identity. The initial
force layout is therefore deterministic for the same snapshot. A
`ResizeObserver` updates viewport dimensions without discarding the user's
current pan, zoom, or pinned-node state. The initial ready render fits once;
subsequent data refreshes refit only when the graph identity changes.

Selected-node metadata is rendered as an unframed Astryx `MetadataList` adjacent
to or below the canvas. Its allowlist is exact: Candidate ID/revision; Job ID,
title, company, and revision; Skill canonical name. Edge details contain only
source, target, and the existing allowlisted relationship type.

### Interaction

- Dragging the canvas pans it.
- Wheel and pinch gestures zoom around the pointer/focal point.
- `Fit view` frames all currently positioned nodes without changing pins.
- Clicking or focusing a node exposes only safe metadata and marks it selected.
- Dragging a node updates it continuously and pins it at the drop position.
- Other nodes continue settling around a pinned node.
- `Reset layout` releases all manual pins and restarts the force simulation.
- Refresh reloads the bounded server snapshot; it never expands the graph client-side.

Pointer capture prevents a node drag from also panning the canvas. Node drag and
canvas pan remain distinct interaction states. Touch targets meet Astryx sizing
expectations. Reduced-motion mode shortens or disables animated settling while
preserving the final layout.

### Accessibility And Fallback

SVG nodes are keyboard-focusable and expose type plus safe display label. The
visual graph is never the only way to read the snapshot. An Astryx `Collapsible`
below the canvas contains the existing semantic node/edge lists, including
relationship direction and truncation status. The fallback remains usable when
SVG rendering or force initialization fails.

`unavailable` renders an error `Banner` and no current graph. `stale` keeps the
safe snapshot visible with a warning `Banner`; stale data is never presented as
fresh.

## Async And Refresh States

| State | Presentation |
|---|---|
| Initial load with known row shape | Astryx `Skeleton` rows matching final dimensions; no simultaneous spinner |
| Detail load with unknown height | One labeled Astryx `Spinner` in the detail region |
| Empty | Context-specific `EmptyState isCompact` with a clear next step |
| First-load error | Persistent error `Banner` with safe summary/code and Retry |
| Refresh with cached data | Keep cached data visible; only the refresh `IconButton` enters loading state |
| Refresh error with cached data | Keep cached data and add a non-destructive error `Banner` |

A failed request never erases previously loaded safe data. Panel headers and
content dimensions remain stable across state transitions.

## File Boundaries

Keep source files focused and preferably below 300 lines:

- `CvSidebar.tsx`: profile state, upload commands, and outer Astryx `SideNav`.
- `ObservabilitySidebar.tsx`: resource state integration and selected-panel routing.
- `ObservabilityTabList.tsx`: expanded/collapsed Astryx tab presentation only.
- Existing panel files: one resource view each.
- `GraphCanvas.tsx`: SVG rendering and event wiring only.
- `useGraphSimulation.ts`: force lifecycle, node pinning, and cleanup.
- `useGraphViewport.ts`: d3 zoom/pan/fit transform and resize integration.
- `GraphSemanticList.tsx`: accessible node/edge fallback.
- `graphPresentation.ts`: pure graph-to-display mapping and type styles.

Before adding any helper, search existing sidebar, graph, formatting, and status
utilities and reuse or refactor them. Do not duplicate API parsing, resource
state, date formatting, status mapping, or graph identity logic.

## Data Flow

The existing lazy-load/cache flow remains unchanged:

1. A tab selection updates sidebar-local state.
2. The resource loads only on first selection or explicit refresh.
3. The typed API parser remains the safety boundary.
4. A successful payload enters the existing cache.
5. Panels derive view models without mutating API data.
6. Graph hooks clone only the bounded node positions needed by the simulation.
7. Unmount and resource replacement stop simulations and detach zoom/resize listeners.

No UI state enters the chat SSE reducer or backend persistence.

## Verification

### Automated

- Preserve all existing observability API/parser and sidebar tests.
- Add tests for vertical tab keyboard navigation and collapsed-tab expansion.
- Add tests for SideNav resize configuration and mobile drawer content reuse.
- Add panel tests for Astryx list hierarchy and single expanded detail.
- Add graph tests for node/edge/label rendering, arrow direction, safe metadata,
  drag-to-pin, reset-to-release, fit transform, and semantic fallback.
- Test ready, stale, unavailable, truncated, empty, first-load error, and cached
  refresh-error states.
- Test simulation/listener cleanup on unmount and snapshot replacement.
- Run the full frontend test suite, lint, typecheck, and production build.

Avoid pixel-coordinate assertions for the force layout. Test invariants and
interaction state; visual geometry belongs in browser checks.

### Browser

Work one approved surface at a time and inspect it before proceeding:

1. Expanded sidebar and Overview hierarchy.
2. CV History and LLM Chunks.
3. Interactive graph, including node drag, pan, zoom, Fit, and Reset.
4. Agent Runs and tool timeline.
5. Collapsed rail and automatic expansion from a tab.
6. Mobile drawer at 390px width, including Escape/backdrop close and composer visibility.
7. Loading, empty, stale, unavailable, and cached refresh-error states.

At minimum verify 1440x900, 1024x768, and 390x844 viewports. Confirm no text
overflow, overlapping controls, blank SVG, console errors, trapped focus, or
chat composer regression.

## Acceptance Criteria

- The UI matches the approved compact-rail hierarchy without replacing the app shell.
- All rendered controls and layout primitives are Astryx 0.1.4.
- The graph is a visible node-link network with readable directed relationship labels.
- Users can drag and pin nodes, pan/zoom the canvas, fit the view, and reset layout.
- The semantic graph fallback remains available and complete within server caps.
- Sidebar resize, collapse, and mobile behavior are owned by Astryx.
- Existing privacy/redaction, lazy loading, caching, and chat behavior do not regress.
- Automated checks and incremental browser validation pass before completion.
