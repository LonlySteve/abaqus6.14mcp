# Text-to-CAE: Plate With Circular Hole

Classic Abaqus finite element benchmark for stress concentration in a steel plate with a central circular hole.

Run:

```powershell
abaqus cae noGUI=models/text-to-cae-hole-plate/hole_plate_abaqus.py
abaqus cae noGUI=models/text-to-cae-hole-plate/export_result_mesh.py
```

The first script builds and solves the Abaqus model. The second script exports ODB nodes, C3D4 elements, displacements, and averaged element von Mises stress to `result_mesh.json` for the browser viewer.
