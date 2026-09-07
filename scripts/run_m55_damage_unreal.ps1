param([Parameter(Mandatory = $true)][string]$LogPath)
$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $repository "integrations\unreal\ArtFlowBridgeHost\ArtFlowBridgeHost.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$script = (Join-Path $repository "integrations\unreal\apply_damage_variant_candidate.py").Replace("\", "/")
$resolvedLog = [System.IO.Path]::GetFullPath($LogPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedLog) | Out-Null
$before = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$process = Start-Process -FilePath $editor -ArgumentList @(
    $project,
    "-unattended",
    "-nop4",
    "-nosplash",
    "-NoSound",
    "-NoCrashDialog",
    "-nocrashreports",
    "-ExecCmds=`"py $script`"",
    "-abslog=$resolvedLog"
) -PassThru -Wait -WindowStyle Hidden
$after = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
if ($process.ExitCode -ne 0) { exit $process.ExitCode }
$receipt = Join-Path $repository "artifacts\goal\m55-s1-damage-variant\unreal-damage-variant-receipt.json"
if (-not (Test-Path -LiteralPath $receipt)) { throw "Damage receipt was not produced; inspect $resolvedLog" }
if (@($before | Where-Object { $_ -notin $after }).Count -ne 0) { throw "A pre-existing Unreal process changed during validation" }
