# TextToCAE 3D Milling Dynamics

This case builds a three-dimensional Abaqus/Explicit end-milling dynamics model and exports high-frame transient results for the browser CAE viewer.

Run:

```powershell
abaqus cae noGUI=models/text-to-cae-milling-3d/milling_abaqus.py
abaqus cae noGUI=models/text-to-cae-milling-3d/export_milling_mesh.py
```

The Abaqus model uses a solid C3D8R workpiece, AA7075-T6 elastic-plastic material data, fixture constraints, and tooth-resolved rotating milling loads. The browser export keeps ODB stress and displacement fields and overlays the rotating end mill, swept slot, and chip stream for smooth playback.
