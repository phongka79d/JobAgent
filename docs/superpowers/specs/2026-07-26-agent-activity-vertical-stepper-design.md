# Agent Activity Vertical Stepper Design

**Date:** 2026-07-26  
**Status:** Approved

## Goal

Make the Agent activity timeline easier to scan by giving it one rounded
Astryx card boundary, moving the disclosure chevron to the far edge, and
replacing standalone status dots with a vertically connected status stepper.

## Scope

This is a presentation-only frontend refinement. The durable activity schema,
history hydration, reducer state, SSE handling, labels, technical names,
durations, error codes, and run-state rules remain unchanged.

Modify only:

- `frontend/src/features/chat/components/AgentActivityTimeline.tsx`
- `frontend/src/features/chat/components/agent-activity.css`
- `frontend/src/test/agent-activity-timeline.test.tsx`

## Approved visual structure

### Shared card boundary

Wrap the complete timeline in an Astryx `Card` with `width="100%"`, the
default variant, and compact `padding={3}`. The card owns the theme-aware
background, border, padding, and container radius. Do not reproduce Card
styling in custom CSS.

The Astryx `Collapsible` remains the disclosure owner. Its root and trigger
fill the available card width so the built-in chevron sits at the far right.
The summary marker, summary text, and chevron share one centered header row.
The supporting `View activity` label aligns with the summary text column rather
than the marker column.

When no activities exist, render the same Card summary without a disclosure or
chevron.

### Collapsed state

The collapsed card shows only:

1. the aggregate run marker or spinner;
2. the existing backend-derived summary and step count;
3. the existing `View activity` supporting label;
4. the Astryx disclosure chevron at the far right.

The individual activity markers and dashed rail remain hidden until expanded.

### Expanded state

An Astryx `Divider` separates the trigger from the activity list. The list is
a vertical stepper with one fixed-width marker column and one content column.
Every row except the last draws a token-colored dashed vertical connector from
its marker toward the next row. The connector is decorative and never carries
state by color alone. Each row exposes a stable last-row data attribute so the
connector rule and its regression test do not depend on DOM position.

Friendly labels stay on the first line. Technical name, exact state, duration,
and safe error code stay on the supporting line in their existing order.

## Astryx component mapping

Use documented public Astryx components:

- `Card` for the outer rounded boundary;
- `Collapsible` for open/close state and chevron behavior;
- `Divider` between header and expanded content;
- `Icon` for terminal and warning markers;
- `Spinner` for active running state;
- `HStack`, `VStack`, and `Text` for layout and typography.

There is no Astryx timeline or vertical stepper component. Custom CSS is
limited to the two-column row structure, fixed marker alignment, full-width
disclosure, and dashed connector. All spacing, border, radius, and color values
must use Astryx design tokens; no raw visual constants are allowed.

## State marker mapping

| Activity state | Marker |
| --- | --- |
| `completed` | Astryx semantic success/check icon |
| `failed` | Astryx semantic error icon |
| `running` | Astryx small Spinner with an accessible running label |
| `pending` | Astryx clock icon in a secondary color |

Aggregate run markers use success for completed, error for failed, warning for
interrupted or disconnected, and an accent clock for a running run while the
stepper is expanded. While collapsed, an actively running run uses the single
visible Spinner. This avoids stacking an aggregate Spinner with the active
activity Spinner after expansion. The Collapsible therefore uses local
controlled open state only for presentation; reducer and durable run state
remain unchanged. Existing text remains the authoritative state label.

## Motion and accessibility

- Preserve `aria-live="polite"` and `aria-atomic="true"` on the summary.
- Preserve the Collapsible button's `aria-expanded` behavior and keyboard
  interaction.
- Give the single visible running Spinner an accessible label derived from the
  visible activity or run summary.
- Treat non-running icons and connector lines as decorative because adjacent
  text exposes the exact state.
- Preserve reduced-motion behavior. Do not introduce new custom animation;
  Astryx owns Spinner motion.
- The collapsed state must not expose hidden activity details to visual users.

## Verification

Update the focused component tests to prove:

1. the timeline renders inside one Astryx Card;
2. the disclosure defaults closed and spans the card width;
3. expanding reveals friendly labels, technical names, exact states, and the
   vertical stepper;
4. pending, running, completed, and failed activities plus aggregate
   warning/interrupted states use their approved Icon or Spinner treatment;
5. only non-final rows receive a dashed connector;
6. the running Spinner has an accessible label;
7. terminal states stop the existing summary shimmer;
8. no tool arguments, results, provider payloads, or raw CV content appear.

Run the focused timeline and chat-page tests, then frontend lint, typecheck,
build, and browser verification in the existing local Docker app.

## Non-goals

- No backend, migration, API, SSE, history, or reducer changes.
- No new dependency or custom icon package.
- No changes to assistant answer rendering, job cards, approval cards, or the
  composer.
- No replacement of Astryx Collapsible behavior or chevron.
