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
  -Query "cantilever static pressure C3D8R" -Limit 5
```

JSON output for agents:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 `
  -Query "surface based tie constraint" -Limit 5 -Json
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
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\search-abaqus-help.ps1 -Query "<topic>" -Limit 5
Use the returned local examples as references, but do not copy commercial Help
text into repo files.
```

