param(
    [string]$LinkPath = 'C:\abaqus-614-mcp-suite',
    [string]$PythonCommand = 'python'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (Test-Path $LinkPath) {
    $item = Get-Item $LinkPath -Force
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Path exists and is not a junction: $LinkPath"
    }
    Write-Host "Junction already exists: $LinkPath"
} else {
    New-Item -ItemType Junction -Path $LinkPath -Target $repoRoot | Out-Null
    Write-Host "Created junction: $LinkPath -> $repoRoot"
}

$serverPath = (Join-Path $LinkPath 'abaqus-docs-mcp\mcp_server.py').Replace('\', '/')
$indexPath = (Join-Path $LinkPath '.local\abaqus-help-index\index.jsonl').Replace('\', '/')
$embeddingsPath = (Join-Path $LinkPath '.local\abaqus-help-index\embeddings.jsonl').Replace('\', '/')

Write-Host ""
Write-Host "Codex MCP config:"

$config = [ordered]@{
    mcpServers = [ordered]@{
        'abaqus-docs' = [ordered]@{
            command = $PythonCommand
            args = @($serverPath)
            env = [ordered]@{
                ABAQUS_HELP_INDEX = $indexPath
                ABAQUS_HELP_EMBEDDINGS = $embeddingsPath
                ABAQUS_HELP_EMBED_MODEL = 'BAAI/bge-small-en-v1.5'
            }
        }
    }
}

$config | ConvertTo-Json -Depth 8
