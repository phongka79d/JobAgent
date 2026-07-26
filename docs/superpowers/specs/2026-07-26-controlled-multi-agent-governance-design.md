# Controlled Multi-Agent Governance Design

**Date:** 2026-07-26
**Status:** Approved
**Scope:** Remove JobAgent's global single-Agent/two-Agent ceiling while keeping every concrete Agent workflow bounded, reviewable, and coordinator-owned.

## 1. Context

The Master Plan historically locks JobAgent to one conversation Agent and rejects multi-agent handoffs. The approved CV-tailoring design adds one bounded CV Tailoring Agent, but its first draft treated two Agents as a permanent system-wide maximum. The user has now approved a broader rule: JobAgent may use multiple Agents when each one has a concrete use case and a controlled orchestration contract.

This amendment changes governance, not the current feature count. Plan 17 still implements only the existing Main Agent and the CV Tailoring Agent. No third Agent, generic orchestration framework, worker, queue, or service is added without a later approved use case.

## 2. Approved Policy

1. JobAgent has no global hard cap on the number of product Agents.
2. Every new Agent requires an approved use case, an owning coordinator, bounded inputs and outputs, privacy rules, a finite topology, retry/repair limits, durable lifecycle behavior, and verification evidence.
3. An Agent may delegate only through its workflow's coordinator. Provider-selected recursive spawning, unrestricted peer handoffs, and arbitrary Agent-to-Agent calls are not allowed.
4. Every orchestration graph must be finite and cycle-free. A coordinator owns child launch, parent-child identity, terminal truth, cancellation, recovery, and cleanup.
5. Child failure is durable and cannot be converted into parent success. User-visible success requires the exact child contract to have completed successfully.
6. Additional Agents remain YAGNI: a future plan may add one only when the approved workflow needs it. The platform does not pre-build a generic Agent mesh or generic run schema for hypothetical Agents.

## 3. Current Plan 17 Boundary

Plan 17 adds one CV Tailoring Agent beside the Main Agent. The Tailoring Agent remains a fixed graph with no `ToolNode`, peer delegation, recursive spawn, or dynamic registry. `TailoringCoordinator` remains the sole launch and lifecycle owner.

Plan 17 may therefore assert that its implemented topology contains Main Agent plus CV Tailoring Agent. It must not describe those two as the permanent maximum for JobAgent or reject future approved specialist Agents. Its `agent_runs.run_kind` values remain exactly `chat | cv_tailoring`; a future Agent must introduce its own explicit plan, migration, ownership checks, and tests instead of weakening the current XOR contract or adding a speculative generic type.

## 4. Agent Contract Required for Future Plans

Every future Agent proposal must define:

- a single business purpose and coordinator owner;
- provider-visible and server-only inputs, including excluded private context;
- strict structured output or tool boundary;
- a finite node/edge topology and cycle-prevention rule;
- parent/child run ownership and workspace-activity effects;
- retry, repair, timeout, cancellation, disconnect, and replay behavior;
- durable terminal status and safe error projection;
- cleanup and deletion ownership;
- topology, privacy, grounding, failure, and recovery tests.

An Agent cannot be added only to split code, simulate a team role, or increase apparent autonomy. Ordinary deterministic services remain services.

## 5. Data Flow and Failure Rules

A coordinator resolves authoritative server state, validates the parent and workspace gate, creates durable run ownership, then invokes a bounded specialist. The specialist receives only its allowlisted context and returns its declared contract. The coordinator validates the result, persists terminal truth, and exposes only safe output to the caller.

If a child times out, fails validation, exhausts its retry/repair budget, is cancelled, or disconnects before durable completion, the coordinator records failure or interruption according to that workflow. It does not silently retry through another Agent, switch models, widen context, or let the parent claim success.

## 6. Observability and Security

Every child run is traceable to its Agent kind, coordinator-owned resource, and optional valid parent. Activity labels remain bounded and safe. Prompts, source documents, contacts, provider payloads, secrets, filesystem paths, and internal traces are never copied into status events merely to improve observability.

Agent boundaries do not replace authorization, source grounding, schema validation, artifact safety, or transaction ownership. Each workflow must keep these deterministic controls outside the model.

## 7. Documentation Changes

- Master Plan Version 2.3 states the global controlled multi-agent policy and removes the permanent one/two-Agent ceiling.
- The CV-tailoring design states that Plan 17 adds one bounded Tailoring Agent but does not cap the whole project.
- Plan 17 and its implementation plan replace `exactly two Agents total` and `no third Agent` acceptance language with `no unapproved or unbounded Agent topology`.
- No product-code contract changes beyond the already approved Plan 17 Main/Tailoring topology are introduced by this governance amendment.

## 8. Acceptance Criteria

1. No current planning authority describes one or two Agents as JobAgent's permanent global maximum.
2. Plan 17 still implements only Main Agent plus the bounded CV Tailoring Agent and adds no speculative Agent framework.
3. Future Agents require an approved coordinator-owned, finite, cycle-free contract with explicit privacy, lifecycle, and tests.
4. Recursive model-driven spawn, peer handoff mesh, unlimited retries, hidden fallback Agents, workers, queues, and new services remain unauthorized.
5. Portfolio review confirms Master, Plan 17, the CV-tailoring design, and the implementation plan use the same policy.
