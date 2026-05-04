# Index Local Abaqus Help

This project can build a small local search index from Abaqus Help and example
files. The index is generated on each user's machine and is ignored by git.

Do not commit Abaqus Help content, generated indexes, ODB files, or commercial
documentation excerpts to GitHub.

## Build The Index

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\index-abaqus-help.ps1
```

The script auto-detects common Abaqus 6.14 paths such as:

```text
D:\abaqus\6.14-4\Help
D:\abaqus\6.14-4\samples
D:\abaqus\6.14-4\code\bin\SMAExternal\TOSCA\abaqus\examples
```

You can also pass explicit roots:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\index-abaqus-help.ps1 `
  -Root 'D:\abaqus\6.14-4\Help','D:\abaqus\6.14-4\samples'
```

Generated files:

```text
.local\abaqus-help-index\index.jsonl
.local\abaqus-help-index\index.sqlite
.local\abaqus-help-index\manifest.json
```

The JSONL index is the primary format. SQLite is created when Python with
`sqlite3` is available.

## Search

Return the top five local matches:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 `
  -Query "cantilever static pressure C3D8R" -Limit 5 -Method bm25
```

JSON output for agents:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 `
  -Query "surface based tie constraint" -Limit 5 -Method hybrid -Json
```

Search methods:

- `bm25`: default lexical retrieval. Good first choice for Help titles,
  keywords, and example names.
- `tfidf`: simpler term-frequency scoring. Useful as a baseline.
- `hybrid`: combines BM25 and TF-IDF. Good for mixed English/Chinese prompts
  such as "多芯片柔性板弯曲 应力".

## Optional Local Embeddings

Embedding search is optional and stays local. It requires
`sentence-transformers`, `numpy`, and a locally cached model such as
`BAAI/bge-small-en-v1.5` or an e5-small variant.

Build vectors from the JSONL index:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-abaqus-help-embeddings.ps1 `
  -BuildIndex -AllowDownload
```

Search vectors:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help-embeddings.ps1 `
  -PythonCommand ".\.local\venvs\abaqus-docs-rag\Scripts\python.exe" `
  -Query "multi chip flexible board bending stress" -Limit 5
```

The embedding script uses local files by default. It will fail clearly if the
Python packages or model cache are missing. If you explicitly want
sentence-transformers to download model files, add `-AllowDownload`; the Help
entries are still encoded locally by the script.

After embeddings are built, MCP can also use semantic retrieval:

```text
search_abaqus_help(query="multi chip flexible board bending stress", method="embedding", limit=5)
suggest_abaqus_pattern(description="multi chip flexible board bending stress", method="embedding")
```

## MCP Tools

The `abaqus-docs-mcp` folder exposes the local index as MCP tools:

- `search_abaqus_help(query, limit, method)`
- `get_abaqus_doc_entry(path_or_id)`
- `suggest_abaqus_pattern(description, limit, method)`

On Windows, prefer an ASCII launch path for MCP servers. This avoids failures
when the repository is under a user directory containing non-ASCII characters.
Create a local junction and print a Codex config snippet:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-abaqus-docs-mcp-link.ps1 `
  -LinkPath C:\abaqus-614-mcp-suite `
  -PythonCommand C:/abaqus-614-mcp-suite/.local/venvs/abaqus-docs-rag/Scripts/python.exe
```

Example Codex MCP config:

```json
{
  "mcpServers": {
    "abaqus-docs": {
      "command": "C:/abaqus-614-mcp-suite/.local/venvs/abaqus-docs-rag/Scripts/python.exe",
      "args": ["C:/abaqus-614-mcp-suite/abaqus-docs-mcp/mcp_server.py"],
      "env": {
        "ABAQUS_HELP_INDEX": "C:/abaqus-614-mcp-suite/.local/abaqus-help-index/index.jsonl",
        "ABAQUS_HELP_EMBEDDINGS": "C:/abaqus-614-mcp-suite/.local/abaqus-help-index/embeddings.jsonl",
        "ABAQUS_HELP_EMBED_MODEL": "BAAI/bge-small-en-v1.5"
      }
    }
  }
}
```

## Recommended Codex Workflow

Before generating a new Abaqus model script:

1. Search local docs/examples with 3-5 targeted keywords.
2. Read the returned titles, paths, keywords, and short excerpts.
3. Use the closest example pattern to choose element type, step type,
   interactions, output requests, and solver settings.
4. Generate a small smoke-test model first.
5. Run through Abaqus MCP or a noGUI runner.
6. Store generated jobs and ODBs under `C:\abaqus-mcp\jobs\...`.

Example prompt fragment:

```text
Before writing the Abaqus script, run:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 -Query "<topic>" -Limit 5 -Method hybrid
Use the returned local examples as references, but do not copy commercial Help
text into repo files.
```
