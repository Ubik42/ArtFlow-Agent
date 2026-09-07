param([Parameter(Mandatory = $true)][string]$LogPath)
$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $repository "integrations\unreal\ArtFlowBridgeHost\ArtFlowBridgeHost.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$script = (Join-Path $repository "integrations\unreal\apply_mechanism_rig_candidate.py").Replace("\", "/")
$resolvedLog = [System.IO.Path]::GetFullPath($LogPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedLog) | Out-Null
$before = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$process = Start-Process -FilePath $editor -ArgumentList @($project, "-unattended", "-nop4", "-nosplash", "-NoSound", "-NoCrashDialog", "-nocrashreports", "-ExecCmds=`"py $script`"", "-abslog=$resolvedLog") -PassThru -WindowStyle Hidden
$deadline = (Get-Date).AddMinutes(4)
while (-not $process.HasExited -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $process.Refresh()
}
if (-not $process.HasExited) {
    Stop-Process -Id $process.Id
    throw "Mechanism Unreal run timed out; inspect $resolvedLog"
}
$after = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
if ($process.ExitCode -ne 0) { exit $process.ExitCode }
$receipt = Join-Path $repository "artifacts\goal\m51-s1-mechanism-rig\unreal-mechanism-rig-receipt.json"
if (-not (Test-Path -LiteralPath $receipt)) { throw "Mechanism receipt was not produced; inspect $resolvedLog" }
if (@($before | Where-Object { $_ -notin $after }).Count -ne 0) { throw "A pre-existing Unreal process changed during validation" }
