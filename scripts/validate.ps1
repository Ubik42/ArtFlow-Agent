[CmdletBinding()]
param([ValidateSet("quick", "full")][string]$Tier = "quick")

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

& $python (Join-Path $PSScriptRoot "validate_goal_state.py") --repo-root $repoRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m pytest (Join-Path $repoRoot "tests") (Join-Path $PSScriptRoot "tests") -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Tier -eq "full") {
    & $python (Join-Path $PSScriptRoot "export_contract_schemas.py")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
