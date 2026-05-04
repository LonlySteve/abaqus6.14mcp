# Abaqus Docs RAG Roadmap

This repository now has three local-only documentation retrieval layers.

## 1. BM25 / TF-IDF

Default search command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 `
  -Query "tie constraint surface contact" -Limit 5
```

Available methods:

```powershell
-Method bm25
-Method tfidf
-Method hybrid
```

This is dependency-free apart from Python and the local JSONL index.

## 2. Optional Local Embeddings

Embedding search is optional and disabled until the user explicitly installs
and caches a local sentence-transformers model.

Example after local setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-abaqus-help-embeddings.ps1
```

Then cache a model according to your local policy, for example
`BAAI/bge-small-en-v1.5`. The build script uses `--local-files-only`, so it will
fail rather than download unexpectedly if the model is not already available.
Add `-AllowDownload` only when you explicitly want sentence-transformers to
download model files; the Abaqus Help text is still embedded locally.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-abaqus-help-embeddings.ps1 `
  -BuildIndex -AllowDownload
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help-embeddings.ps1 `
  -PythonCommand ".\.local\venvs\abaqus-docs-rag\Scripts\python.exe" `
  -Query "multi chip flexible board bending stress" -Limit 5
```

Generated embedding files are under `.local/` and are ignored by git.

## 3. MCP Tools

The `abaqus-docs-mcp` server exposes:

- `search_abaqus_help(query, limit, method)`
- `get_abaqus_doc_entry(path_or_id)`
- `suggest_abaqus_pattern(description, limit, method)`

Use `method="embedding"` after vectors are built and the MCP server is launched
with the embedding venv Python.

Run it from the repository root, or use the setup script below when the
repository path contains non-ASCII characters:

```powershell
python .\abaqus-docs-mcp\mcp_server.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-abaqus-docs-mcp-link.ps1 `
  -PythonCommand C:/abaqus-614-mcp-suite/.local/venvs/abaqus-docs-rag/Scripts/python.exe
```

Codex config example:

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

Keep the index local. Do not commit Abaqus Help content or generated indexes.
