param(
    [string[]]$Root,
    [string]$OutDir = "",
    [int]$MaxFileBytes = 1048576,
    [int]$MaxFiles = 0,
    [switch]$NoSqlite
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot ".local\abaqus-help-index"
}

$Extensions = @(".htm", ".html", ".txt", ".inp", ".py", ".for", ".f", ".sub")
$SkipDirectoryNames = @("graphics", "images", "icons", "css", "js", "__pycache__")

function Get-DefaultRoots {
    $candidates = @()
    foreach ($envName in @("ABAQUS_HELP_ROOT", "ABAQUS_DOC_ROOT", "ABAQUS_EXAMPLES_ROOT")) {
        $value = [Environment]::GetEnvironmentVariable($envName)
        if ($value) {
            $candidates += $value
        }
    }
    $candidates += @(
        "C:\abaqus-mcp\help",
        "D:\abaqus\6.14-4\Help",
        "D:\abaqus\6.14-4\samples",
        "D:\abaqus\6.14-4\code\bin\SMAExternal\TOSCA\abaqus\examples",
        "C:\SIMULIA\Abaqus\6.14-4\Help",
        "C:\SIMULIA\Abaqus\6.14-4\samples",
        "C:\Program Files\Dassault Systemes\SimulationServices\V6R2014x\Help"
    )
    $existing = @()
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $existing += (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    $existing | Select-Object -Unique
}

function Read-TextFile {
    param([string]$Path)
    try {
        return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    } catch {
        return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::Default)
    }
}

function ConvertTo-PlainText {
    param([string]$Text, [string]$Extension)
    if ($Extension -in @(".htm", ".html")) {
        $text = [Regex]::Replace($Text, "(?is)<script.*?</script>", " ")
        $text = [Regex]::Replace($text, "(?is)<style.*?</style>", " ")
        $text = [Regex]::Replace($text, "(?is)<[^>]+>", " ")
        $text = [System.Net.WebUtility]::HtmlDecode($text)
    } else {
        $text = $Text
    }
    $text = [Regex]::Replace($text, "\s+", " ").Trim()
    return $text
}

function Get-Title {
    param([string]$RawText, [string]$PlainText, [string]$Path, [string]$Extension)
    if ($Extension -in @(".htm", ".html")) {
        $titleMatch = [Regex]::Match($RawText, "(?is)<title[^>]*>(.*?)</title>")
        if ($titleMatch.Success) {
            $title = [System.Net.WebUtility]::HtmlDecode(($titleMatch.Groups[1].Value -replace "\s+", " ").Trim())
            if ($title) { return $title }
        }
        $h1Match = [Regex]::Match($RawText, "(?is)<h1[^>]*>(.*?)</h1>")
        if ($h1Match.Success) {
            $title = [System.Net.WebUtility]::HtmlDecode(($h1Match.Groups[1].Value -replace "<[^>]+>", " " -replace "\s+", " ").Trim())
            if ($title) { return $title }
        }
    }
    $firstLine = ($PlainText -split "\r?\n|\. ")[0]
    if ($firstLine -and $firstLine.Length -le 160) {
        return $firstLine.Trim()
    }
    return [System.IO.Path]::GetFileName($Path)
}

function Get-Kind {
    param([string]$Path, [string]$Extension)
    $lower = $Path.ToLowerInvariant()
    if ($Extension -eq ".inp") { return "input-deck" }
    if ($Extension -in @(".py", ".for", ".f", ".sub")) { return "script" }
    if ($lower -match "example|sample|verification|\\exa\\|\\ver\\") { return "example" }
    return "help"
}

function Get-Keywords {
    param([string]$Text)
    $stop = @{
        "the"=1; "and"=1; "for"=1; "with"=1; "that"=1; "this"=1; "from"=1; "are"=1; "you"=1; "your"=1
        "abaqus"=1; "analysis"=1; "using"=1; "will"=1; "can"=1; "all"=1; "has"=1; "have"=1; "was"=1
    }
    $counts = @{}
    foreach ($match in [Regex]::Matches($Text.ToLowerInvariant(), "[a-z][a-z0-9_+\-]{2,}")) {
        $word = $match.Value
        if ($stop.ContainsKey($word)) { continue }
        if (-not $counts.ContainsKey($word)) { $counts[$word] = 0 }
        $counts[$word] += 1
    }
    $counts.GetEnumerator() |
        Sort-Object -Property Value -Descending |
        Select-Object -First 24 |
        ForEach-Object { $_.Key }
}

