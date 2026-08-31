param(
    [int]$Port = 8190,
    [string]$RuntimeName = "m13-comfy-host"
)

$ErrorActionPreference = "Stop"
$comfyRoot = "D:\3D\_tools\_reference\_AI\ComfyUI"
$productionNodes = "D:\3D\_tools\ComfyUI-Production-Nodes"
$runtimeRoot = Join-Path $PSScriptRoot "..\artifacts\runtime\$RuntimeName"
$endpoint = "http://127.0.0.1:$Port"

try {
    $stats = Invoke-RestMethod "$endpoint/system_stats" -TimeoutSec 2
    [pscustomobject]@{
        status = "already_running"
        endpoint = $endpoint
        device = $stats.devices[0].name
        comfyui = $stats.system.comfyui_version
    } | ConvertTo-Json
    exit 0
} catch {
    # A closed local port is the expected precondition.
}

foreach ($name in @("custom_nodes", "input", "output", "temp", "user")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $runtimeRoot $name) | Out-Null
}
$nodeDestination = Join-Path $runtimeRoot "custom_nodes\ComfyUI-Production-Nodes"
if (-not (Test-Path -LiteralPath $nodeDestination)) {
    Copy-Item -LiteralPath $productionNodes -Destination $nodeDestination -Recurse -Force
}

$python = Join-Path $comfyRoot ".venv\Scripts\python.exe"
$stdout = Join-Path $runtimeRoot "stdout.log"
$stderr = Join-Path $runtimeRoot "stderr.log"
$arguments = @(
    "main.py",
    "--listen", "127.0.0.1",
    "--port", "$Port",
    "--base-directory", $runtimeRoot,
    "--extra-model-paths-config", (Join-Path $comfyRoot "extra_model_paths.yaml"),
    "--database-url", "sqlite:///:memory:",
    "--preview-method", "none"
)
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $comfyRoot `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Set-Content -LiteralPath (Join-Path $runtimeRoot "owned-pid.txt") -Value $process.Id

$stats = $null
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $stats = Invoke-RestMethod "$endpoint/system_stats" -TimeoutSec 2
        break
    } catch {
        if ($process.HasExited) { break }
    }
}
if ($null -eq $stats) {
    Get-Content -LiteralPath $stderr -Tail 80
    throw "ArtFlow isolated ComfyUI host failed to start (PID $($process.Id))."
}

[pscustomobject]@{
    status = "started"
    pid = $process.Id
    endpoint = $endpoint
    device = $stats.devices[0].name
    comfyui = $stats.system.comfyui_version
} | ConvertTo-Json
