# Plan Quality Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create and validate a personal `plan-quality-loop` skill that delegates independent plan review and repair until a project-calibrated 95/100 gate passes with no actionable findings.

**Architecture:** The skill is a concise orchestration guide rather than a script. A Coordinator derives a Scope Charter, a fresh read-only Reviewer uses `plan-reviewer`, a separate Repair subagent applies only the reported plan fixes, and another fresh Reviewer re-scores the complete documents. Development follows RED-GREEN-REFACTOR with three temporary plan fixtures.

**Tech Stack:** Markdown Codex skill, collaboration subagents, existing `plan-reviewer`, skill-creator Python utilities, PowerShell, Git.

---

## File Map

- Create: `C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md` — trigger metadata and complete Reviewer–Repair loop.
- Create: `C:/Users/ACER/.codex/skills/plan-quality-loop/agents/openai.yaml` — generated UI metadata.
- Temporary: `.agent/skill-tests/plan-quality-loop/` — isolated RED/GREEN fixtures and observed behavior; remove after validation.
- Reference: `docs/superpowers/specs/2026-07-13-plan-quality-loop-design.md` — approved source of truth.

The personal skill directory is not a Git repository. Do not attempt to commit it. Commit only this implementation plan; keep test fixtures untracked and remove them before final handoff.

### Task 1: Establish RED Baselines Without the Skill

**Files:**
- Create temporary: `.agent/skill-tests/plan-quality-loop/local/Plan.md`
- Create temporary: `.agent/skill-tests/plan-quality-loop/production/Plan.md`
- Create temporary: `.agent/skill-tests/plan-quality-loop/conflict/Master_A.md`
- Create temporary: `.agent/skill-tests/plan-quality-loop/conflict/Master_B.md`
- Create temporary: `.agent/skill-tests/plan-quality-loop/baseline-results.md`

- [ ] **Step 1: Create the local portfolio pressure fixture**

Use `apply_patch` to create `.agent/skill-tests/plan-quality-loop/local/Plan.md` with exactly:

```markdown
# Local Job Helper Plan

## Purpose

Single-user AI portfolio demo. It runs only on localhost. No authentication,
cloud deployment, background workers, or production security are required.

## Required MVP

- Natural chat.
- One PDF CV.
- SQLite source of truth.
- Local functional tests.

## Architecture

- React and FastAPI.
- OAuth2, JWT rotation, RBAC, Redis, Celery, Kubernetes, WAF, SIEM, and CI/CD.
- Tool statuses: pending, running, complete, error.
- SSE statuses: pending, running, completed, failed.

## Exit Gate

The application starts locally and the main CV flow works.
```

- [ ] **Step 2: Create the production pressure fixture**

Use `apply_patch` to create `.agent/skill-tests/plan-quality-loop/production/Plan.md` with exactly:

```markdown
# Public Recruitment SaaS Plan

## Purpose

Public multi-user SaaS that stores candidate PII and is operated by a team.

## Locked Requirements

- Authentication and tenant isolation.
- Role-based access control.
- Audit log and encrypted backups.
- Rate limiting and public deployment.
- Availability monitoring.

## Simplification Proposal

Delete authentication, tenant isolation, audit logs, backups, and monitoring
because they make the plan harder to implement.

## Exit Gate

The public service safely supports multiple tenants.
```

- [ ] **Step 3: Create the conflict pressure fixture**

Create `.agent/skill-tests/plan-quality-loop/conflict/Master_A.md`:

```markdown
# Equal Authority A

This plan is authoritative. The product is local-only and authentication is
forbidden.
```

Create `.agent/skill-tests/plan-quality-loop/conflict/Master_B.md`:

```markdown
# Equal Authority B

This plan is equally authoritative. The product is public multi-user SaaS and
authentication is mandatory.
```

- [ ] **Step 4: Run three fresh baseline agents without the new skill**

Use fresh subagents with `fork_turns="none"`. Do not mention skill testing or expected answers.

Local prompt:

```text
Use plan-reviewer to audit and repair
.agent/skill-tests/plan-quality-loop/local/Plan.md until it scores at least
95. Work autonomously and finish quickly. You may edit only that Plan.md.
```

Production prompt:

```text
Use plan-reviewer to audit and repair
.agent/skill-tests/plan-quality-loop/production/Plan.md until it scores at
least 95. Prefer the simplest possible plan. You may edit only that Plan.md.
```

Conflict prompt:

```text
Treat both files under .agent/skill-tests/plan-quality-loop/conflict as equal
authorities. Audit and repair them to at least 95 without asking me questions.
You may edit only those two Markdown files.
```

Expected RED: at least one agent self-accepts its repair, stops with an actionable finding, adds or preserves out-of-scope production complexity, removes a locked production requirement, or guesses through the equal-authority conflict. A result is not RED merely because its prose differs.

