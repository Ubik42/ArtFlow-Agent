param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("publish", "review")]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$LogPath,

    [int]$Port = 8804
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $repository "integrations\unreal\ArtFlowBridgeHost\ArtFlowBridgeHost.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$script = if ($Action -eq "publish") {
    Join-Path $repository "integrations\unreal\publish_session_candidate.py"
} else {
    Join-Path $repository "integrations\unreal\review_published_variant.py"
}
$resolvedLog = [System.IO.Path]::GetFullPath($LogPath)
$logDirectory = Split-Path -Parent $resolvedLog
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

$env:ARTFLOW_REPO_ROOT = $repository
$env:ARTFLOW_CURRENT_VARIANT_ORIGIN = "http://127.0.0.1:$Port"
$env:ARTFLOW_CURRENT_VARIANT_RUN = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"

$arguments = @(
    $project,
    "-unattended",
    "-nop4",
    "-nosplash",
    "-NoSound",
    "-ExecutePythonScript=$script",
    "-abslog=$resolvedLog"
)
$process = Start-Process `
    -FilePath $editor `
    -ArgumentList $arguments `
    -PassThru `
    -Wait `
    -WindowStyle Hidden

[pscustomobject]@{
    action = $Action
    pid = $process.Id
    exit_code = $process.ExitCode
    exited = $process.HasExited
    log_path = $resolvedLog
} | ConvertTo-Json -Compress

if ($process.ExitCode -ne 0) {
    exit $process.ExitCode
}
