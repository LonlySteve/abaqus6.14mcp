# Third Party Attribution

This repository packages patched local copies of upstream projects for Abaqus
6.14 usage.

## abaqus-mcp

Source: `https://github.com/Cai-aa/abaqus-mcp`

The bundled copy is under `abaqus-mcp/`. The upstream `LICENSE` file is kept in
that directory.

Local changes include:

- Python 2 compatible plugin execution helper.
- Python 2 compatible JSON writing for file IPC responses.
- Default fallback to `C:\abaqus-mcp` to avoid non-ASCII Windows user paths.
- Abaqus startup example updated for Abaqus 6.14.

## text-to-cae

Source: `https://github.com/Cai-aa/text-to-cae`

The bundled copy is under `text-to-cae/`. The upstream `LICENSE` file is kept in
that directory.

Local usage:

- Browser visualization for exported Abaqus ODB result meshes.
- Local Vite viewer on `127.0.0.1:4178`.

