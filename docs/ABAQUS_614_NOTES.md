# Abaqus 6.14 Notes

## Why `C:\abaqus-mcp`

Abaqus/CAE 6.14 uses Python 2.7. On Windows, Python 2 path handling can fail
when the user profile path contains non-ASCII characters. The file IPC bridge
uses JSON files under `commands/` and `results/`, so path encoding failures can
make Abaqus consume commands but fail to write responses.

Use an ASCII install path:

```text
C:\abaqus-mcp
```

## Manual Startup

If `mcp_loop` is not defined in the Abaqus console, load the plugin manually:

```python
execfile(r'C:\abaqus-mcp\abaqus_mcp_plugin.py')
mcp_status()
mcp_loop()
```

`mcp_loop()` blocks the Abaqus console while it listens for commands.

## Compatibility Fixes

The Abaqus-side plugin has these Abaqus 6.14 compatibility fixes:

- A Python 2 compatible `exec` helper for scripts sent through MCP.
- JSON response writing that works with Python 2 Unicode behavior.
- `C:\abaqus-mcp` fallback when `__file__` or user home resolution is not
  reliable.
- Startup file uses `io.open` and `compile(..., 'exec')` rather than Python 3
  only `open(..., encoding=...)`.

## License And Abaqus Versions

This package does not include Abaqus or license files.

Multiple Abaqus versions can usually coexist if they are installed in separate
directories and scripts call the intended `abaqus.bat` by absolute path. License
compatibility depends on the installed SIMULIA/FLEXnet/DSLS license server and
the Abaqus version being launched.

