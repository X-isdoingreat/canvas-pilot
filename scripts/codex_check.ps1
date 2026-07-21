param(
  [string]$Batch = "B2"
)

$ErrorActionPreference = "Stop"

if ($Batch -ne "B2") {
  Write-Error "Only B2 is implemented in scripts/codex_check.ps1"
}

Write-Host "Running Codex hook tests for $Batch"
python scripts/codex_check.py --batch $Batch
