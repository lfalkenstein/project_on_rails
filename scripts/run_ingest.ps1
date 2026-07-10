# Ingest-only cycle, meant to be called by Windows Task Scheduler on a short
# timer (e.g. every 5 min). Does NOT run dbt - rebuild models separately/on demand.
# Appends timestamped output to logs\ingest.log so scheduled runs are debuggable.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py      = Join-Path $repo ".venv\Scripts\python.exe"
$logDir  = Join-Path $repo "logs"
$logFile = Join-Path $logDir "ingest.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
try {
    $out = & $py -m ingest 2>&1 | Out-String
    Add-Content -Path $logFile -Value "[$stamp] OK`n$out"
}
catch {
    Add-Content -Path $logFile -Value "[$stamp] FAILED: $_"
    throw
}
