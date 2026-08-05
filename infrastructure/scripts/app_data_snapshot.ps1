param(
  [Parameter(Mandatory = $true)][ValidateSet('Backup', 'Restore', 'Verify')][string]$Action,
  [Parameter(Mandatory = $true)][string]$ProjectName,
  [Parameter(Mandatory = $true)][string]$VolumeName,
  [string]$ExpectedConsumer,
  [string]$ExpectedPurpose,
  [Parameter(Mandatory = $true)][string]$ArchivePath,
  [string]$ExpectedArchiveSha256,
  [string]$ExpectedAlembicRevision,
  [switch]$ConfirmRestore
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ArchivePath = [IO.Path]::GetFullPath($ArchivePath)
$ManifestPath = "$ArchivePath.manifest.json"

function Fail([string]$Message) { throw "app_data snapshot refused: $Message" }
function Assert-NativeSucceeded([string]$Name) { if ($LASTEXITCODE -ne 0) { Fail "$Name failed" } }
function Assert-PrivatePath([string]$Path) {
  if ([IO.Path]::GetFullPath($Path).StartsWith($RepositoryRoot, [StringComparison]::OrdinalIgnoreCase)) { Fail 'archive and manifest must be outside the repository worktree' }
}
function Get-Volume { docker volume inspect $VolumeName | ConvertFrom-Json | Select-Object -First 1 }
function Assert-AuthoritativeVolume($Volume) {
  if ($Volume.Labels.'com.docker.compose.project' -ne $ProjectName) { Fail 'authoritative Compose project label mismatch' }
  if ($Volume.Labels.'com.docker.compose.volume' -ne 'app_data') { Fail 'authoritative Compose volume label mismatch' }
}
function Assert-CloneVolume($Volume) {
  if ($Volume.Labels.'jobagent.release.purpose' -ne $ExpectedPurpose) { Fail 'clone purpose label mismatch' }
}
function Assert-Consumer([string]$Consumer) {
  $container = docker inspect $Consumer 2>$null | ConvertFrom-Json | Select-Object -First 1
  if ($null -eq $container) { Fail 'expected backend consumer does not exist' }
  if (-not ($container.Mounts | Where-Object { $_.Type -eq 'volume' -and $_.Name -eq $VolumeName })) { Fail 'expected consumer does not mount the requested volume' }
  return $container
}
function Get-Sha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Read-Manifest { if (-not (Test-Path -LiteralPath $ManifestPath)) { Fail 'private manifest is missing' }; Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json }
function Assert-Archive([string]$ExpectedHash) {
  if (-not (Test-Path -LiteralPath $ArchivePath)) { Fail 'archive is missing' }
  if ([string]::IsNullOrWhiteSpace($ExpectedHash)) { Fail 'ExpectedArchiveSha256 is required for Verify and Restore' }
  $actual = Get-Sha256 $ArchivePath
  if ($actual -ne $ExpectedHash.ToLowerInvariant()) { Fail 'archive SHA-256 mismatch' }
  $manifest = Read-Manifest
  if ($manifest.sha256 -ne $actual) { Fail 'manifest SHA-256 mismatch' }
  if ($manifest.inventory.Count -eq 0) { Fail 'manifest inventory is empty' }
  foreach ($fact in @('table_counts', 'active_profile', 'pending_actions', 'alembic_revision')) {
    if ($manifest.PSObject.Properties.Name -notcontains $fact) { Fail "manifest $fact is missing" }
  }
  if ($manifest.table_counts.PSObject.Properties.Count -eq 0) { Fail 'manifest table counts are empty' }
  if ([string]::IsNullOrWhiteSpace([string]$manifest.alembic_revision)) { Fail 'manifest Alembic revision is missing' }
  if ($ExpectedAlembicRevision -and $manifest.alembic_revision -ne $ExpectedAlembicRevision) { Fail 'Alembic revision mismatch' }
  return $manifest
}
function Get-SnapshotFacts([string]$MountPath = '/source') {
  $program = @"
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

path = Path('$MountPath/jobagent.db')
if not path.is_file():
    raise SystemExit('jobagent.db is missing from the source volume')
with tempfile.TemporaryDirectory() as temporary:
    scratch = Path(temporary) / 'jobagent.db'
    shutil.copy2(path, scratch)
    for suffix in ('-wal', '-shm'):
        sidecar = Path(f'{path}{suffix}')
        if sidecar.is_file():
            shutil.copy2(sidecar, Path(f'{scratch}{suffix}'))
    with sqlite3.connect(f'file:{scratch}?mode=ro', uri=True) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
        revision = connection.execute('SELECT version_num FROM alembic_version').fetchone()
        active = connection.execute("SELECT active_profile_id FROM workspace_state WHERE id = 'main'").fetchone()
        pending = connection.execute("SELECT COUNT(*) FROM profile_reextract_operations WHERE state IN ('running', 'review_ready')").fetchone()[0]
print(json.dumps({
    'table_counts': counts,
    'active_profile': None if active is None else active[0],
    'pending_actions': pending,
    'alembic_revision': '' if revision is None else revision[0],
}))
"@
  $json = $program | docker run --rm -i -v "${VolumeName}:${MountPath}:ro" python:3.13-alpine python -
  if ($LASTEXITCODE -ne 0) { Fail 'could not collect SQLite snapshot facts' }
  if ([string]::IsNullOrWhiteSpace(($json | Out-String))) { Fail 'SQLite snapshot facts output is empty' }
  try { return ($json | ConvertFrom-Json -ErrorAction Stop) } catch { Fail 'SQLite snapshot facts output is malformed JSON' }
}
function Get-LiveInventory {
  $inventory = docker run --rm -v "${VolumeName}:/target:ro" alpine:3.20 sh -c 'cd /target && find . -type f -print | sort' | Where-Object { $_ }
  Assert-NativeSucceeded 'live inventory collection'
  return @($inventory)
}
function Get-ComparableInventory([object[]]$LiveInventory, [object[]]$ManifestInventory) {
  $manifestEntries = @{}
  foreach ($entry in @($ManifestInventory)) { $manifestEntries[[string]$entry] = $true }
  return @($LiveInventory | Where-Object {
      $path = [string]$_
      $match = [regex]::Match($path, '^(?<base>.+)-(?<sidecar>wal|shm)$')
      -not ($match.Success -and $manifestEntries.ContainsKey($match.Groups['base'].Value))
    })
}

Assert-PrivatePath $ArchivePath
Assert-PrivatePath $ManifestPath
if ($ProjectName -ne 'jobagentlatest') { Fail 'ProjectName must be jobagentlatest' }
if ($ExpectedPurpose) {
  if ($ExpectedPurpose -ne 'plan18-rehearsal') { Fail 'clone purpose must be plan18-rehearsal' }
  if ($VolumeName -ne 'jobagentlatest_app_data_plan18_rehearsal') { Fail 'clone volume name mismatch' }
  if (-not [string]::IsNullOrWhiteSpace($ExpectedConsumer)) { Fail 'clone actions must not name an authoritative consumer' }
} else {
  if ($VolumeName -ne 'jobagentlatest_app_data') { Fail 'VolumeName must be jobagentlatest_app_data' }
  if ($ExpectedConsumer -ne 'jobagentlatest-backend-1') { Fail 'ExpectedConsumer must name the exact authoritative backend consumer' }
}
if ($Action -eq 'Restore' -and -not $ConfirmRestore) { Fail 'Restore requires -ConfirmRestore' }
if ($Action -ne 'Backup' -and [string]::IsNullOrWhiteSpace($ExpectedArchiveSha256)) { Fail 'ExpectedArchiveSha256 is required for Verify and Restore' }
$volume = Get-Volume
if ($ExpectedPurpose) { Assert-CloneVolume $volume } else { Assert-AuthoritativeVolume $volume; Assert-Consumer $ExpectedConsumer | Out-Null }

if ($Action -eq 'Backup') {
  $backend = docker inspect $ExpectedConsumer | ConvertFrom-Json | Select-Object -First 1
  if ($backend.State.Running) { Fail 'backend must be stopped before Backup' }
  $directory = Split-Path -Parent $ArchivePath
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
  docker run --rm -v "${VolumeName}:/source:ro" -v "${directory}:/backup" alpine:3.20 sh -c "cd /source && tar cf /backup/$([IO.Path]::GetFileName($ArchivePath)) ."
  Assert-NativeSucceeded 'Docker archive creation'
  $inventory = docker run --rm -v "${VolumeName}:/source:ro" alpine:3.20 sh -c 'cd /source && find . -type f -print | sort' | Where-Object { $_ }
  Assert-NativeSucceeded 'Docker inventory collection'
  $sqliteFiles = $inventory | Where-Object { $_ -match '\.(db|sqlite)(-wal|-shm)?$' }
  $facts = Get-SnapshotFacts
  if ($ExpectedAlembicRevision -and $facts.alembic_revision -ne $ExpectedAlembicRevision) { Fail 'Alembic revision mismatch' }
  $manifest = [ordered]@{ sha256 = Get-Sha256 $ArchivePath; size_bytes = (Get-Item -LiteralPath $ArchivePath).Length; inventory = @($inventory); sqlite_sidecars = @($sqliteFiles); table_counts = $facts.table_counts; active_profile = $facts.active_profile; pending_actions = $facts.pending_actions; alembic_revision = $facts.alembic_revision }
  $manifest | ConvertTo-Json -Depth 5 | Set-Content -NoNewline -LiteralPath $ManifestPath
  return
}

$manifest = Assert-Archive $ExpectedArchiveSha256
if ($Action -eq 'Verify') {
  $liveInventory = Get-LiveInventory
  $comparableInventory = Get-ComparableInventory $liveInventory $manifest.inventory
  if ((@($comparableInventory | Sort-Object) -join "`n") -ne (@($manifest.inventory | Sort-Object) -join "`n")) { Fail 'live volume inventory mismatch' }
  $liveFacts = Get-SnapshotFacts '/target'
  if ($liveFacts.alembic_revision -ne $manifest.alembic_revision) { Fail 'live Alembic revision mismatch' }
  return
}
$temporary = Join-Path ([IO.Path]::GetDirectoryName($ArchivePath)) ("restore-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
  tar -xf $ArchivePath -C $temporary
  Assert-NativeSucceeded 'archive extraction'
  $actualInventory = Get-ChildItem -Recurse -File $temporary | ForEach-Object { '.' + $_.FullName.Substring($temporary.Length).Replace('\', '/') } | Sort-Object
  if ((@($actualInventory) -join "`n") -ne (@($manifest.inventory | Sort-Object) -join "`n")) { Fail 'temporary restore inventory mismatch' }
  docker run --rm -v "${VolumeName}:/target" -v "${temporary}:/restore:ro" alpine:3.20 sh -c 'rm -rf /target/* /target/.[!.]* /target/..?*; cp -a /restore/. /target/'
  Assert-NativeSucceeded 'Docker replacement'
} finally { Remove-Item -Recurse -Force -LiteralPath $temporary -ErrorAction SilentlyContinue }
