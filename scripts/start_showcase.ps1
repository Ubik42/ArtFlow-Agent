param(
    [int]$Port = 8798,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WebRoot = Join-Path $ProjectRoot "web"
$VenvRoot = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VenvRoot "Scripts\python.exe"

function Assert-CommandSucceeded([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step 失败，退出码 $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $WebRoot "node_modules"))) {
    Push-Location $WebRoot
    try {
        npm ci
        Assert-CommandSucceeded "安装前端依赖"
    }
    finally {
        Pop-Location
    }
}

Push-Location $WebRoot
try {
    npm run build
    Assert-CommandSucceeded "构建 Scene Lab"
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $Python)) {
    python -m venv $VenvRoot
    Assert-CommandSucceeded "创建 Python 虚拟环境"
}

$PreviousErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "import artflow_agent" 2>$null
$ImportExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorAction
if ($ImportExitCode -ne 0) {
    & $Python -m pip install -e $ProjectRoot
    Assert-CommandSucceeded "安装 ArtFlow Python 依赖"
}

Push-Location $ProjectRoot
try {
    $Arguments = @("scripts/run_showcase.py", "--port", "$Port")
    if (-not $NoBrowser) {
        $Arguments += "--open-browser"
    }
    & $Python @Arguments
    $ServerExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $ServerExitCode
