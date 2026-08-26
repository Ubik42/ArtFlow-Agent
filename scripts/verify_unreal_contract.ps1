param(
    [string]$EngineRoot = "",
    [string]$SceneFixture = ""
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$FixtureSource = Join-Path $RepositoryRoot "contract-tests\unreal\scene_constraint_fixture.cpp"
if (-not $SceneFixture) {
    $SceneFixture = Join-Path $RepositoryRoot "examples\scene-constraint-package.example.json"
}
if (-not (Test-Path -LiteralPath $SceneFixture -PathType Leaf)) {
    throw "Scene fixture was not found: $SceneFixture"
}
$BuildRoot = Join-Path $RepositoryRoot "contract-tests\unreal\build"

if (-not $EngineRoot) {
    $EngineRoot = Get-ChildItem "C:\Program Files\Epic Games" -Directory -Filter "UE_*" |
        Sort-Object Name -Descending |
        Where-Object {
            Test-Path (Join-Path $_.FullName "Engine\Source\ThirdParty\RapidJSON\1.1.0\rapidjson\document.h")
        } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $EngineRoot) {
    throw "No Unreal Engine installation with RapidJSON headers was found."
}

$RapidJsonRoot = Join-Path $EngineRoot "Engine\Source\ThirdParty\RapidJSON\1.1.0"
$VsWhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $VsWhere)) {
    throw "Visual Studio Installer vswhere.exe was not found."
}
$VisualStudioRoot = & $VsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$VcVars = Join-Path $VisualStudioRoot "VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $VcVars)) {
    throw "Visual C++ x64 build environment was not found."
}

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
$Executable = Join-Path $BuildRoot "scene_constraint_fixture.exe"
$ObjectFile = Join-Path $BuildRoot "scene_constraint_fixture.obj"
$Compile = '"{0}" && cl.exe /nologo /std:c++17 /EHsc /W4 /I"{1}" "{2}" /Fo"{3}" /Fe"{4}"' -f $VcVars, $RapidJsonRoot, $FixtureSource, $ObjectFile, $Executable
& cmd.exe /d /s /c $Compile
if ($LASTEXITCODE -ne 0) {
    throw "Unreal-side contract fixture failed to compile."
}

& $Executable $SceneFixture
if ($LASTEXITCODE -ne 0) {
    throw "Unreal-side contract fixture failed validation."
}
