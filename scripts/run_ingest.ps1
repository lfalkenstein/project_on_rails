# Ingest-only cycle, meant to be called by Windows Task Scheduler on a short
# timer (e.g. every 5 min). Does NOT run dbt - rebuild models separately/on demand.
# Appends timestamped output to logs\ingest.log so scheduled runs are debuggable.

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py      = Join-Path $repo ".venv\Scripts\python.exe"
$logDir  = Join-Path $repo "logs"
$logFile = Join-Path $logDir "ingest.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Capture stdout+stderr together and decide success by exit code, so the full
# Python message (e.g. a DuckDB file-lock error) is always logged - not masked
# by PowerShell's NativeCommandError wrapper.
$out  = & $py -m ingest 2>&1 | Out-String
$code = $LASTEXITCODE

if ($code -eq 0) {
    Add-Content -Path $logFile -Value "[$stamp] OK`n$out"
}
else {
    Add-Content -Path $logFile -Value "[$stamp] FAILED (exit $code)`n$out"
    Write-Warning "ingest failed (exit $code) - see $logFile"
    exit $code
}
