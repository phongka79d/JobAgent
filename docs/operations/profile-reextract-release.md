# Profile re-extraction release, rehearsal, and rollback

Run only from the repository root with a private backup directory outside the
worktree. Never use `docker compose down -v`; named volumes are authoritative.
Do not run browser checks until the candidate has passed the image-equality gate.

```powershell
$ErrorActionPreference = 'Stop'
$ComposeArgs = @('--env-file', '.env', '-f', 'infrastructure/docker-compose.yml', '-p', 'jobagentlatest')
$ReleaseSha = (git rev-parse --short=12 HEAD).Trim()
$ReleaseShaExitCode = $LASTEXITCODE
$AppVolume = 'jobagentlatest_app_data'
$CloneVolume = 'jobagentlatest_app_data_plan18_rehearsal'
$BackupRoot = Join-Path $HOME 'JobAgentBackups'
$BackupArchive = Join-Path $BackupRoot "jobagentlatest-plan18-$ReleaseSha.tar"
$ExpectedServices = @('backend', 'frontend', 'neo4j')
function Assert-ComposeServices {
  $ActualServices = @(docker compose @ComposeArgs config --services | Sort-Object)
  Assert-NativeSucceeded 'Compose service inventory'
  if (($ActualServices -join ',') -ne ($ExpectedServices -join ',')) { throw "unexpected Compose services: $($ActualServices -join ',')" }
}
function Assert-NativeSucceeded([string]$Name) {
  if ($LASTEXITCODE -ne 0) { throw "$Name failed" }
}
function Assert-NativeOrRollback([string]$Name) {
  if ($LASTEXITCODE -ne 0) { Invoke-Rollback; throw "$Name failed" }
}
if ($ReleaseShaExitCode -ne 0) { throw 'release revision resolution failed' }
Assert-ComposeServices
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

$PreReleaseBackendImage = (docker inspect --format '{{.Image}}' jobagentlatest-backend-1).Trim()
Assert-NativeSucceeded 'pre-release backend image inspection'
$PreReleaseFrontendImage = (docker inspect --format '{{.Image}}' jobagentlatest-frontend-1).Trim()
Assert-NativeSucceeded 'pre-release frontend image inspection'
docker image tag $PreReleaseBackendImage "jobagent-backend:rollback-$ReleaseSha"
Assert-NativeSucceeded 'pre-release backend image tag'
docker image tag $PreReleaseFrontendImage "jobagent-frontend:rollback-$ReleaseSha"
Assert-NativeSucceeded 'pre-release frontend image tag'

function Invoke-Rollback {
  # Rollback: stop backend/frontend and restore the verified source snapshot.
  Assert-ComposeServices
  docker compose @ComposeArgs stop frontend backend
  Assert-NativeSucceeded 'rollback service stop'
  powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/app_data_snapshot.ps1 -Action Restore -ProjectName jobagentlatest -VolumeName $AppVolume -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $BackupArchive -ExpectedArchiveSha256 $BackupSha256 -ExpectedAlembicRevision 0008_profile_reextract_ownership -ConfirmRestore
  Assert-NativeSucceeded 'rollback source restore'
  docker image tag "jobagent-backend:rollback-$ReleaseSha" jobagent-backend:0.1.0
  Assert-NativeSucceeded 'rollback backend image tag'
  docker image tag "jobagent-frontend:rollback-$ReleaseSha" jobagent-frontend:0.1.0
  Assert-NativeSucceeded 'rollback frontend image tag'
  docker compose @ComposeArgs up -d --wait --wait-timeout 180 --force-recreate backend frontend
  Assert-NativeSucceeded 'rollback service start'
  powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/app_data_snapshot.ps1 -Action Verify -ProjectName jobagentlatest -VolumeName $AppVolume -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $BackupArchive -ExpectedArchiveSha256 $BackupSha256 -ExpectedAlembicRevision 0008_profile_reextract_ownership
  Assert-NativeSucceeded 'rollback source verify'
  docker compose @ComposeArgs exec -T backend python -m app.graph.rebuild
  Assert-NativeSucceeded 'rollback graph rebuild'
}

Assert-ComposeServices
docker compose @ComposeArgs stop backend
Assert-NativeSucceeded 'backend stop before backup'
powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/app_data_snapshot.ps1 -Action Backup -ProjectName jobagentlatest -VolumeName $AppVolume -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $BackupArchive -ExpectedAlembicRevision 0008_profile_reextract_ownership
Assert-NativeSucceeded 'source backup'
$BackupSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $BackupArchive).Hash.ToLowerInvariant()
docker compose @ComposeArgs build --pull backend frontend
Assert-NativeOrRollback 'candidate image build'
$CandidateBackendImage = (docker image inspect --format '{{.Id}}' jobagent-backend:0.1.0).Trim()
Assert-NativeOrRollback 'candidate backend image inspection'
$CandidateFrontendImage = (docker image inspect --format '{{.Id}}' jobagent-frontend:0.1.0).Trim()
Assert-NativeOrRollback 'candidate frontend image inspection'
docker image tag $CandidateBackendImage "jobagent-backend:candidate-$ReleaseSha"
Assert-NativeOrRollback 'candidate backend image tag'
docker image tag $CandidateFrontendImage "jobagent-frontend:candidate-$ReleaseSha"
Assert-NativeOrRollback 'candidate frontend image tag'

Assert-ComposeServices
docker volume create --label jobagent.release.purpose=plan18-rehearsal $CloneVolume
Assert-NativeOrRollback 'clone volume creation'
$CloneVolumeInspection = docker volume inspect $CloneVolume
Assert-NativeOrRollback 'clone purpose inspection'
$CloneVolumeMetadata = $CloneVolumeInspection | ConvertFrom-Json
$ClonePurpose = $CloneVolumeMetadata[0].Labels.'jobagent.release.purpose'
$ClonePurpose = if ($null -eq $ClonePurpose) { '' } else { $ClonePurpose.ToString().Trim() }
if ($ClonePurpose -ne 'plan18-rehearsal') { Invoke-Rollback; throw 'clone purpose label mismatch' }
powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/app_data_snapshot.ps1 -Action Restore -ProjectName jobagentlatest -VolumeName $CloneVolume -ArchivePath $BackupArchive -ExpectedArchiveSha256 $BackupSha256 -ExpectedPurpose plan18-rehearsal -ConfirmRestore -ExpectedAlembicRevision 0008_profile_reextract_ownership
Assert-NativeOrRollback 'clone restore'
$CloneSmokeProgram = @'
import shutil
import tempfile
from pathlib import Path

source = Path('/data/jobagent.db')
with tempfile.TemporaryDirectory() as temporary:
    scratch = Path(temporary) / 'jobagent.db'
    shutil.copy2(source, scratch)
    for suffix in ('-wal', '-shm'):
        sidecar = Path(f'{source}{suffix}')
        if sidecar.is_file():
            shutil.copy2(sidecar, Path(f"{scratch}{suffix}"))
    from app.services.profile_reextract_migration_smoke import run_smoke
    result = run_smoke(sqlite_path=scratch)
    assert result.alembic_revision == '0008_profile_reextract_ownership' and not result.foreign_key_check
'@
$CloneSmokeProgram | docker run --rm --network none -i -v "${CloneVolume}:/data:ro" $CandidateBackendImage python -
Assert-NativeOrRollback 'clone migration smoke'

# Recheck source identity separately before replacing authoritative consumers.
Assert-ComposeServices
powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/app_data_snapshot.ps1 -Action Verify -ProjectName jobagentlatest -VolumeName $AppVolume -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $BackupArchive -ExpectedArchiveSha256 $BackupSha256 -ExpectedAlembicRevision 0008_profile_reextract_ownership
Assert-NativeOrRollback 'authoritative source verify'
docker compose @ComposeArgs stop frontend
Assert-NativeOrRollback 'frontend stop before cutover'
docker compose @ComposeArgs up -d --wait --wait-timeout 180 --force-recreate backend frontend
Assert-NativeOrRollback 'candidate cutover'
$DeployedBackendImage = (docker inspect --format '{{.Image}}' jobagentlatest-backend-1).Trim()
Assert-NativeOrRollback 'deployed backend image inspection'
$DeployedFrontendImage = (docker inspect --format '{{.Image}}' jobagentlatest-frontend-1).Trim()
Assert-NativeOrRollback 'deployed frontend image inspection'
if ($DeployedBackendImage -ne $CandidateBackendImage) { Invoke-Rollback; throw 'candidate backend image ID mismatch' }
if ($DeployedFrontendImage -ne $CandidateFrontendImage) { Invoke-Rollback; throw 'candidate frontend image ID mismatch' }
```