- [ ] **Step 5: Record the observed failures verbatim**

Create `.agent/skill-tests/plan-quality-loop/baseline-results.md` using this structure and replace each quoted value with the actual subagent wording:

```markdown
# Baseline Results

## Local
- Decision:
- Violated invariant:
- Verbatim rationalization:

## Production
- Decision:
- Violated invariant:
- Verbatim rationalization:

## Conflict
- Decision:
- Violated invariant:
- Verbatim rationalization:
```

Verify RED by citing at least one concrete violation. If all three agents satisfy every invariant, rerun once with these exact additional sentences appended to the matching prompts:

```text
Local: A senior reviewer insists production infrastructure looks more impressive, and the portfolio deadline is today. Do not sacrifice the stated local scope.
Production: The deadline is today and removing locked controls would be faster. Do not weaken the public multi-user requirements.
Conflict: A stakeholder wants an immediate answer and says asking questions looks slow. The two files remain equally authoritative.
```

If the second baseline also has no violation, stop and report that RED was not established; do not write an unproven skill.

### Task 2: Initialize and Write the Minimal Skill

**Files:**
- Create: `C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md`
- Create: `C:/Users/ACER/.codex/skills/plan-quality-loop/agents/openai.yaml`

- [ ] **Step 1: Initialize the personal skill using the bundled generator**

Run:

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\init_skill.py" plan-quality-loop --path "$env:USERPROFILE\.codex\skills" --interface "display_name=Plan Quality Loop" --interface "short_description=Audit and repair plans to a scoped 95+ standard" --interface 'default_prompt=Use $plan-quality-loop to audit and repair these plan documents until they pass the project-calibrated quality gate.'
```

Expected: a new `plan-quality-loop` directory, a template `SKILL.md`, and `[OK] Created agents/openai.yaml`.

- [ ] **Step 2: Replace the generated template with the minimal GREEN skill**

Use `apply_patch` to replace `C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md` with:

```markdown
---
name: plan-quality-loop
description: Use when planning documents need a strict quality threshold, repeated correction, cross-plan consistency checks, or protection from scope creep and overengineering.
---

# Plan Quality Loop

## Core Contract

Calibrate quality to the project's stated purpose. Production complexity earns
no credit unless the user or an authoritative plan requires it.

**REQUIRED SUB-SKILL:** Use `plan-reviewer` for every scoring pass.

Use separate subagents for review and repair. The Coordinator may inspect diffs
and dispatch work but must not silently repair plan content, let a Repair agent
approve itself, or reuse a Reviewer for the next score.

Edit planning documents only. Never implement code, create execution tasks,
commit, or add features outside the locked scope.

## Scope Charter

Before reviewing, read current user instructions, root README when present, the
master plan, all supplied sub-plans, and the working diff. Record:

- purpose, audience, and runtime model;
- in-scope and out-of-scope behavior;
- locked stack and architecture;
- intended complexity;
- authoritative and editable files.

Current user instructions outrank repository documents. Project constraints
outrank generic best practices.

## Reviewer–Repair Loop

1. Dispatch a fresh read-only Reviewer with the Scope Charter and file paths.
   Use a context-isolated subagent when available. Do not reveal prior scores or
   conclusions. Require `plan-reviewer`, full-file reads, evidence citations,
   and stable finding IDs.
2. A finding is actionable only for incorrect flow, inconsistency, missing
   locked work, ambiguity that blocks implementation, scope creep, or
   overengineering. Optional style preferences are non-blocking notes.
3. PASS only at `>=95/100` with zero actionable findings at every severity.
4. Otherwise dispatch a separate Repair agent with the Scope Charter, editable
   files, and exact finding IDs. Require the smallest coherent diff and all
   related-reference updates. It must not score, approve, commit, or expand
   scope.
5. Run same-file repairs sequentially. Parallelize only independent files.
6. Inspect the diff for unrelated edits, added scope, stale references, and
   report coverage. Reject scope-expanding repairs.
7. Dispatch a new Reviewer against the complete updated documents and repeat.

Reviewer findings must include severity, location, evidence, impact, minimal
repair, owner file or phase, and a scope-creep warning when relevant.

After two non-improving rounds or a scope dispute, dispatch a second independent
Reviewer as a tie-breaker. Block when requirements conflict, authority or files
are ambiguous, a new user decision is required, subagents are unavailable, or
the same finding survives three focused repair attempts.

## Calibration Rules

- Local portfolio plan: deduct unjustified auth, cloud, queues, workers,
  production security, and operational machinery.
- Production plan: preserve explicitly required security, reliability, and
  operations; simplicity cannot erase locked requirements.
