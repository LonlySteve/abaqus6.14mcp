param(
    [Parameter(Mandatory = $true)]
    [string]$Query,
    [string]$IndexDir = "",
    [string]$Model = "BAAI/bge-small-en-v1.5",
    [int]$Limit = 5,
    [switch]$Json,
    [switch]$AllowDownload
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $IndexDir) {
    $IndexDir = Join-Path $RepoRoot ".local\abaqus-help-index"
}

$EmbeddingsPath = Join-Path $IndexDir "embeddings.jsonl"
$EmbedTool = Join-Path $RepoRoot "tools\abaqus_docs_embed.py"

if (-not (Test-Path -LiteralPath $EmbeddingsPath)) {
    throw "Embeddings not found: $EmbeddingsPath. Run scripts\build-abaqus-help-embeddings.ps1 first."
}

$argsList = @(
    $EmbedTool,
    "search",
    $Query,
    "--embeddings", $EmbeddingsPath,
    "--model", $Model,
    "--limit", [string]$Limit
)
if ($Json) {
    $argsList += "--json"
}
if ($AllowDownload) {
    $argsList += "--allow-download"
} else {
    $argsList += "--local-files-only"
}

python @argsList
