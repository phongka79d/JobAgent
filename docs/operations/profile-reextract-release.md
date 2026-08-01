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
$ClonePurpose = (docker volume inspect --format '{{index .Labels "jobagent.release.purpose"}}' $CloneVolume).Trim()
Assert-NativeOrRollback 'clone purpose inspection'
if ($ClonePurpose -ne 'plan18-rehearsal') { Invoke-Rollback; throw 'clone purpose label mismatch' }
powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/scripts/app_data_snapshot.ps1 -Action Restore -ProjectName jobagentlatest -VolumeName $CloneVolume -ArchivePath $BackupArchive -ExpectedArchiveSha256 $BackupSha256 -ExpectedPurpose plan18-rehearsal -ConfirmRestore -ExpectedAlembicRevision 0008_profile_reextract_ownership
Assert-NativeOrRollback 'clone restore'
docker run --rm --network none -v "${CloneVolume}:/data:ro" $CandidateBackendImage python -c "from pathlib import Path; from app.services.profile_reextract_migration_smoke import run_smoke; r=run_smoke(sqlite_path=Path('/data/jobagent.db')); assert r.alembic_revision == '0008_profile_reextract_ownership' and not r.foreign_key_check"
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