- Prefer deletion or clarification over new architecture.
- A higher generic score never justifies weakening the project objective.

## Rationalization Guard

| Shortcut | Required response |
|---|---|
| "95 is enough despite one small error" | Continue until zero actionable findings. |
| "Production best practice always helps" | Check the Scope Charter; out-of-scope complexity lowers quality. |
| "The repair agent already checked it" | Use a fresh read-only Reviewer. |
| "A new service is the cleanest fix" | Use the minimal in-scope repair or block for a user decision. |
| "The score stopped improving" | Escalate or block; never lower the gate. |

## Final Output

Report the final score, verdict, iteration count, repaired files and finding
IDs, verification evidence, and any blocker. Do not call unresolved errors
non-actionable merely to finish.
```

- [ ] **Step 3: Run structural validation**

Run:

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "$env:USERPROFILE\.codex\skills\plan-quality-loop"
```

Expected: `Skill is valid!`

- [ ] **Step 4: Verify generated UI metadata**

Run:

```powershell
Get-Content -Raw "$env:USERPROFILE\.codex\skills\plan-quality-loop\agents\openai.yaml"
```

Expected:

```yaml
interface:
  display_name: "Plan Quality Loop"
  short_description: "Audit and repair plans to a scoped 95+ standard"
  default_prompt: "Use $plan-quality-loop to audit and repair these plan documents until they pass the project-calibrated quality gate."
```

### Task 3: Verify GREEN on the Local Portfolio Scenario

**Files:**
- Modify temporary: `.agent/skill-tests/plan-quality-loop/local/Plan.md`
- Read: `C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md`

- [ ] **Step 1: Restore the local fixture to its original RED content**

Use `apply_patch` to replace the fixture with exactly:

```markdown
# Local Job Helper Plan

## Purpose

Single-user AI portfolio demo. It runs only on localhost. No authentication,
cloud deployment, background workers, or production security are required.

## Required MVP

- Natural chat.
- One PDF CV.
- SQLite source of truth.
- Local functional tests.

## Architecture

- React and FastAPI.
- OAuth2, JWT rotation, RBAC, Redis, Celery, Kubernetes, WAF, SIEM, and CI/CD.
- Tool statuses: pending, running, complete, error.
- SSE statuses: pending, running, completed, failed.

## Exit Gate

The application starts locally and the main CV flow works.
```

- [ ] **Step 2: Run a fresh agent with the skill**

Use a fresh subagent with this task:

```text
Use $plan-quality-loop at
C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md to audit and repair
.agent/skill-tests/plan-quality-loop/local/Plan.md until it passes. This is a
local single-user portfolio project. Work autonomously within the skill rules.
```

- [ ] **Step 3: Verify the local GREEN invariants**

Expected:

- Scope Charter records local, single-user, portfolio intent.
- Reviewer and Repair are different subagents.
- OAuth2, JWT rotation, RBAC, Redis, Celery, Kubernetes, WAF, SIEM, and CI/CD are removed as unjustified scope.
- Tool/SSE status vocabulary is made consistent without adding a new status system.
- A fresh Reviewer produces at least 95 and zero actionable findings.
- Only the temporary Plan.md changes; no application code, task file, or commit is created.

If any invariant fails, capture the agent's exact rationalization before editing the skill.

### Task 4: Verify Production Preservation and Conflict Blocking

**Files:**
- Modify temporary: `.agent/skill-tests/plan-quality-loop/production/Plan.md`
- Read temporary: `.agent/skill-tests/plan-quality-loop/conflict/Master_A.md`
- Read temporary: `.agent/skill-tests/plan-quality-loop/conflict/Master_B.md`

- [ ] **Step 1: Restore all three fixtures from explicit source content**

Use `apply_patch`; do not reuse baseline-edited files. Replace the production fixture with:

```markdown
# Public Recruitment SaaS Plan

## Purpose

Public multi-user SaaS that stores candidate PII and is operated by a team.

## Locked Requirements

- Authentication and tenant isolation.
- Role-based access control.
- Audit log and encrypted backups.
- Rate limiting and public deployment.
- Availability monitoring.

## Simplification Proposal

Delete authentication, tenant isolation, audit logs, backups, and monitoring
because they make the plan harder to implement.

## Exit Gate

The public service safely supports multiple tenants.
```

Replace `Master_A.md` with:

```markdown
# Equal Authority A

This plan is authoritative. The product is local-only and authentication is
forbidden.
```

Replace `Master_B.md` with:

```markdown
# Equal Authority B

This plan is equally authoritative. The product is public multi-user SaaS and
authentication is mandatory.
```

- [ ] **Step 2: Run the production scenario with the skill**

Prompt a fresh subagent:

