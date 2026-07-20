# Intent-Aware Pasted-JD Save Design

## Status

Approved in conversation by the user on 2026-07-20. This is an incremental
correction to the existing pasted-JD confirmation and Plan 13 repair contracts.

## Problem

The current passive-JD fallback uses a fixed five-line predicate. A real pasted
JD may arrive as one very large whitespace-separated paragraph. In that case the
LLM can still recognize the content and emit `save_job`, but the provider may
include both `text` and `source='current_message'` (and an empty placeholder
field). The strict runtime validator correctly rejects the mixed-source call,
and the graph has no general intent-aware repair path, so the user sees
`INVALID_JOB_INPUT` instead of the existing confirmation card.

The product requirement is semantic: a large message that is a JD should be
recognized as such regardless of the exact phrase used to request saving,
line-wrapping, or copy/paste formatting.

## User-facing contract

| User intent | Result |
| --- | --- |
| A pure pasted JD with no other request | Show **Lưu JD / Không lưu** confirmation |
| Explicitly asks to save a JD | Show the same confirmation before mutation |
| Asks to analyse, summarise, compare, or otherwise work on a JD without asking to save | Perform that request; do not open a save confirmation |
| Asks to analyse and save | Perform the requested answer and open save confirmation for the save part |
| Clearly opts out of saving | No confirmation and no save mutation |

Every save remains confirmation-gated. Cancellation and terminal replay retain
their existing no-mutation and idempotency guarantees.

## Options considered

### A — Broaden the line/marker heuristic

Remove the five-line requirement and accept long text containing enough JD
markers. This is small, but still makes formatting and keyword thresholds the
semantic owner. It can miss unusual JDs and can create false positives.

### B — Make the provider schema mutually exclusive

Expose a strict provider `oneOf` schema so the model cannot send mixed fields.
This addresses one malformed shape but does not decide whether a long message is
an analysis request or a save request, and provider compatibility is already a
release constraint.

### C — LLM-first intent with canonical source repair (selected)

Keep the LLM as the semantic intent owner. Strengthen the prompt with the
pure-paste versus analysis distinction. If the LLM emits a `save_job` intent for
a passive turn, the graph never forwards its raw `url`/`text`/`source` mixture;
it emits one canonical `{"source": "current_message"}` call, then uses the
existing interrupt confirmation. If the LLM answers without a tool on a large
message, make at most one bounded reconsideration using the same semantic rule;
the model may return a normal answer or a source-only call. No line-count or
exact save phrase is used as the semantic decision.

The existing strict `SaveJobInput` validator remains authoritative. The graph
does not silently ingest provider text or strip fields inside the runtime tool;
it discards malformed model arguments before `ToolNode` and constructs only the
approved current-message source call.

## Selected design

### Decision flow

1. Apply the existing clear opt-out precedence and preserve the direct sole-URL
   path. Preserve only the repository's exact technical `save_job` acceptance
   command as a legacy direct-text exception; natural-language save requests
   containing a pasted JD use current-message confirmation.
2. Send the complete durable user message to the normal LLM with explicit
   intent instructions: pure pasted JD means passive save confirmation;
   analysis-only requests must not call `save_job`.
3. For a passive turn, inspect the model response before `ToolNode`:
   - a sole `save_job` call is treated as positive save intent;
   - regardless of malformed optional fields, replace it with one canonical
     source-only current-message call;
   - a non-save response remains ordinary conversation.
4. When the first response has no tool call and the message has at least 300
   non-whitespace characters, make one bounded semantic reconsideration. This
   gate is skipped for a sole URL, a clear opt-out, and the legacy exact direct
   command. A valid source-only reconsideration enters confirmation; an
   ordinary-text reconsideration is returned as the final answer; an invalid
   tool response produces the fixed truthful no-confirmation result and never
   reaches `ToolNode`.
5. Validate the canonical call with the existing `SaveJobInput` path and enter
   the current confirmation interrupt. The source is always reloaded from the
   durable initiating message by `run_id`.

The fixed 300-non-whitespace “large message” check only decides whether the
bounded reconsideration is worth an extra model call. It is not a JD classifier
and does not use line count, exact Vietnamese phrases, or a growing marker list.

### Data and safety boundaries

- The public registry remains unchanged: one `save_job`, one Agent decision node,
  one `ToolNode`, and the existing loop limit.
- `SaveJobInput` continues to require exactly one source and remains the only
  runtime authority.
- Raw JD text, provider argument values, and prompts remain absent from repair
  logs, summaries, pending approval state, and frontend payloads.
- Opt-out wins before canonicalization. Analysis-only intent is protected by
  the prompt and a regression test; if the model emits an invalid save intent,
  the confirmation gate still prevents an unreviewed mutation.
- Direct URL and legacy exact-command text saves, deduplication, cancellation,
  evaluation behavior, and saved-job rendering remain unchanged.

## Testing and acceptance

Backend tests must prove:

1. The exact one-line, large MISA-like paste whose first model call contains
   mixed `text`/`source` arguments produces exactly one canonical source-only
   call and reaches the confirmation interrupt without ingestion side effects.
2. A pure large one-line JD with a plain first response receives at most one
   semantic reconsideration and then a source-only confirmation call.
3. A long JD analysis/summarisation request does not open save confirmation.
4. Opt-out, sole URL, explicit direct save, valid source-only calls, malformed
   repair, cancellation, and existing direct paths retain their current
   behavior.
5. Sanitized logs contain no raw JD, preview, prompt, URL, or provider payload.

Frontend/browser verification must paste the original one-line Vietnamese JD,
confirm that the card appears, choose **Không lưu** once, and verify no Job or
ingestion side effect occurs before or after cancellation. A separate save run
must verify the normal card/result and exact dedupe behavior.

## Scope and files

Expected product/test owners are limited to the existing owners:

- `backend/app/agent/graph.py` — intent gate, canonical source dispatch, one
  bounded reconsideration.
- `backend/app/agent/prompt.py` — explicit semantic save-versus-analysis rules.
- `backend/app/services/job_save_confirmation.py` — only if a coarse large-text
  helper is needed; the existing source resolver and opt-out owner remain.
- `backend/tests/unit/test_agent_graph.py` and prompt/confirmation tests — red,
  green, and regression coverage.
- Existing integration/browser evidence files only when required by the test
  contract.

No new endpoint, database migration, dependency, public tool, or frontend card
is introduced.

## Self-review

- No exact phrase or newline count is a semantic requirement.
- Confirmation remains mandatory, so a model false positive cannot silently
  mutate storage.
- Runtime exclusivity is preserved rather than weakened.
- The design reuses the existing graph, tool, interrupt, and source-ownership
  boundaries; no duplicate persistence path is proposed.
