# JobAgent Dependency and Container Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove obsolete scaffold files, make runtime/development dependency intent explicit, and reduce Docker build context without changing application behavior or adding dependencies.

**Architecture:** Keep one pinned runtime dependency list and one pinned Python `dev` extra, keep Astryx runtime packages separate from its CLI tooling, and use per-context `.dockerignore` files so Docker receives only build inputs. Validate both clean runtime and clean development installs before updating setup documentation.

**Tech Stack:** Python packaging (`pyproject.toml`, setuptools, pip), npm/package-lock, Docker Compose, PowerShell, Pytest, Ruff, Mypy, Vite.

---

## Scope and execution boundary

- Execute after Plan 16 and the three code-maintenance plans; do not mix manifest changes with product refactors.
- Remove dependencies only after clean-install validation. Do not upgrade any pinned version.
- Do not add a lockfile tool, CI workflow, package manager, base image, Compose service, or production dependency.
- Keep root `.env` ignored and outside Docker contexts. Do not print secrets during validation.
- Preserve the user's existing `docs/plans/Master_plan.md` modification.
- The four `docs/superpowers/plans/2026-07-22-*.md` files are planning
  artifacts. They may already be tracked or may remain untracked when execution
  starts; implementation commits must not stage them.

### Task 1: Remove obsolete scaffold sentinels

**Files:**
- Delete: `infrastructure/docker/.gitkeep`
- Delete: `infrastructure/neo4j/.gitkeep`
- Delete: `infrastructure/scripts/.gitkeep`

- [ ] **Step 1: Verify each directory already contains tracked real files**

Run:

```powershell
Get-ChildItem infrastructure/docker -Force
Get-ChildItem infrastructure/neo4j -Force
Get-ChildItem infrastructure/scripts -Force
git ls-files 'infrastructure/**/.gitkeep'
```

Expected: every directory contains real tracked files in addition to one zero-byte `.gitkeep`; Git lists exactly the three sentinels.

- [ ] **Step 2: Delete only the three sentinels**

Run:

```powershell
git rm -- infrastructure/docker/.gitkeep infrastructure/neo4j/.gitkeep infrastructure/scripts/.gitkeep
git diff --cached --name-status
```

Expected: exactly three staged `D` entries, one for each `.gitkeep`; no real
infrastructure file is staged.

- [ ] **Step 3: Verify directory and reference integrity**

Run:

```powershell
git ls-files 'infrastructure/**/.gitkeep'
rg -n '\.gitkeep' README.md docs infrastructure
git diff --check
```

Expected: Git lists no sentinel; only historical report prose may mention `.gitkeep`; real Dockerfiles, seed, and scripts remain tracked.

- [ ] **Step 4: Commit the scaffold cleanup**

```powershell
git add infrastructure/docker/.gitkeep infrastructure/neo4j/.gitkeep infrastructure/scripts/.gitkeep
git commit -m "chore: remove obsolete infrastructure sentinels"
```

Expected: one deletion-only commit.

### Task 2: Separate Python runtime and development dependencies

**Files:**
- Create: `backend/tests/unit/test_dependency_manifest.py`
- Modify: `backend/pyproject.toml:10-40`
- Test: `backend/tests/unit/test_dependency_manifest.py`

- [ ] **Step 1: Add a failing manifest contract test**

Create `backend/tests/unit/test_dependency_manifest.py`:

```python
from __future__ import annotations

import tomllib
from pathlib import Path

RUNTIME_FORBIDDEN = {
    "langchain",
    "mypy",
    "pytest",
    "pytest-asyncio",
    "ruff",
}
EXPECTED_DEV = {
    "mypy",
    "pytest",
    "pytest-asyncio",
    "ruff",
}


def _name(requirement: str) -> str:
    return requirement.split("==", maxsplit=1)[0].strip()


def test_runtime_and_dev_dependencies_are_separated() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = payload["project"]
    runtime = {_name(item) for item in project["dependencies"]}
    dev = {
        _name(item)
        for item in project["optional-dependencies"]["dev"]
    }
    assert runtime.isdisjoint(RUNTIME_FORBIDDEN)
    assert dev == EXPECTED_DEV
```

- [ ] **Step 2: Run the manifest test to verify RED**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_dependency_manifest.py -q
```

Expected: failure because no `dev` extra exists and runtime currently includes all forbidden entries.

- [ ] **Step 3: Remove only the unneeded direct runtime package and move tools to `dev`**

Delete these entries from `[project].dependencies`:

```toml
"langchain==1.3.13"
"ruff==0.15.21"
"mypy==1.18.2"
"pytest==9.1.1"
"pytest-asyncio==1.4.0"
```

Keep `langchain-core`, `langchain-openai`, `langgraph`, and every other runtime pin. Add:

```toml
[project.optional-dependencies]
dev = [
    "ruff==0.15.21",
    "mypy==1.18.2",
    "pytest==9.1.1",
    "pytest-asyncio==1.4.0",
]
```

- [ ] **Step 4: Verify clean runtime and development installs in one self-cleaning workspace**

Run from the repository root. The block is self-contained so execution does
not depend on PowerShell variables surviving between plan steps:

```powershell
Set-Location ..
$repoRoot = (Get-Location).Path
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$verifyRoot = Join-Path $tempRoot ("jobagent-deps-" + [guid]::NewGuid().ToString('N'))
$runtimeVenv = Join-Path $verifyRoot 'runtime'
$devVenv = Join-Path $verifyRoot 'dev'

