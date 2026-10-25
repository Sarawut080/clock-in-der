<#
.SYNOPSIS
  Back up the database (pg_dump) and the uploads/ photos into backups\<yyyyMMdd-HHmm>\, then prune old sets.

.DESCRIPTION
  Reads DATABASE_URL from .env. The password goes to pg_dump through the PGPASSWORD variable of this process
  only: it is never printed, logged or written to a file.
  Both parts are needed together: a dump alone points at photos that are not there, because photos live on
  disk and not in the database.
  The dump is verified with pg_restore --list; an unreadable dump makes the script exit 1 so Task Scheduler
  shows the run as failed.

  NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI and Thai text
  would break the script (see README, Gotchas).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 -KeepDays 60 -OutDir E:\backups
#>
param(
    [string]$OutDir = (Join-Path $PSScriptRoot "..\backups"),
    [int]$KeepDays = 30,
    # bin folder of the PostgreSQL that DATABASE_URL points to (17 = port 5433, 18 = port 5432)
    [string]$PgBin = "C:\Program Files\PostgreSQL\17\bin"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Get-EnvValue([string]$name) {
    $line = Get-Content -Encoding utf8 (Join-Path $root ".env") |
        Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -First 1
    if (-not $line) { throw "$name not found in .env" }
    return ($line -replace "^\s*$name\s*=\s*", "").Trim()
}

$url = [uri](Get-EnvValue "DATABASE_URL")
$userInfo = $url.UserInfo.Split(":", 2)
$dbUser = [uri]::UnescapeDataString($userInfo[0])
$dbPass = [uri]::UnescapeDataString($userInfo[1])
$dbName = $url.AbsolutePath.TrimStart("/")
$pgDump = Join-Path $PgBin "pg_dump.exe"
$pgRestore = Join-Path $PgBin "pg_restore.exe"
foreach ($exe in $pgDump, $pgRestore) {
    if (-not (Test-Path $exe)) { throw "$exe not found - set -PgBin to the installed PostgreSQL bin folder" }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$dest = Join-Path $OutDir $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$dumpFile = Join-Path $dest "$dbName.dump"

$env:PGPASSWORD = $dbPass
try {
    # -Fc = custom format (compressed, restorable with pg_restore, can restore single tables)
    & $pgDump -h $url.Host -p $url.Port -U $dbUser -d $dbName -Fc -f $dumpFile
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed (exit code $LASTEXITCODE)" }
    & $pgRestore --list $dumpFile | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "dump verification failed - do not trust this backup" }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

# Photos: additive copy (no mirror). If a photo is lost locally by mistake, the backup copy must survive.
$uploads = Join-Path $root "uploads"
if (Test-Path $uploads) {
    robocopy $uploads (Join-Path $dest "uploads") /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copying photos failed (robocopy exit code $LASTEXITCODE)" }
}

# Prune: only folders named like a stamp of this script, so nothing else under OutDir is ever touched.
Get-ChildItem $OutDir -Directory |
    Where-Object { $_.Name -match "^\d{8}-\d{4}$" -and $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
    ForEach-Object { Remove-Item -Recurse -Force $_.FullName; Write-Host "pruned old set: $($_.Name)" }

$mb = [math]::Round((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 2)
Write-Host "backup OK: $dest ($mb MB), dump verified"
