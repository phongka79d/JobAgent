# Passive `save_job` Tool-Call Repair Design

**Date:** 2026-07-19

**Status:** Approved by user for implementation (option B)

## Problem

When a durable user message is recognized as a passive pasted job description,
the model can emit a malformed `save_job` call containing both a non-empty
`text` argument and `source="current_message"`. The strict `SaveJobInput`
contract correctly rejects that call, but the passive-JD decision branch lets
the malformed call reach `ToolNode`, producing `INVALID_JOB_INPUT` instead of a
confirmation card.

The provider-visible function schema intentionally exposes optional fields and
does not encode the cross-field one-of constraint. The graph therefore remains
the right deterministic boundary: it must validate the complete call before
dispatching it.

## Goals and non-goals

Goals:

1. Ensure every passive-JD decision dispatched to `ToolNode` is exactly one
   valid `save_job(source="current_message", preview?)` call.
2. Treat an invalid first decision, whether plain text or malformed tool call,
   as one bounded repair opportunity.
3. Preserve the existing truthful fallback when the repair is not a sole valid
   current-message call.
4. Reuse `SaveJobInput` as the single source of truth for source exclusivity,
   preview validation, and strict extra-field rejection.
5. Leave direct URL/text saves, named `save_job` handling, opt-out precedence,
   interrupt/resume behavior, and frontend rendering unchanged.

Non-goals:

- Do not silently discard `text` or `url` from a malformed call.
- Do not redesign the provider JSON schema or add a second tool.
- Do not change the persisted current-message source or ingestion path.

## Design

### Validation boundary

Extend the existing `_is_sole_current_message_save_job_call` predicate in
`backend/app/agent/graph.py` so it validates the call's argument dictionary
with `SaveJobInput.model_validate`. It returns true only when:

- the assistant message has exactly one tool call named `save_job`;
- the validated input has `source="current_message"`;
- no URL or non-empty text is present; and
- any preview is valid under the existing bounded preview model.

Invalid arguments, malformed preview data, unknown fields, and mixed source
modes all return false without invoking the tool.

### One bounded repair

For an obvious passive JD, the decision node will validate the model's first
response regardless of whether it contains tool calls. A valid source-only call
continues unchanged. Any other response (plain text, another tool, empty args,
URL/text source, or mixed sources) is discarded and receives exactly one repair
instruction requiring the sole current-message `save_job` call. The repaired
response is validated by the same predicate. If it is still invalid, the node
returns `PASSIVE_JD_NO_CONFIRMATION_TEXT` and emits no tool call.

This keeps malformed calls out of `ToolNode`, avoids hidden data rewriting, and
preserves the existing one-repair loop bound.

### Data flow

```text
model response
    -> passive-JD source-only validator (SaveJobInput)
       -> valid: ToolNode -> current-message interrupt
       -> invalid: one repair model call
          -> valid: ToolNode -> current-message interrupt
          -> invalid: truthful no-confirmation response
```

Direct URL/text and explicit named-tool branches retain their current routing.

## Tests and acceptance

Add graph regression coverage in
`backend/tests/unit/test_agent_graph.py` for:

1. A passive JD whose first response contains both `text` and
   `source="current_message"`: exactly one repair is requested, only the
   repaired source-only call reaches the tool, and the resulting ToolResult is
   projected normally.
2. A passive JD whose repair also contains mixed sources: no tool executes and
   the fixed no-confirmation text is returned.
3. Existing valid first-call and plain-text-repair tests continue to pass.

The focused graph test file and the related job-save contract/integration
tests must pass. The full backend test suite must then pass before completion.

## Risks and mitigations

- **Extra model invocation:** Only malformed passive-JD decisions incur the
  existing single repair call; valid calls remain one invocation.
- **Behavioral drift:** The validator is reused rather than duplicated, and
  direct URL/text branches are not changed.
- **False confirmation:** A repair that cannot produce a strict source-only
  call is refused, never normalized or ingested.
