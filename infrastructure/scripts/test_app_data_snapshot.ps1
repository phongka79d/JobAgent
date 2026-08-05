$ErrorActionPreference = 'Stop'

function Assert-Throws([scriptblock]$Action) {
  try { & $Action } catch { return }
  throw 'Expected command to fail closed.'
}
function Assert-Contains([string]$Text, [string]$Needle) { if (-not $Text.Contains($Needle)) { throw "Missing required contract: $Needle" } }
function Assert-NotContains([string]$Text, [string]$Needle) { if ($Text.Contains($Needle)) { throw "Forbidden contract text: $Needle" } }
function Assert-ReleaseGate([string]$Text, [string]$Command) {
  $pattern = [regex]::Escape($Command) + '[\s\S]{0,500}Assert-Native(?:Succeeded|OrRollback)'
  if (-not [regex]::IsMatch($Text, $pattern)) { throw "Missing failure gate after: $Command" }
}
function Assert-CloneSmokeUsesWritableScratch([string]$Text) {
  Assert-Contains $Text '$CloneSmokeProgram | docker run --rm --network none -i'
  Assert-Contains $Text '-v "${CloneVolume}:/data:ro"'
  Assert-Contains $Text 'import shutil'
  Assert-Contains $Text 'import tempfile'
  Assert-Contains $Text "for suffix in ('-wal', '-shm'):"
  Assert-Contains $Text 'shutil.copy2(source, scratch)'
  Assert-Contains $Text 'shutil.copy2(sidecar, Path(f"{scratch}{suffix}"))'
  Assert-Contains $Text 'run_smoke(sqlite_path=scratch)'
  Assert-Contains $Text 'python -'
  Assert-NotContains $Text 'python -c'
}
function Assert-ClonePurposeUsesJsonInspection([string]$Text) {
  Assert-Contains $Text '$CloneVolumeInspection = docker volume inspect $CloneVolume'
  Assert-Contains $Text '$CloneVolumeMetadata = $CloneVolumeInspection | ConvertFrom-Json'
  Assert-Contains $Text ".Labels.'jobagent.release.purpose'"
  Assert-NotContains $Text 'docker volume inspect --format'
  $pattern = [regex]::Escape('$CloneVolumeInspection = docker volume inspect $CloneVolume') + '[\s\S]{0,120}' + [regex]::Escape("Assert-NativeOrRollback 'clone purpose inspection'")
  if (-not [regex]::IsMatch($Text, $pattern)) { throw 'Clone label inspection must assert native success before parsing JSON.' }
}
function Assert-SnapshotFactsUsesStdin {
  $temporary = Join-Path $env:TEMP ("jobagent-snapshot-stdin-test-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Path $temporary | Out-Null
  try {
    $archive = Join-Path $temporary 'snapshot.tar'
    Set-Content -NoNewline -LiteralPath $archive -Value 'synthetic archive'
    $global:SnapshotStdinSource = $null
    function global:docker {
      if ($args[0] -eq 'volume' -and $args[1] -eq 'inspect') {
        '[{"Labels":{"com.docker.compose.project":"jobagentlatest","com.docker.compose.volume":"app_data"}}]'
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'inspect') {
        '{"State":{"Running":false},"Mounts":[{"Type":"volume","Name":"jobagentlatest_app_data"}]}'
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'run' -and $args -contains 'python:3.13-alpine') {
        if ($args[-2] -ne 'python' -or $args[-1] -ne '-') { throw 'snapshot facts did not end with python -' }
        $global:SnapshotStdinSource = ($input | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($global:SnapshotStdinSource)) { throw 'snapshot facts Python source was not supplied on stdin' }
        '{"table_counts":{"profiles":1},"active_profile":"profile-1","pending_actions":0,"alembic_revision":"0008_profile_reextract_ownership"}'
        $global:LASTEXITCODE = 0
        return
      }
      $global:LASTEXITCODE = 0
    }
    & $script -Action Backup -ProjectName jobagentlatest -VolumeName jobagentlatest_app_data -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $archive -ExpectedAlembicRevision 0008_profile_reextract_ownership
    if ([string]::IsNullOrWhiteSpace($global:SnapshotStdinSource)) { throw 'Snapshot facts stdin regression did not observe source.' }
  } finally {
    Remove-Item function:global:docker -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force -LiteralPath $temporary -ErrorAction SilentlyContinue
  }
}
function Assert-RestoreFailsOnNativeFailure([string]$NativeFailure) {
  $temporary = Join-Path $env:TEMP ("jobagent-snapshot-test-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Path $temporary | Out-Null
  try {
    $archive = Join-Path $temporary 'snapshot.tar'
    Set-Content -NoNewline -LiteralPath $archive -Value 'synthetic archive'
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    @{ sha256 = $hash; inventory = @('./payload.txt'); table_counts = @{ profiles = 1 }; active_profile = 'profile-1'; pending_actions = 0; alembic_revision = '0008_profile_reextract_ownership' } |
      ConvertTo-Json -Depth 5 | Set-Content -NoNewline -LiteralPath "$archive.manifest.json"
    $global:SnapshotNativeFailure = $NativeFailure
    $global:SnapshotDockerRunCount = 0
    function global:tar {
      if ($global:SnapshotNativeFailure -eq 'archive') { $global:LASTEXITCODE = 1; return }
      $destination = $args[($args.IndexOf('-C') + 1)]
      Set-Content -NoNewline -LiteralPath (Join-Path $destination 'payload.txt') -Value 'synthetic payload'
      $global:LASTEXITCODE = 0
    }
    function global:docker {
      if ($args[0] -eq 'volume' -and $args[1] -eq 'inspect') {
        '[{"Labels":{"jobagent.release.purpose":"plan18-rehearsal"}}]'
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'run') {
        $global:SnapshotDockerRunCount++
        $global:LASTEXITCODE = 1
        return
      }
      throw "unexpected fake Docker call: $($args -join ' ')"
    }
    $failure = $null
    try {
      & $script -Action Restore -ProjectName jobagentlatest -VolumeName jobagentlatest_app_data_plan18_rehearsal -ExpectedPurpose plan18-rehearsal -ArchivePath $archive -ExpectedArchiveSha256 $hash -ExpectedAlembicRevision 0008_profile_reextract_ownership -ConfirmRestore
    } catch { $failure = $_.Exception.Message }
    if ($null -eq $failure) { throw 'Expected Restore to fail closed on fake native failure.' }
    if ($NativeFailure -eq 'archive' -and $failure -notmatch 'archive extraction failed') { throw "Expected archive extraction failure, got: $failure" }
    if ($NativeFailure -eq 'replacement' -and $failure -notmatch 'Docker replacement failed') { throw "Expected Docker replacement failure, got: $failure" }
    if ($NativeFailure -eq 'archive' -and $global:SnapshotDockerRunCount -ne 0) { throw 'Restore reached Docker replacement after archive extraction failure.' }
    if ($NativeFailure -eq 'replacement' -and $global:SnapshotDockerRunCount -ne 1) { throw 'Restore did not attempt exactly one fake Docker replacement.' }
  } finally {
    Remove-Item function:global:tar -ErrorAction SilentlyContinue
    Remove-Item function:global:docker -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force -LiteralPath $temporary -ErrorAction SilentlyContinue
  }
}
function Assert-VerifyRejectsLiveMismatch([string]$MismatchType) {
  $temporary = Join-Path $env:TEMP ("jobagent-verify-test-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Path $temporary | Out-Null
  try {
    $archive = Join-Path $temporary 'snapshot.tar'
    Set-Content -NoNewline -LiteralPath $archive -Value 'synthetic archive'
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    @{ sha256 = $hash; inventory = @('./payload.txt'); table_counts = @{ profiles = 1 }; active_profile = 'profile-1'; pending_actions = 0; alembic_revision = '0008_profile_reextract_ownership' } |
      ConvertTo-Json -Depth 5 | Set-Content -NoNewline -LiteralPath "$archive.manifest.json"
    $global:SnapshotVerifyMismatch = $MismatchType
    $global:SnapshotDockerRunCount = 0
    function global:docker {
      $command = $args -join ' '
      if ($args[0] -eq 'volume' -and $args[1] -eq 'inspect') {
        '[{"Labels":{"com.docker.compose.project":"jobagentlatest","com.docker.compose.volume":"app_data"}}]'
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'inspect') {
        '[{"Mounts":[{"Type":"volume","Name":"jobagentlatest_app_data"}]}]'
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'run' -and $command -match 'find \. -type f') {
        $global:SnapshotDockerRunCount++
        if ($global:SnapshotVerifyMismatch -eq 'inventory') { './unexpected.txt' } else { './payload.txt' }
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'run' -and $command -match 'python -$') {
        $global:SnapshotDockerRunCount++
        $revision = if ($global:SnapshotVerifyMismatch -eq 'revision') { '0007_previous_revision' } else { '0008_profile_reextract_ownership' }
        @{ table_counts = @{ profiles = 1 }; active_profile = 'profile-1'; pending_actions = 0; alembic_revision = $revision } | ConvertTo-Json -Compress
        $global:LASTEXITCODE = 0
        return
      }
      throw "unexpected fake Docker call: $command"
    }
    $failure = $null
    try {
      & $script -Action Verify -ProjectName jobagentlatest -VolumeName jobagentlatest_app_data -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $archive -ExpectedArchiveSha256 $hash -ExpectedAlembicRevision 0008_profile_reextract_ownership
    } catch { $failure = $_.Exception.Message }
    if ($null -eq $failure) { throw "Expected Verify to reject live $MismatchType mismatch." }
    if ($MismatchType -eq 'inventory' -and $failure -notmatch 'live volume inventory mismatch') { throw "Expected live inventory failure, got: $failure" }
    if ($MismatchType -eq 'revision' -and $failure -notmatch 'live Alembic revision mismatch') { throw "Expected live revision failure, got: $failure" }
    $expectedDockerRuns = if ($MismatchType -eq 'inventory') { 1 } else { 2 }
    if ($global:SnapshotDockerRunCount -ne $expectedDockerRuns) { throw "Expected Verify to read $expectedDockerRuns live Docker resource(s), got $($global:SnapshotDockerRunCount)." }
  } finally {
    Remove-Item function:global:docker -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force -LiteralPath $temporary -ErrorAction SilentlyContinue
  }
}

function Assert-VerifyAcceptsManifestListedSidecars {
  $temporary = Join-Path $env:TEMP ("jobagent-verify-sidecar-test-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Path $temporary | Out-Null
  try {
    $archive = Join-Path $temporary 'snapshot.tar'
    Set-Content -NoNewline -LiteralPath $archive -Value 'synthetic archive'
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    @{ sha256 = $hash; inventory = @('./jobagent.db'); table_counts = @{ profiles = 1 }; active_profile = 'profile-1'; pending_actions = 0; alembic_revision = '0008_profile_reextract_ownership' } |
      ConvertTo-Json -Depth 5 | Set-Content -NoNewline -LiteralPath "$archive.manifest.json"
    $global:SnapshotVerifySidecarMode = 'valid'
    $global:SnapshotDockerRunCount = 0
    function global:docker {
      $command = $args -join ' '
      if ($args[0] -eq 'volume' -and $args[1] -eq 'inspect') {
        '[{"Labels":{"com.docker.compose.project":"jobagentlatest","com.docker.compose.volume":"app_data"}}]'
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'inspect') {
        '[{"Mounts":[{"Type":"volume","Name":"jobagentlatest_app_data"}]}]'
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'run' -and $command -match 'find \. -type f') {
        $global:SnapshotDockerRunCount++
        @('./jobagent.db', './jobagent.db-shm', './jobagent.db-wal')
        if ($global:SnapshotVerifySidecarMode -eq 'unexpected') { './unexpected.txt' }
        $global:LASTEXITCODE = 0
        return
      }
      if ($args[0] -eq 'run' -and $command -match 'python -$') {
        $global:SnapshotDockerRunCount++
        @{ table_counts = @{ profiles = 1 }; active_profile = 'profile-1'; pending_actions = 0; alembic_revision = '0008_profile_reextract_ownership' } | ConvertTo-Json -Compress
        $global:LASTEXITCODE = 0
        return
      }
      throw "unexpected fake Docker call: $command"
    }
    try {
      & $script -Action Verify -ProjectName jobagentlatest -VolumeName jobagentlatest_app_data -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $archive -ExpectedArchiveSha256 $hash -ExpectedAlembicRevision 0008_profile_reextract_ownership
      if ($global:SnapshotDockerRunCount -ne 2) { throw "Expected Verify to read inventory and facts for valid sidecars, got $($global:SnapshotDockerRunCount) Docker runs." }
      $global:SnapshotVerifySidecarMode = 'unexpected'
      $global:SnapshotDockerRunCount = 0
      $failure = $null
      try {
        & $script -Action Verify -ProjectName jobagentlatest -VolumeName jobagentlatest_app_data -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath $archive -ExpectedArchiveSha256 $hash -ExpectedAlembicRevision 0008_profile_reextract_ownership
      } catch { $failure = $_.Exception.Message }
      if ($null -eq $failure -or $failure -notmatch 'live volume inventory mismatch') { throw "Expected Verify to reject unrelated inventory, got: $failure" }
      if ($global:SnapshotDockerRunCount -ne 1) { throw "Expected Verify to reject unrelated inventory before facts, got $($global:SnapshotDockerRunCount) Docker runs." }
    } finally {
      Remove-Item function:global:docker -ErrorAction SilentlyContinue
    }
  } finally {
    Remove-Item -Recurse -Force -LiteralPath $temporary -ErrorAction SilentlyContinue
  }
}

function Assert-SnapshotFactsUsesWritableScratch {
  $source = Get-Content -Raw $script
  Assert-Contains $source 'import shutil'
  Assert-Contains $source 'import tempfile'
  Assert-Contains $source 'with tempfile.TemporaryDirectory() as temporary:'
  Assert-Contains $source "for suffix in ('-wal', '-shm'):"
  Assert-Contains $source 'shutil.copy2(path, scratch)'
  Assert-Contains $source "sqlite3.connect(f'file:{scratch}?mode=ro', uri=True)"
}

$script = Join-Path $PSScriptRoot 'app_data_snapshot.ps1'
Assert-Throws { & $script -Action Backup -ProjectName jobagentlatest -VolumeName wrong_volume -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath (Join-Path $env:TEMP 'outside.tar') }
Assert-Throws { & $script -Action Verify -ProjectName jobagentlatest -VolumeName jobagentlatest_app_data -ExpectedConsumer jobagentlatest-backend-1 -ArchivePath (Join-Path $env:TEMP 'outside.tar') }
$source = Get-Content -Raw $script
Assert-Contains $source "[ValidateSet('Backup', 'Restore', 'Verify')]"
Assert-Contains $source 'function Get-SnapshotFacts'
Assert-Contains $source 'table_counts = $facts.table_counts'
Assert-Contains $source 'active_profile = $facts.active_profile'
Assert-Contains $source 'pending_actions = $facts.pending_actions'
Assert-Contains $source 'alembic_revision = $facts.alembic_revision'
Assert-Contains $source 'if ($ExpectedPurpose) { Assert-CloneVolume'
Assert-NotContains $source 'down -v'
Assert-SnapshotFactsUsesStdin
Assert-SnapshotFactsUsesWritableScratch
Assert-RestoreFailsOnNativeFailure 'archive'
Assert-RestoreFailsOnNativeFailure 'replacement'
Assert-VerifyRejectsLiveMismatch 'inventory'
Assert-VerifyRejectsLiveMismatch 'revision'
Assert-VerifyAcceptsManifestListedSidecars

$releaseProcedure = Get-Content -Raw (Join-Path $PSScriptRoot '..\..\docs\operations\profile-reextract-release.md')
Assert-CloneSmokeUsesWritableScratch $releaseProcedure
Assert-ClonePurposeUsesJsonInspection $releaseProcedure
@(
  'docker image tag $PreReleaseBackendImage',
  'docker volume create --label jobagent.release.purpose=plan18-rehearsal',
  '-Action Restore -ProjectName jobagentlatest -VolumeName $CloneVolume',
  '-ExpectedArchiveSha256 $BackupSha256 -ExpectedPurpose plan18-rehearsal -ConfirmRestore',
  'python -',
  'candidate backend image ID mismatch',
  'Rollback: stop backend/frontend and restore the verified source snapshot'
) | ForEach-Object { Assert-Contains $releaseProcedure $_ }
@(
  'app_data_snapshot.ps1 -Action Backup',
  'docker compose @ComposeArgs build --pull backend frontend',
  'app_data_snapshot.ps1 -Action Restore -ProjectName jobagentlatest -VolumeName $CloneVolume',
  'docker run --rm --network none',
  'app_data_snapshot.ps1 -Action Verify -ProjectName jobagentlatest -VolumeName $AppVolume',
  'docker compose @ComposeArgs up -d --wait --wait-timeout 180 --force-recreate backend frontend'
) | ForEach-Object { Assert-ReleaseGate $releaseProcedure $_ }
