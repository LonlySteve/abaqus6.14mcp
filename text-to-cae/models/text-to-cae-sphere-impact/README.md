# Text-to-CAE Sphere Impact

Run:

```powershell
abaqus cae noGUI=models/text-to-cae-sphere-impact/sphere_impact_abaqus.py
abaqus cae noGUI=models/text-to-cae-sphere-impact/export_dynamic_mesh.py
```

This case uses an Abaqus/Explicit clamped shell plate with a steel sphere launched by initial velocity. The model uses hard, frictionless sphere-to-plate contact instead of an equivalent center force pulse, and the browser result viewer shows the contact indentation, rebound, and transient stress field.
