param(
    [string]$IndexDir = "",
    [string]$Model = "BAAI/bge-small-en-v1.5",
    [int]$BatchSize = 32,
    [string]$PythonCommand = "python",
    [switch]$AllowDownload
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $IndexDir) {
    $IndexDir = Join-Path $RepoRoot ".local\abaqus-help-index"
}

$IndexPath = Join-Path $IndexDir "index.jsonl"
$OutPath = Join-Path $IndexDir "embeddings.jsonl"
$EmbedTool = Join-Path $RepoRoot "tools\abaqus_docs_embed.py"

if (-not (Test-Path -LiteralPath $IndexPath)) {
    throw "Index not found: $IndexPath. Run scripts\index-abaqus-help.ps1 first."
}

$argsList = @(
    $EmbedTool,
    "build",
    "--index", $IndexPath,
    "--output", $OutPath,
    "--model", $Model,
    "--batch-size", [string]$BatchSize
)

if ($AllowDownload) {
    $argsList += "--allow-download"
} else {
    $argsList += "--local-files-only"
}

& $PythonCommand @argsList