function Assert-NativeSuccess([string]$label) {
  if ($LASTEXITCODE -ne 0) {
    throw "$label failed with exit code $LASTEXITCODE"
  }
}

try {
  New-Item -ItemType Directory -Path $verifyRoot | Out-Null

  python -m venv $runtimeVenv
  Assert-NativeSuccess 'create runtime venv'
  & (Join-Path $runtimeVenv 'Scripts/python.exe') -m pip install .\backend
  Assert-NativeSuccess 'install runtime package'
  & (Join-Path $runtimeVenv 'Scripts/python.exe') -m pip check
  Assert-NativeSuccess 'runtime pip check'
  & (Join-Path $runtimeVenv 'Scripts/python.exe') -c "import app.main; import langchain_core; import langchain_openai; import langgraph"
  Assert-NativeSuccess 'runtime import smoke test'
  & (Join-Path $runtimeVenv 'Scripts/python.exe') -c "import importlib.util; assert importlib.util.find_spec('pytest') is None; assert importlib.util.find_spec('pytest_asyncio') is None; assert importlib.util.find_spec('ruff') is None; assert importlib.util.find_spec('mypy') is None; assert importlib.util.find_spec('langchain') is None"
  Assert-NativeSuccess 'runtime exclusion check'

  python -m venv $devVenv
  Assert-NativeSuccess 'create development venv'
  & (Join-Path $devVenv 'Scripts/python.exe') -m pip install -e '.\backend[dev]'
  Assert-NativeSuccess 'install development package'
  & (Join-Path $devVenv 'Scripts/python.exe') -m pip check
  Assert-NativeSuccess 'development pip check'
  Set-Location backend
  & (Join-Path $devVenv 'Scripts/python.exe') -m pytest tests/unit/test_dependency_manifest.py -q
  Assert-NativeSuccess 'development manifest test'
} finally {
  Set-Location $repoRoot
  if (Test-Path -LiteralPath $verifyRoot) {
    $resolved = [System.IO.Path]::GetFullPath($verifyRoot)
    if (
      $resolved -eq $tempRoot -or
      -not $resolved.StartsWith(
        $tempRoot,
        [System.StringComparison]::OrdinalIgnoreCase
      )
    ) {
      throw "Refusing to remove a path outside the temp directory"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
}
```

Expected: the runtime install imports the application/frameworks while all
five removed packages are absent; the `[dev]` install runs the manifest test;
the verified temporary root is removed even when a validation command fails.

- [ ] **Step 5: Run the current backend environment gates**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m pytest tests/unit/test_dependency_manifest.py -q
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q
```

Expected: all commands exit 0 in the existing development environment.

- [ ] **Step 6: Commit the Python dependency separation**

```powershell
Set-Location ..
git add backend/pyproject.toml backend/tests/unit/test_dependency_manifest.py
git commit -m "build(backend): separate runtime and dev dependencies"
```

Expected: one Python-manifest/test commit with unchanged versions and no application code changes.

### Task 3: Classify the Astryx CLI as development tooling

**Files:**
- Modify: `frontend/package.json:14-31`
- Modify: `frontend/package-lock.json`
- Test: `frontend/package.json`

- [ ] **Step 1: Run a failing manifest assertion**

Run:

```powershell
Set-Location frontend
node -e "const p=require('./package.json'); if (p.dependencies['@astryxdesign/cli'] || !p.devDependencies['@astryxdesign/cli']) process.exit(1)"
```

Expected: exit 1 because the CLI is currently in `dependencies`.

- [ ] **Step 2: Move the exact pinned package using npm**

Run:

```powershell
npm install --save-dev --save-exact @astryxdesign/cli@0.1.4
```

Expected: `package.json` and `package-lock.json` change; version remains exactly `0.1.4`; `@astryxdesign/core` and `@astryxdesign/theme-neutral` remain runtime dependencies.

- [ ] **Step 3: Verify clean install, CLI availability, and frontend gates**

Run:

```powershell
npm ci
node -e "const p=require('./package.json'); if (p.dependencies['@astryxdesign/cli'] || p.devDependencies['@astryxdesign/cli'] !== '0.1.4') process.exit(1)"
npx astryx --help
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: all commands exit 0; Astryx CLI remains available to developers; production application imports/build output remain unchanged.

- [ ] **Step 4: Commit the frontend manifest change**

```powershell
Set-Location ..
git add frontend/package.json frontend/package-lock.json
git commit -m "build(frontend): classify astryx cli as dev tooling"
```

Expected: one lockstep package manifest/lock commit.

### Task 4: Reduce Docker contexts and build inputs

**Files:**
- Create: `backend/.dockerignore`
- Create: `frontend/.dockerignore`
- Modify: `infrastructure/docker/frontend.Dockerfile:12`
- Validate: `infrastructure/docker/backend.Dockerfile`
- Validate: `infrastructure/docker-compose.yml`

- [ ] **Step 1: Confirm the current context files are absent and ESLint is copied**

Run:

```powershell
Test-Path backend/.dockerignore
Test-Path frontend/.dockerignore
rg -n 'COPY .*eslint\.config\.js' infrastructure/docker/frontend.Dockerfile
```

Expected: both `Test-Path` calls return `False`; the Dockerfile copies `eslint.config.js` even though it runs only `npm run build`.

- [ ] **Step 2: Add the backend context allow/ignore boundary**

Create `backend/.dockerignore`:

```dockerignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
tests/
*.egg-info/
.env
.env.*
data/
```

- [ ] **Step 3: Add the frontend context boundary**

Create `frontend/.dockerignore`:

```dockerignore
node_modules/
dist/
coverage/
.vite/
*.log
.env
.env.*
eslint.config.js
```

- [ ] **Step 4: Remove ESLint config from the frontend build COPY**

Replace the Dockerfile line with:

```dockerfile
COPY index.html tsconfig.json vite.config.ts ./
```

Keep `COPY src ./src`, `npm ci`, and `npm run build` unchanged.

- [ ] **Step 5: Validate Compose configuration and build both images**

Run:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml config --quiet
docker compose --env-file .env -f infrastructure/docker-compose.yml build --progress plain backend frontend
```

Expected: configuration and both builds exit 0; printed contexts exclude host caches, tests, `node_modules`, and `dist`.

- [ ] **Step 6: Verify the runtime backend excludes development tools**

Run:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml run --rm --no-deps --entrypoint python backend -c "import importlib.util; assert importlib.util.find_spec('pytest') is None; assert importlib.util.find_spec('ruff') is None; assert importlib.util.find_spec('mypy') is None; import app.main"
```

Expected: exit 0; the runtime image imports the application and does not contain the three dev tools.

- [ ] **Step 7: Commit Docker context hygiene**

```powershell
git add backend/.dockerignore frontend/.dockerignore infrastructure/docker/frontend.Dockerfile
git commit -m "build: reduce docker build contexts"
```

Expected: one Docker-only commit.

### Task 5: Update installation documentation and run the integrated gate

**Files:**
- Modify: `README.md:440-455,500-521`
- Validate: `backend/pyproject.toml`
- Validate: `frontend/package.json`
- Validate: `infrastructure/docker-compose.yml`

- [ ] **Step 1: Update the local development install command**

Replace the backend editable-install command in README setup with:

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -e '.\backend[dev]'
```

Add one sentence immediately below it:

```text
The production image installs `backend` without `[dev]`; the local editable install uses `[dev]` so Pytest, Ruff, Mypy, and pytest-asyncio are available for repository gates.
```

Do not change application runtime commands or claim a Python lockfile exists.

- [ ] **Step 2: Verify documented commands exist in manifests**

Run:

```powershell
rg -n "backend\[dev\]|production image installs" README.md
& '.\.venv\Scripts\python.exe' -c "import tomllib, pathlib; p=tomllib.loads(pathlib.Path('backend/pyproject.toml').read_text()); assert 'dev' in p['project']['optional-dependencies']"
node -e "const p=require('./frontend/package.json'); for (const s of ['test','lint','typecheck','build']) if (!p.scripts[s]) process.exit(1)"
```

Expected: README contains the dev-extra distinction; Python and frontend manifest checks exit 0.

- [ ] **Step 3: Run final static, test, build, and Compose gates**

Run:

```powershell
Set-Location backend
& '..\.venv\Scripts\python.exe' -m ruff check app tests --no-cache
& '..\.venv\Scripts\python.exe' -m mypy app --no-incremental
& '..\.venv\Scripts\python.exe' -m pytest -q

Set-Location ..\frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build

Set-Location ..
docker compose --env-file .env -f infrastructure/docker-compose.yml config --quiet
git diff --check
git status --short
```

Expected: all commands exit 0; only planned files plus the user's pre-existing
Master Plan edit appear in status. The four authorized plan artifacts may also
appear when they were not committed before execution; no other unplanned path
may appear.

- [ ] **Step 4: Commit the documentation update**

```powershell
git add README.md
git commit -m "docs: document runtime and dev installs"
```

Expected: one README-only commit.

- [ ] **Step 5: Audit the five-commit scope**

Run:

```powershell
git log -5 --oneline
git diff --name-only HEAD~5..HEAD
git diff HEAD~5..HEAD -- backend/app frontend/src infrastructure/docker-compose.yml docs/plans docs/tasks
```

Expected: the five planned commits are present; application source, Compose service topology, plans/tasks, and database contracts are unchanged.

## Deferred findings requiring Master Plan approval

- GitHub Actions or any CI workflow is explicitly out of scope in Master Plan Section 2.2.
- Backup/restore automation, request IDs, structured metrics, tracing, and production network hardening are operational features with independent acceptance criteria; they must receive a Master amendment before implementation.
- A Python lockfile or hash-locked constraints set introduces a new dependency-management workflow and is intentionally not part of this hygiene plan.