function Get-Sha1 {
    param([string]$Text)
    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    (($sha1.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "")
}

if (-not $Root -or $Root.Count -eq 0) {
    $Root = @(Get-DefaultRoots)
}

if (-not $Root -or $Root.Count -eq 0) {
    throw "No Abaqus help/example roots found. Pass -Root 'D:\abaqus\6.14-4\Help','D:\abaqus\6.14-4\samples' or set ABAQUS_HELP_ROOT."
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$IndexPath = Join-Path $OutDir "index.jsonl"
$ManifestPath = Join-Path $OutDir "manifest.json"
$SqlitePath = Join-Path $OutDir "index.sqlite"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$writer = New-Object System.IO.StreamWriter($IndexPath, $false, $utf8NoBom)

$indexed = 0
$skippedLarge = 0
$skippedUnreadable = 0
$started = Get-Date

try {
    foreach ($rootPath in $Root) {
        if (-not (Test-Path -LiteralPath $rootPath)) { continue }
        $resolvedRoot = (Resolve-Path -LiteralPath $rootPath).Path
        $files = Get-ChildItem -LiteralPath $resolvedRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $ext = $_.Extension.ToLowerInvariant()
                if ($Extensions -notcontains $ext) { return $false }
                foreach ($skipName in $SkipDirectoryNames) {
                    if ($_.FullName -match "\\$([Regex]::Escape($skipName))\\") { return $false }
                }
                return $true
            }

        foreach ($file in $files) {
            if ($MaxFiles -gt 0 -and $indexed -ge $MaxFiles) { break }
            if ($file.Length -gt $MaxFileBytes) {
                $skippedLarge += 1
                continue
            }
            try {
                $raw = Read-TextFile -Path $file.FullName
                $plain = ConvertTo-PlainText -Text $raw -Extension $file.Extension.ToLowerInvariant()
                if (-not $plain) { continue }

                $relativePath = $file.FullName.Substring($resolvedRoot.Length).TrimStart("\")
                $title = Get-Title -RawText $raw -PlainText $plain -Path $file.FullName -Extension $file.Extension.ToLowerInvariant()
                $sampleLength = [Math]::Min(700, $plain.Length)
                $sample = $plain.Substring(0, $sampleLength)
                $record = [ordered]@{
                    schemaVersion = 1
                    id = Get-Sha1 ($file.FullName.ToLowerInvariant())
                    kind = Get-Kind -Path $file.FullName -Extension $file.Extension.ToLowerInvariant()
                    title = $title
                    path = $file.FullName
                    sourceRoot = $resolvedRoot
                    relativePath = $relativePath
                    extension = $file.Extension.ToLowerInvariant()
                    sizeBytes = $file.Length
                    lastWriteTimeUtc = $file.LastWriteTimeUtc.ToString("o")
                    keywords = @(Get-Keywords -Text ($title + " " + $relativePath + " " + $sample))
                    textSample = $sample
                }
                $writer.WriteLine(($record | ConvertTo-Json -Depth 5 -Compress))
                $indexed += 1
            } catch {
                $skippedUnreadable += 1
            }
        }
    }
} finally {
    $writer.Close()
}

$manifest = [ordered]@{
    schemaVersion = 1
    createdAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    roots = @($Root)
    outDir = (Resolve-Path -LiteralPath $OutDir).Path
    indexPath = $IndexPath
    sqlitePath = if ($NoSqlite) { $null } else { $SqlitePath }
    indexedFiles = $indexed
    skippedLargeFiles = $skippedLarge
    skippedUnreadableFiles = $skippedUnreadable
    maxFileBytes = $MaxFileBytes
    elapsedSeconds = [Math]::Round(((Get-Date) - $started).TotalSeconds, 2)
}
[System.IO.File]::WriteAllText($ManifestPath, ($manifest | ConvertTo-Json -Depth 5), $utf8NoBom)

if (-not $NoSqlite) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $pyPath = Join-Path $OutDir "_create_sqlite.py"
        $pyCode = @'
import json
import sqlite3
import sys

jsonl_path, sqlite_path = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(sqlite_path)
cur = conn.cursor()
cur.execute("drop table if exists docs")
cur.execute("""
create table docs (
  id text primary key,
  kind text,
  title text,
  path text,
  source_root text,
  relative_path text,
  extension text,
  size_bytes integer,
  last_write_time_utc text,
  keywords text,
  text_sample text
)
""")
with open(jsonl_path, "r", encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        cur.execute(
            "insert or replace into docs values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.get("id"),
                record.get("kind"),
                record.get("title"),
                record.get("path"),
                record.get("sourceRoot"),
                record.get("relativePath"),
                record.get("extension"),
                record.get("sizeBytes"),
                record.get("lastWriteTimeUtc"),
                " ".join(record.get("keywords") or []),
                record.get("textSample"),
            ),
        )
cur.execute("create index if not exists idx_docs_kind on docs(kind)")
cur.execute("create index if not exists idx_docs_title on docs(title)")
conn.commit()
conn.close()
'@
        [System.IO.File]::WriteAllText($pyPath, $pyCode, $utf8NoBom)
        try {
            & $python.Source $pyPath $IndexPath $SqlitePath
        } finally {
            Remove-Item -LiteralPath $pyPath -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Warning "Python not found; skipped SQLite index creation."
    }
}

Write-Host "Indexed files: $indexed"
Write-Host "JSONL index: $IndexPath"
if (-not $NoSqlite -and (Test-Path -LiteralPath $SqlitePath)) {
    Write-Host "SQLite index: $SqlitePath"
}
Write-Host "Manifest: $ManifestPath"