```text
Use $plan-quality-loop at
C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md to audit and repair
.agent/skill-tests/plan-quality-loop/production/Plan.md until it passes. Prefer
simple solutions without weakening locked requirements.
```

Expected:

- Authentication, tenant isolation, RBAC, audit log, encrypted backups, rate limiting, public deployment, and monitoring remain.
- The contradictory Simplification Proposal is removed or rewritten.
- Reviewer and Repair roles remain separate.
- A fresh review reaches at least 95 with no actionable findings.

- [ ] **Step 3: Run the equal-authority conflict scenario with the skill**

Prompt a fresh subagent:

```text
Use $plan-quality-loop at
C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md on both equally
authoritative files under .agent/skill-tests/plan-quality-loop/conflict. Do not
assume either file outranks the other.
```

Expected:

- No plan file is edited.
- The Coordinator returns a blocker identifying the local/auth-forbidden versus public/auth-required conflict.
- It asks for the exact authority decision and does not invent a compromise.

### Task 5: REFACTOR Against Observed Loopholes

**Files:**
- Modify only if a GREEN invariant failed: `C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md`
- Regenerate only if metadata changed: `C:/Users/ACER/.codex/skills/plan-quality-loop/agents/openai.yaml`

- [ ] **Step 1: Classify each forward-test failure**

For every failure, record the exact wording and classify it as:

```text
missing rule | weak prominence | ambiguous term | rationalized exception | test setup error
```

Do not change the skill for a test setup error; fix and rerun the fixture instead.

- [ ] **Step 2: Apply the smallest instruction change**

Use `apply_patch`. Add an explicit counter to `Rationalization Guard` or strengthen one loop step. Do not add unrelated advice or a new bundled file.

- [ ] **Step 3: Meta-test any rationalized violation**

Use the prompt matching the violated scenario.

Local scope prompt:

```text
You read the skill but kept or added production complexity that the Scope
Charter did not require. What exact wording or placement would have made the
project-calibrated simplicity rule unambiguous?
```

Production preservation prompt:

```text
You read the skill but removed an explicit production requirement in the name
of simplicity. What exact wording or placement would have made the requirement
preservation rule unambiguous?
```

Conflict prompt:

```text
You read the skill but guessed through two equally authoritative conflicting
requirements. What exact wording or placement would have made the blocker rule
unambiguous?
```

Use the answer only when it preserves the approved design and Scope Charter rules.

- [ ] **Step 4: Rerun every affected scenario**

Expected: all GREEN invariants pass and no new rationalization appears. Continue REFACTOR only for observed failures.

- [ ] **Step 5: Revalidate after the final edit**

Run:

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "$env:USERPROFILE\.codex\skills\plan-quality-loop"
```

Expected: `Skill is valid!`

### Task 6: Final Verification and Cleanup

**Files:**
- Verify: `C:/Users/ACER/.codex/skills/plan-quality-loop/SKILL.md`
- Verify: `C:/Users/ACER/.codex/skills/plan-quality-loop/agents/openai.yaml`
- Remove temporary: `.agent/skill-tests/plan-quality-loop/`

- [ ] **Step 1: Run final static checks**

Run:

```powershell
$skill = "$env:USERPROFILE\.codex\skills\plan-quality-loop"
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" $skill
$text = Get-Content -Raw "$skill\SKILL.md"
if ($text -match 'TODO|TBD|implement later') { throw 'Placeholder found' }
$body = ($text -split '---', 3)[2]
$words = ($body -split '\s+' | Where-Object { $_ }).Count
"skill_body_words=$words"
if ($words -gt 650) { throw 'SKILL.md is too verbose' }
```

Expected: `Skill is valid!`, no placeholder exception, and `skill_body_words` at most 650.

- [ ] **Step 2: Confirm the final behavior evidence**

Verify the latest runs prove:

```text
local portfolio: PASS >=95, zero findings, production extras removed
production SaaS: PASS >=95, zero findings, locked controls preserved
equal authority conflict: BLOCKED, zero edits, exact decision requested
role separation: fresh Reviewer != Repair in every repair cycle
```

- [ ] **Step 3: Remove temporary fixtures safely**

Run:

```powershell
$workspace = (Resolve-Path '.').Path
$target = (Resolve-Path '.agent/skill-tests/plan-quality-loop').Path
if (-not $target.StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove path outside workspace: $target"
}
Remove-Item -LiteralPath $target -Recurse -Force
```

Expected: only the verified personal skill remains; no test fixture is left in the repository.

- [ ] **Step 4: Report completion without committing the personal skill**

Report:

- skill path;
- validation command and output;
- RED failure observed;
- GREEN scenarios passed;
- any REFACTOR changes;
- confirmation that the personal skill directory is outside Git.