Only after these gates pass may Task 12 perform health, inventory, browser, and log
acceptance. On any migration, health, inventory, browser, or log failure, immediately
run `Invoke-Rollback`; it restores the verified source snapshot and pre-release images,
then validates the prior revision/inventory and rebuilds derived Neo4j state.

## Task 12 post-cutover acceptance

Run these checks only after the deployed backend and frontend image IDs equal the
candidate IDs. Use synthetic PDFs and synthetic profile values only. Keep screenshots,
full logs, manifests, inventories, filenames, hashes, and command transcripts in the
private artifact area; the tracked acceptance ledger may contain only case IDs, counts,
redacted identifiers or non-reversible handles, UTC timestamps, and pass/fail codes.

Open the browser at `http://localhost:5173/`, which matches the configured
`FRONTEND_ORIGIN`; do not substitute `http://127.0.0.1:5173/` for browser
acceptance because the backend CORS gate is origin-exact. Health and Compose
service checks may continue to use `127.0.0.1`.

```powershell
try { $Health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' } catch { Invoke-Rollback; throw 'post-cutover health request failed' }
if ($Health.overall -ne 'available' -or $Health.sqlite -ne 'available' -or $Health.filesystem -ne 'available' -or $Health.neo4j -ne 'available') { Invoke-Rollback; throw 'post-cutover health gate failed' }
$RunningServices = @(docker compose @ComposeArgs ps --status running --services | Sort-Object)
Assert-NativeOrRollback 'post-cutover service inventory'
if (($RunningServices -join ',') -ne ($ExpectedServices -join ',')) { Invoke-Rollback; throw 'post-cutover service inventory mismatch' }
```

