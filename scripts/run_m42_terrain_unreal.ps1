param([Parameter(Mandatory = $true)][string]$LogPath)
$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $repository "integrations\unreal\ArtFlowBridgeHost\ArtFlowBridgeHost.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$script = (Join-Path $repository "integrations\unreal\apply_biome_terrain_candidate.py").Replace("\", "/")
$resolvedLog = [System.IO.Path]::GetFullPath($LogPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedLog) | Out-Null
$process = Start-Process -FilePath $editor -ArgumentList @($project, "-unattended", "-nop4", "-nosplash", "-NoSound", "-NoCrashDialog", "-nocrashreports", "-ExecCmds=`"py $script`"", "-abslog=$resolvedLog") -PassThru -Wait -WindowStyle Hidden
if ($process.ExitCode -ne 0) { exit $process.ExitCode }
$receipt = Join-Path $repository "artifacts\goal\m42-s1-terrain-biome\unreal-biome-terrain-receipt.json"
if (-not (Test-Path -LiteralPath $receipt)) { throw "Terrain receipt was not produced; inspect $resolvedLog" }
