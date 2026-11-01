param(
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunId,
    [ValidatePattern('^http://127\.0\.0\.1:[0-9]+$')][string]$Origin='http://127.0.0.1:8816'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskProject=Join-Path $taskRoot 'integrations/unreal/ArtFlowBridgeHost/ArtFlowBridgeHost.uproject'
$taskScript=Join-Path $taskRoot 'integrations/unreal/ArtFlowSceneBridge/Content/Python/publish_session_candidate.py'
$taskOutput=Join-Path $taskRoot 'artifacts/goal/m62-s1-native-publish'
New-Item -ItemType Directory -Force $taskOutput | Out-Null
$taskOldOrigin=$env:ARTFLOW_CURRENT_VARIANT_ORIGIN
$taskOldRun=$env:ARTFLOW_CURRENT_VARIANT_RUN
try {
    $env:ARTFLOW_CURRENT_VARIANT_ORIGIN=$Origin
    $env:ARTFLOW_CURRENT_VARIANT_RUN=$RunId
    $taskProcess=Start-Process -FilePath 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' -ArgumentList @(
      ('"'+$taskProject+'"'),'-run=pythonscript',('-script="'+$taskScript+'"'),'-unattended','-nullrhi','-nosound','-nop4',('-abslog="'+$taskOutput+'/publish.log"')
    ) -WindowStyle Hidden -PassThru
    @{pid=$taskProcess.Id;started=$taskProcess.StartTime.ToUniversalTime().ToString('o');run=$RunId}|ConvertTo-Json|Set-Content "$taskOutput/owned-process.json" -Encoding utf8
    Write-Output "Owned UE process $($taskProcess.Id): current publish with native inspection"
    $taskProcess.WaitForExit()
    if($taskProcess.ExitCode -ne 0){throw 'Current publish failed; inspect artifacts/goal/m62-s1-native-publish/publish.log'}
    Select-String "$taskOutput/publish.log" -Pattern 'ARTFLOW_ROUTED_FACTS|ARTFLOW_SESSION_PUBLISH'
} finally {
    $env:ARTFLOW_CURRENT_VARIANT_ORIGIN=$taskOldOrigin
    $env:ARTFLOW_CURRENT_VARIANT_RUN=$taskOldRun
}
