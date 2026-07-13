# Plan Quality Loop Skill Design

**Date:** 2026-07-13

**Status:** Approved for implementation planning

**Target location:** `C:\Users\ACER\.codex\skills\plan-quality-loop`

## 1. Objective

Create a personal Codex skill that repeatedly audits and repairs planning documents until they reach at least 95/100 and contain no remaining actionable findings.

The loop must preserve the project's stated purpose and intended complexity. A local portfolio project is not penalized for lacking production-only infrastructure or controls; adding those elements without an explicit requirement is scope creep and lowers the score.

## 2. Reuse and Boundaries

- Reuse `plan-reviewer` as the scoring and audit authority. Do not duplicate its rubric.
- Use separate Reviewer and Repair subagents. A Repair agent never accepts its own work.
- Edit planning documents only. Do not modify application code, create implementation tasks, or add project features.
- Do not commit plan repairs unless the user separately requests a commit.
- Keep the skill self-contained with `SKILL.md` and `agents/openai.yaml`; no scripts, assets, or extra reference files are required.

## 3. Scope Charter

Before the first review, the Coordinator derives a short Scope Charter from current user instructions and repository documents:

- project purpose and audience;
- runtime/environment model;
- explicit in-scope features;
- explicit out-of-scope features;
- required stack and architecture decisions;
- expected complexity level;
- files the loop may edit.

Current user instructions outrank repository documents. Explicit project constraints outrank generic best practices. Missing production features must not reduce the score when production readiness is outside scope.

## 4. Roles

### Coordinator

- Builds and preserves the Scope Charter.
- Dispatches a fresh Reviewer for every scoring pass.
- Dispatches Repair agents only for findings from the latest accepted report.
- Ensures repair scopes do not overlap when agents run concurrently.
- Checks the resulting diff against the report and Scope Charter.
- Owns iteration, PASS, and blocker decisions; it does not silently repair plan content itself.

### Reviewer

- Must use `plan-reviewer`.
- Is read-only and receives the Scope Charter plus all authoritative plan documents.
- Reads the supplied documents fully and scores them from fresh evidence.
- Reports only actionable correctness, flow, consistency, completeness, scope, and overengineering findings.
- Treats optional stylistic preferences as non-blocking notes rather than errors.

Every finding includes:

- stable finding ID;
- severity;
- file and heading or reliable line number;
- evidence;
- impact;
- minimal required repair;
- owner file/phase;
- scope-creep warning when relevant.

### Repair Agent

- Receives the Scope Charter, editable file list, and exact finding IDs assigned to it.
- Reads every affected section and adjacent flow before editing.
- Applies the smallest coherent diff that resolves root causes and all related references.
- Must not introduce new features, dependencies, services, endpoints, tables, statuses, or abstractions unless they are already required by the Scope Charter.
- Does not score, approve, commit, or expand its repair scope.

## 5. Iteration Flow

1. Discover authoritative documents and build the Scope Charter.
2. Run a fresh read-only Reviewer using `plan-reviewer`.
3. PASS only when the score is at least 95 and the report contains no actionable findings.
4. Otherwise, group compatible findings into non-overlapping repair scopes.
5. Run one Repair agent per scope. Repairs to the same file run sequentially; independent files may be repaired in parallel.
6. Inspect the diff for report alignment, cross-reference consistency, and scope preservation.
7. Run a new Reviewer from the complete updated documents, not from the prior report's conclusions.
8. Repeat until PASS or blocker.

A second independent Reviewer is an escalation mechanism only. Use it when two consecutive iterations do not improve the score or when Reviewer and Repair disagree about scope creep.

## 6. Completion and Blockers

PASS requires both:

- overall score `>= 95/100` under the project-calibrated rubric;
- zero remaining actionable findings at any severity.

Do not lower the threshold, relabel unresolved errors as stylistic notes, or stop merely because the score improved.

Return a blocker instead of guessing when:

- a repair requires a new user decision;
- authoritative requirements conflict;
- required documents are missing or ambiguous;
- the same finding survives three focused repair attempts.

The blocker report states the evidence, attempts made, exact unresolved decision, and affected files.

## 7. Safety and Simplicity Rules

- Preserve unrelated user changes and inspect the current diff before every repair.
- Search all references to a changed contract, status, flow, or owner phase.
- Prefer deletion or clarification over adding architecture.
- Never reward production complexity when it is not part of the project goal.
- Never remove explicit production requirements from a production-targeted plan merely to make it simpler.
- Reject repair proposals that improve a generic rubric while weakening the stated project objective.

## 8. Validation Design

Skill development follows RED-GREEN-REFACTOR with independent subagents.

### RED baseline

Run realistic prompts without the new skill and record whether the agent:

- self-reviews its own repair;
- stops at a high score while findings remain;
- adds production security, cloud, queues, or other out-of-scope work to a local portfolio plan;
- simplifies away explicit production requirements;
- guesses when requirements conflict.

### GREEN forward tests

Run the same scenarios with the skill:

1. A local portfolio plan must treat unjustified production infrastructure as overengineering.
2. A production-targeted plan must preserve explicit production requirements.
3. A plan with conflicting authoritative requirements must return a blocker.

Success requires role separation, a project-calibrated score, scoped repairs, fresh re-review, and correct PASS/blocker behavior.

### REFACTOR

Add only instructions needed to close failures observed during forward testing, then repeat the affected scenarios.

## 9. Skill Interface

Suggested invocation:

```text
Use $plan-quality-loop to audit and repair these plan documents until they pass.
```

The final response reports:

- final score and verdict;
- iteration count;
- repaired files and finding IDs;
- verification evidence;
- any blocker or intentionally non-actionable notes.
