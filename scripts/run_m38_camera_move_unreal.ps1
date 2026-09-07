param([Parameter(Mandatory = $true)][string]$LogPath)
$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $repository "integrations\unreal\ArtFlowBridgeHost\ArtFlowBridgeHost.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$script = Join-Path $repository "integrations\unreal\apply_camera_move_sequence.py"
$scriptArg = $script.Replace("\", "/")
$resolvedLog = [System.IO.Path]::GetFullPath($LogPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedLog) | Out-Null
$before = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $editor
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
@(
    $project,
    "-unattended",
    "-nop4",
    "-nosplash",
    "-NoSound",
    "-NoCrashDialog",
    "-nocrashreports",
    "-ExecCmds=py $scriptArg",
    "-abslog=$resolvedLog"
) | ForEach-Object { [void]$startInfo.ArgumentList.Add($_) }
$process = [System.Diagnostics.Process]::Start($startInfo)
$process.WaitForExit()
$after = @(Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
[pscustomobject]@{pid=$process.Id;exit_code=$process.ExitCode;exited=$process.HasExited;prior_pids=$before;surviving_prior_pids=@($before|Where-Object{$after -contains $_});log_path=$resolvedLog}|ConvertTo-Json -Compress
if ($process.ExitCode -ne 0) { exit $process.ExitCode }
$receipt = Join-Path $repository "artifacts\goal\m38-s1-camera-move\unreal-camera-move-receipt.json"
if (-not (Test-Path -LiteralPath $receipt)) { throw "Camera-move receipt was not produced; inspect $resolvedLog" }
