param([Parameter(Mandatory = $true)][string]$LogPath)
$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $repository "integrations\unreal\ArtFlowBridgeHost\ArtFlowBridgeHost.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$script = Join-Path $repository "integrations\unreal\apply_set_dressing_candidate.py"
$resolvedLog = [System.IO.Path]::GetFullPath($LogPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedLog) | Out-Null
$before = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$process = Start-Process -FilePath $editor -ArgumentList @($project, "-unattended", "-nop4", "-nosplash", "-NoSound", "-NoCrashDialog", "-nocrashreports", "-ExecutePythonScript=$script", "-abslog=$resolvedLog") -PassThru -Wait -WindowStyle Hidden
$after = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
[pscustomobject]@{pid=$process.Id;exit_code=$process.ExitCode;exited=$process.HasExited;prior_pids=$before;surviving_prior_pids=@($before|Where-Object{$after -contains $_});log_path=$resolvedLog}|ConvertTo-Json -Compress
if ($process.ExitCode -ne 0) { exit $process.ExitCode }
