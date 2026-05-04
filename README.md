# Abaqus 6.14 MCP Suite

This repository packages the Abaqus MCP bridge and a local text-to-CAE viewer
setup for Abaqus/CAE 6.14 on Windows.

The main change from the upstream Abaqus MCP project is Abaqus 6.14
compatibility:

- Abaqus 6.14 uses Python 2.7, so plugin-side `exec` and JSON writing need
  Python 2 compatible handling.
- Windows user names with non-ASCII characters can break Abaqus 6.14 file IPC,
  so the default MCP home is `C:\abaqus-mcp`.
- The install script writes an Abaqus startup file that loads the MCP plugin
  from that ASCII path.

## Repository Layout

```text
abaqus-mcp/      Abaqus MCP server and CAE plugin, patched for Abaqus 6.14
abaqus-docs-mcp/ Local MCP server for Abaqus Help retrieval
text-to-cae/     Optional browser viewer and Abaqus examples
scripts/         Windows install, smoke-test, and viewer startup scripts
docs/            Notes for Abaqus 6.14 and collaboration
examples/        Small validation examples
tools/           Local document retrieval helpers
```

## Quick Install

Run PowerShell from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-abaqus-mcp.ps1
```

By default this installs to:

```text
C:\abaqus-mcp
```

It also:

- installs the Python `mcp` package with `python -m pip install --user mcp`
- copies the Abaqus GUI plugin to `%USERPROFILE%\abaqus_plugins\mcp_control`
- writes `%USERPROFILE%\abaqus_v6.env` with a backup if one already exists
- prints a Codex MCP config snippet

## Start Abaqus MCP

In Abaqus/CAE, run:

```python
execfile(r'C:\abaqus-mcp\abaqus_mcp_plugin.py')
mcp_status()
mcp_loop()
```

`mcp_loop()` is blocking. Keep that Abaqus console session open while another
client sends commands.

## Test The Connection

From PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-abaqus-mcp.ps1
```

Success looks like:

```json
{
  "success": true,
  "data": {
    "response": "pong",
    "version": "4.0.0"
  }
}
```

## Optional Viewer

The `text-to-cae` folder is included for local browser visualization. To start:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-text-to-cae-viewer.ps1
```

Then open:

```text
http://127.0.0.1:4178/?case=cantilever&mode=cae
```

ODB files cannot be shown directly in the browser. Export ODB results to the
viewer `result_mesh.json` schema first.

Only a small default viewer result is kept in git. Large generated
`result_mesh.json` files for other examples are intentionally excluded and
should be regenerated from ODBs when needed.

## Local Abaqus Help Search

This repository includes a local Abaqus Help/example indexer and retrieval
tools. It does not commit Abaqus commercial documentation content to GitHub;
each user builds their own local index:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\index-abaqus-help.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 -Query "cantilever static C3D8R" -Limit 5 -Method bm25
```

The search wrapper supports local BM25, TF-IDF, and hybrid scoring:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 `
  -Query "multi chip flexible board bending stress" -Limit 5 -Method hybrid
```

Optional local-only embedding scripts are included, but they require the user
to install/cache a sentence-transformers model locally first. No Abaqus Help
content needs to be uploaded to a cloud service.

For Codex MCP use on Windows, create an ASCII launch path and use the printed
config:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-abaqus-docs-mcp-link.ps1
```

See `docs/HOW_TO_INDEX_ABAQUS_HELP.md` and
`docs/ABAQUS_DOCS_RAG_ROADMAP.md`.

## License And Attribution

This suite includes code derived from:

- `Cai-aa/abaqus-mcp`
- `Cai-aa/text-to-cae`

Their upstream license files are preserved in the corresponding subdirectories.
Review `THIRD_PARTY.md` before publishing a public fork.
