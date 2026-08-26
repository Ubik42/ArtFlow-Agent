[CmdletBinding()]
param(
    [ValidateSet("Status", "Next", "Resume", "Doctor", "Audit", "Validate")]
    [string]$Action = "Status"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$statePath = Join-Path $repoRoot "config\goal-state.json"
$schemaPath = Join-Path $repoRoot "config\goal-state.schema.json"
$auditScript = Join-Path $repoRoot "scripts\validate_goal_state.py"

function Read-GoalState {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        throw "Goal state is missing: $statePath"
    }
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.schemaVersion -ne "codex-goal-state@2.0.0") {
        throw "Unsupported goal state schema: $($state.schemaVersion)"
    }
    return $state
}

function Invoke-GoalAudit {
    if (-not (Test-Path -LiteralPath $schemaPath -PathType Leaf)) {
        throw "Goal state schema is missing: $schemaPath"
    }
    if (-not (Test-Path -LiteralPath $auditScript -PathType Leaf)) {
        throw "Goal audit script is missing: $auditScript"
    }
    $output = & python $auditScript --repo-root $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Goal state audit failed: $output"
    }
    return $output
}

function Show-Status($state) {
    Write-Output "Goal: $($state.goalId)"
    Write-Output "Status: $($state.status)"
    Write-Output "State revision: $($state.stateRevision)"
    Write-Output "Strategy: $($state.strategyVersion)"
    Write-Output "Current milestone: $($state.currentMilestone)"
    Write-Output "Next slice: $($state.nextSlice.id) - $($state.nextSlice.title)"
    Write-Output "Risk / evidence target: $($state.nextSlice.risk) / $($state.nextSlice.evidenceTarget)"
    Write-Output "Requires real hosts: $($state.nextSlice.requiresRealHosts)"
    Write-Output "Evidence ceiling: $($state.evidenceCeiling)"
    Write-Output "Last checkpoint: $($state.lastCheckpoint)"
    Write-Output ""
    $state.milestones | Select-Object id, status, title | Format-Table -AutoSize
    if (@($state.manualTracks).Count -gt 0) {
        Write-Output "Manual tracks:"
        $state.manualTracks | Select-Object id, status, blocking, title | Format-Table -AutoSize
    }
    Write-Output "Git status:"
    git -C $repoRoot status --short
    if ($LASTEXITCODE -ne 0) { throw "git status failed" }
}

function Show-Next($state) {
    Write-Output "$($state.nextSlice.id): $($state.nextSlice.title)"
    Write-Output $state.nextSlice.outcome
    Write-Output "Risk: $($state.nextSlice.risk)"
    Write-Output "Evidence target: $($state.nextSlice.evidenceTarget)"
    Write-Output "Requires real hosts: $($state.nextSlice.requiresRealHosts)"
    Write-Output ""
    Write-Output "Allowed paths:"
    @($state.nextSlice.allowedPaths) | ForEach-Object { Write-Output "  - $_" }
    Write-Output "Non-goals:"
    @($state.nextSlice.nonGoals) | ForEach-Object { Write-Output "  - $_" }
    Write-Output "Acceptance:"
    @($state.nextSlice.acceptance) | ForEach-Object { Write-Output "  - $_" }
    Write-Output "Stop conditions:"
    @($state.nextSlice.stopConditions) | ForEach-Object { Write-Output "  - $_" }
    Write-Output "Validation (reviewed fixed entrypoints; never dynamically executed):"
    @($state.nextSlice.validationCommands) | ForEach-Object { Write-Output "  - $_" }
}

function Show-Resume($state) {
    Write-Output "Recovered durable development state"
    Write-Output "Objective: $($state.objective)"
    Write-Output "Checkpoint: $($state.lastCheckpoint)"
    Write-Output "Continue: $($state.nextSlice.id) - $($state.nextSlice.title)"
    if ($state.currentBlocker) {
        Write-Output "Blocker: $($state.currentBlocker.code)"
        Write-Output "Resume condition: $($state.currentBlocker.resumeCondition)"
    } else {
        Write-Output "Blocker: none"
    }
    $nonBlocking = @($state.manualTracks | Where-Object { -not $_.blocking -and $_.status -ne "completed" })
    if ($nonBlocking.Count -gt 0) {
        Write-Output "Non-blocking manual tracks: $($nonBlocking.id -join ', ')"
    }
    Write-Output "Run Doctor before implementation. Work only inside nextSlice.allowedPaths."
}

function Resolve-Requirement($requirement) {
    switch ($requirement.kind) {
        "command" {
            $command = Get-Command $requirement.value -ErrorAction SilentlyContinue
            return [PSCustomObject]@{ Id = $requirement.id; Ready = ($null -ne $command); Detail = $(if ($command) { $command.Source } else { "missing command: $($requirement.value)" }); Required = $requirement.required }
        }
        "environment" {
            $value = [Environment]::GetEnvironmentVariable($requirement.value)
            return [PSCustomObject]@{ Id = $requirement.id; Ready = (-not [string]::IsNullOrWhiteSpace($value)); Detail = $(if ($value) { "configured" } else { "missing environment variable: $($requirement.value)" }); Required = $requirement.required }
        }
        "repo_path" {
            $path = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $requirement.value))
            $ready = $path.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $path)
            return [PSCustomObject]@{ Id = $requirement.id; Ready = $ready; Detail = $(if ($ready) { "ready" } else { "missing repository requirement" }); Required = $requirement.required }
        }
        "sibling_path" {
            $workspaceRoot = Split-Path -Parent $repoRoot
            $path = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot $requirement.value))
            $ready = $path.StartsWith($workspaceRoot, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $path)
            return [PSCustomObject]@{ Id = $requirement.id; Ready = $ready; Detail = $(if ($ready) { "ready" } else { "missing sibling requirement" }); Required = $requirement.required }
        }
        default { throw "Unsupported environment requirement kind: $($requirement.kind)" }
    }
}

function Invoke-Doctor($state) {
    $audit = Invoke-GoalAudit
    Write-Output "Goal state audit: passed"
    $results = @($state.nextSlice.environmentRequirements | ForEach-Object { Resolve-Requirement $_ })
    $results | Format-Table Id, Ready, Required, Detail -AutoSize
    $failed = @($results | Where-Object { $_.Required -and -not $_.Ready })

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $pythonVersion = (& python -c "import platform; print(platform.python_version())").Trim()
        Write-Output "Python version: $pythonVersion"
        $parts = $pythonVersion.Split(".")
        if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
            $failed += [PSCustomObject]@{ Id = "python-version"; Ready = $false; Required = $true; Detail = "Python 3.11+ required" }
        }
    }
    if ($failed.Count -gt 0) {
        throw "Doctor found missing or incompatible requirements: $($failed.Id -join ', ')"
    }
    Write-Output "Doctor passed for slice $($state.nextSlice.id)"
}

$state = Read-GoalState
switch ($Action) {
    "Status" { Invoke-GoalAudit | Out-Null; Show-Status $state }
    "Next" { Invoke-GoalAudit | Out-Null; Show-Next $state }
    "Resume" { Invoke-GoalAudit | Out-Null; Show-Resume $state }
    "Doctor" { Invoke-Doctor $state }
    "Audit" { Invoke-GoalAudit }
    "Validate" {
        Invoke-GoalAudit | Out-Null
        & (Join-Path $PSScriptRoot "validate.ps1") -Tier quick
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