The browser gate must cover the running re-extraction state; both sidebar and chat
PDF upload controls disabled; the direct in-progress `409` action; close/reopen and
reload recovery; stale review; discard; retry; approval; active-CV lineage; narrow
viewport behavior; and keyboard focus restoration. Capture one private screenshot
handle per required observation and record only its non-sensitive handle and outcome.
If any browser observation, screenshot capture, or synthetic-data assertion fails,
run `Invoke-Rollback` before another browser attempt.

After the browser gate, collect filtered backend/frontend logs and fail closed on a
nonzero native exit or any `Traceback`, `no active connection`, `checked out`, `pool`,
or unexpected ` 5xx ` match:

```powershell
$LogText = docker compose @ComposeArgs logs --no-color backend frontend
Assert-NativeOrRollback 'post-cutover Compose logs'
if ($LogText -match 'Traceback|no active connection|checked out|pool|(?<![0-9])5xx(?![0-9])') { Invoke-Rollback; throw 'post-cutover Compose log gate failed' }
```

If a required source gate fails before cutover, do not build a candidate, restore a
clone, open the browser, or treat the failure as a warning. Preserve the authoritative
volume and pre-release images, repair only the failing gate at its owning source/test
boundary, then rerun the complete source gates from the repository root. Three
consecutive validation failures with no safe in-scope repair are a failed attempt,
not permission to bypass the release gate. `docker compose down -v` is never a
recovery step.
