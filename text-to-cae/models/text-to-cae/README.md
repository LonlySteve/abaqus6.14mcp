# Text to CAE

This example is part of the standalone Text-to-CAE workspace and uses an Abaqus-backed CAE
case. The source of truth is the Abaqus Python script in this directory.

## Inventory

- `cantilever_beam_abaqus.py` creates and solves a static cantilever beam model
  in Abaqus/CAE.
- `cae_project.json` is the viewer-facing project summary and result manifest.

## Abaqus Run

Run from the repository root after Abaqus/CAE is available:

```powershell
abaqus cae noGUI=models/text-to-cae/cantilever_beam_abaqus.py
```

The script writes `cae_project.json` with the latest job status and extracted
result metrics.
