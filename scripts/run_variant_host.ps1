param(
    [Parameter(Mandatory)][ValidateSet('inspect','publish','review')][string]$Action,
    [Parameter(Mandatory)][string]$Request,
    [Parameter(Mandatory)][string]$Result
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskRequest = (Resolve-Path -LiteralPath $Request).Path
$taskResult = [IO.Path]::GetFullPath($Result)
foreach ($taskPath in @($taskRequest, $taskResult)) {
    if (-not $taskPath.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Request and result must stay inside this project.'
    }
}
$taskNames = @{ inspect='inspect_routed_publish_candidate.py'; publish='publish_session_candidate.py'; review='review_published_variant.py' }
$taskScript = Join-Path $taskRoot ('integrations/unreal/ArtFlowSceneBridge/Content/Python/' + $taskNames[$Action])
$taskProject = Join-Path $taskRoot 'integrations/unreal/ArtFlowBridgeHost/ArtFlowBridgeHost.uproject'
$taskLog = [IO.Path]::ChangeExtension($taskResult, '.log')
$taskEnvNames = @('ARTFLOW_REPO_ROOT','ARTFLOW_SCENE_PUBLISH_REQUEST','ARTFLOW_SCENE_PUBLISH_RESULT','ARTFLOW_SCENE_REVIEW_REQUEST','ARTFLOW_SCENE_REVIEW_RESULT','ARTFLOW_CURRENT_VARIANT_ORIGIN','ARTFLOW_CURRENT_VARIANT_RUN')
$taskPrevious = @{}
foreach ($taskName in $taskEnvNames) { $taskPrevious[$taskName] = [Environment]::GetEnvironmentVariable($taskName) }
try {
    $env:ARTFLOW_REPO_ROOT=$taskRoot
    $env:ARTFLOW_CURRENT_VARIANT_ORIGIN=$null
    $env:ARTFLOW_CURRENT_VARIANT_RUN=$null
    $env:ARTFLOW_SCENE_PUBLISH_REQUEST=$taskRequest
    $env:ARTFLOW_SCENE_PUBLISH_RESULT=$taskResult
    $env:ARTFLOW_SCENE_REVIEW_REQUEST=$taskRequest
    $env:ARTFLOW_SCENE_REVIEW_RESULT=$taskResult
    $taskProcess=Start-Process -FilePath 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' -ArgumentList @(
        ('"'+$taskProject+'"'), '-run=pythonscript', ('-script="'+$taskScript+'"'),
        '-unattended','-nullrhi','-nosound','-nop4',('-abslog="'+$taskLog+'"')
    ) -WindowStyle Hidden -PassThru
    Write-Output "Owned UE process $($taskProcess.Id): $Action"
    if (-not $taskProcess.WaitForExit(90000)) {
        $taskProcess.Kill()
        throw "UE timed out; inspect $taskLog before retry."
    }
    if ($taskProcess.ExitCode -ne 0) {
        Get-Content -LiteralPath $taskLog | Select-String 'LogPython: Error:'
        throw "UE failed with exit code $($taskProcess.ExitCode)."
    }
    if ($Action -ne 'inspect') { Get-Content -LiteralPath $taskResult }
} finally {
    foreach ($taskName in $taskEnvNames) { [Environment]::SetEnvironmentVariable($taskName,$taskPrevious[$taskName]) }
}
