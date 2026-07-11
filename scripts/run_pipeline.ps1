# Runs one full collection cycle: ingest -> dbt.
# Designed to be called by Windows Task Scheduler on a timer.
# It resolves paths relative to this script, so it works from any CWD.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py  = Join-Path $repo ".venv\Scripts\python.exe"
$dbt = Join-Path $repo ".venv\Scripts\dbt.exe"

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Output "[$stamp] starting pipeline in $repo"

& $py -m ingest
& $dbt run --project-dir dbt_project --profiles-dir dbt_project

Write-Output "[$stamp] pipeline finished"
