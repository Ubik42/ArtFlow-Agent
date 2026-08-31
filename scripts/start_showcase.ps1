param(
    [int]$Port = 8798,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WebRoot = Join-Path $ProjectRoot "web"

if (-not (Test-Path -LiteralPath (Join-Path $WebRoot "node_modules"))) {
    Push-Location $WebRoot
    try {
        npm ci
    }
    finally {
        Pop-Location
    }
}

Push-Location $WebRoot
try {
    npm run build
}
finally {
    Pop-Location
}

Push-Location $ProjectRoot
try {
    $Arguments = @("run", "python", "scripts/run_showcase.py", "--port", "$Port")
    if (-not $NoBrowser) {
        $Arguments += "--open-browser"
    }
    & uv @Arguments
}
finally {
    Pop-Location
}
