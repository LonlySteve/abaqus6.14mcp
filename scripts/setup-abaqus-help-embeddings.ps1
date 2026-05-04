param(
    [string]$VenvPath = "",
    [string]$Model = "BAAI/bge-small-en-v1.5",
    [int]$BatchSize = 32,
    [switch]$BuildIndex,
    [switch]$AllowDownload
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $VenvPath) {
    $VenvPath = Join-Path $RepoRoot ".local\venvs\abaqus-docs-rag"
}

if (-not (Test-Path -LiteralPath $VenvPath)) {
    python -m venv $VenvPath --system-site-packages
    Write-Host "Created venv: $VenvPath"
} else {
    Write-Host "Venv already exists: $VenvPath"
}

$PythonPath = Join-Path $VenvPath "Scripts\python.exe"
& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install sentence-transformers

if ($BuildIndex) {
    $buildArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "build-abaqus-help-embeddings.ps1"),
        "-Model", $Model,
        "-BatchSize", [string]$BatchSize,
        "-PythonCommand", $PythonPath
    )
    if ($AllowDownload) {
        $buildArgs += "-AllowDownload"
    }
    powershell @buildArgs
}

Write-Host ""
Write-Host "Embedding Python:"
Write-Host $PythonPath
Write-Host ""
Write-Host "Build command:"
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-abaqus-help-embeddings.ps1 -PythonCommand `"$PythonPath`" -AllowDownload"
Write-Host ""
Write-Host "Search command:"
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help-embeddings.ps1 -PythonCommand `"$PythonPath`" -Query `"multi chip flexible board bending stress`" -Limit 5"
