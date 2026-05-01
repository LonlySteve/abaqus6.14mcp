param(
    [string]$McpHome = "C:\abaqus-mcp",
    [int]$TimeoutSec = 10
)

$ErrorActionPreference = "Stop"

$CommandDir = Join-Path $McpHome "commands"
$ResultDir = Join-Path $McpHome "results"
New-Item -ItemType Directory -Force -Path $CommandDir, $ResultDir | Out-Null

$Id = "ping_" + (Get-Date -Format "yyyyMMdd_HHmmss")
$CommandPath = Join-Path $CommandDir ("cmd_" + $Id + ".json")
$ResultPath = Join-Path $ResultDir ($Id + ".json")

$Command = @{
    id = $Id
    type = "ping"
    timestamp = [DateTimeOffset]::Now.ToUnixTimeSeconds()
}

$Command | ConvertTo-Json -Compress | Set-Content -LiteralPath $CommandPath -Encoding UTF8

$Deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $Deadline) {
    if (Test-Path -LiteralPath $ResultPath) {
        Get-Content -LiteralPath $ResultPath
        exit 0
    }
    Start-Sleep -Milliseconds 200
}

Write-Error "Timed out waiting for $ResultPath. Start Abaqus and run: execfile(r'$McpHome\abaqus_mcp_plugin.py'); mcp_loop()"

