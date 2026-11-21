# Everything, start to finish. Needs Python 3.11+ and Java 17.
#   .\run.ps1              1,500 Illinois patients, seed 7 (about 20 minutes, 6 GB)
#   .\run.ps1 -Size 150    a quick look
param([int]$Size = 1500, [int]$Seed = 7, [string]$Label = "il-7")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    python -m venv .venv
    .\.venv\Scripts\python -m pip install --quiet --upgrade pip
    .\.venv\Scripts\python -m pip install --quiet -e ".[dev]"
}
.\.venv\Scripts\python -m carelake all --size $Size --seed $Seed --label $Label --fresh
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ""
Write-Host "page:  .\.venv\Scripts\python -m http.server -d web 8080"
