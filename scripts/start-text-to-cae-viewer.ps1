param(
    [int]$Port = 4178,
    [string]$AbaqusCommand = "D:\abaqus\Commands\abaqus.bat"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ViewerDir = Join-Path $RepoRoot "text-to-cae\viewer"

if (-not (Test-Path -LiteralPath $ViewerDir)) {
    throw "Viewer directory not found: $ViewerDir"
}

Push-Location $ViewerDir
try {
    if (-not (Test-Path -LiteralPath "node_modules")) {
        npm.cmd ci
    }

    $env:VIEWER_PORT = [string]$Port
    $env:ABAQUS_COMMAND = $AbaqusCommand
    npm.cmd run dev
}
finally {
    Pop-Location
}

