param(
    [Parameter(Mandatory = $true)]
    [string]$Query,
    [string]$IndexDir = "",
    [int]$Limit = 5,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $IndexDir) {
    $IndexDir = Join-Path $RepoRoot ".local\abaqus-help-index"
}

$IndexPath = Join-Path $IndexDir "index.jsonl"
if (-not (Test-Path -LiteralPath $IndexPath)) {
    throw "Index not found: $IndexPath. Run scripts\index-abaqus-help.ps1 first."
}

$terms = @()
foreach ($match in [Regex]::Matches($Query.ToLowerInvariant(), "[a-z0-9_+\-]{2,}")) {
    $terms += $match.Value
}
$terms = @($terms | Select-Object -Unique)
if ($terms.Count -eq 0) {
    throw "Query must contain at least one searchable term."
}

function Get-Score {
    param($Record, [string[]]$Terms, [string]$QueryText)
    $title = [string]$Record.title
    $path = [string]$Record.relativePath
    $sample = [string]$Record.textSample
    $keywords = ""
    if ($Record.keywords) {
        $keywords = (($Record.keywords | ForEach-Object { [string]$_ }) -join " ")
    }
    $titleLower = $title.ToLowerInvariant()
    $pathLower = $path.ToLowerInvariant()
    $sampleLower = $sample.ToLowerInvariant()
    $keywordsLower = $keywords.ToLowerInvariant()
    $queryLower = $QueryText.ToLowerInvariant()

    $score = 0
    if ($titleLower.Contains($queryLower)) { $score += 25 }
    if ($pathLower.Contains($queryLower)) { $score += 12 }
    if ($sampleLower.Contains($queryLower)) { $score += 5 }

    foreach ($term in $Terms) {
        if ($titleLower.Contains($term)) { $score += 10 }
        if ($keywordsLower.Contains($term)) { $score += 6 }
        if ($pathLower.Contains($term)) { $score += 4 }
        if ($sampleLower.Contains($term)) { $score += 1 }
    }
    return $score
}

$results = New-Object System.Collections.Generic.List[object]

Get-Content -LiteralPath $IndexPath -Encoding UTF8 | ForEach-Object {
    if (-not $_) { return }
    $record = $_ | ConvertFrom-Json
    $score = Get-Score -Record $record -Terms $terms -QueryText $Query
    if ($score -gt 0) {
        $excerpt = [string]$record.textSample
        if ($excerpt.Length -gt 360) {
            $excerpt = $excerpt.Substring(0, 360) + "..."
        }
        $results.Add([pscustomobject]@{
            score = $score
            kind = $record.kind
            title = $record.title
            relativePath = $record.relativePath
            path = $record.path
            keywords = (($record.keywords | Select-Object -First 10) -join ", ")
            excerpt = $excerpt
        })
    }
}

$top = @($results | Sort-Object -Property score -Descending | Select-Object -First $Limit)

if ($Json) {
    $top | ConvertTo-Json -Depth 5
    exit 0
}

if ($top.Count -eq 0) {
    Write-Host "No matches."
    exit 0
}

$rank = 1
foreach ($item in $top) {
    Write-Host ("[{0}] score={1} kind={2}" -f $rank, $item.score, $item.kind)
    Write-Host ("Title: {0}" -f $item.title)
    Write-Host ("Path:  {0}" -f $item.path)
    if ($item.keywords) {
        Write-Host ("Keys:  {0}" -f $item.keywords)
    }
    Write-Host ("Text:  {0}" -f $item.excerpt)
    Write-Host ""
    $rank += 1
}

