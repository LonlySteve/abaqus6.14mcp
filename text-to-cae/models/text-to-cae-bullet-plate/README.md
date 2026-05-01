# Bullet penetration of an armor steel plate

This Abaqus/Explicit example builds a high-speed 3D projectile penetration model.

Run from the repository root:

```powershell
abaqus cae noGUI=models/text-to-cae-bullet-plate/bullet_plate_penetration_abaqus.py
```

Main assumptions:

- Unit system: mm, tonne, second, Newton, MPa.
- Projectile: 7.62 mm class rigid equivalent bullet by default, 9.6 g, 830 m/s. Set `rigid_projectile` to `false` for a deformable projectile, but expect a much longer run.
- Target: 150 x 150 x 8 mm armor steel plate with clamped edges.
- Material model: Johnson-Cook plasticity/rate dependence where supported, with ductile damage and element deletion controls where available for the steel plate.
- Interaction: Abaqus/Explicit general contact with hard normal contact and Coulomb friction.
- Output: 240 field output intervals over 80 microseconds for smoother ODB animation playback.

For a faster trial run, increase `plate_seed_mm` and `bullet_seed_mm` or reduce `output_frames` in `cae_parameters.json`.
