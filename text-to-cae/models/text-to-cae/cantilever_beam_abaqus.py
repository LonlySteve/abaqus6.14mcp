"""Abaqus/CAE source script for the Text-to-CAE cantilever example.

Run with:
    abaqus cae noGUI=models/text-to-cae/cantilever_beam_abaqus.py
"""

from __future__ import print_function

import json
import math
import os
import sys

from abaqus import mdb
from abaqusConstants import (
    C3D8R,
    ANALYSIS,
    CARTESIAN,
    DEFAULT,
    DEFORMABLE_BODY,
    FROM_SECTION,
    HEX,
    MIDDLE_SURFACE,
    NODAL,
    OFF,
    ODB,
    ON,
    PERCENTAGE,
    SINGLE,
    STANDARD,
    THREE_D,
    UNIFORM,
)
import mesh
import regionToolset
from odbAccess import openOdb


def script_root():
    env_root = os.environ.get("TEXT_TO_CAE_ROOT", "")
    if env_root and os.path.exists(os.path.join(env_root, "cae_project.json")):
        return os.path.abspath(env_root)
    script_path = globals().get("__file__", "")
    if script_path:
        return os.path.dirname(os.path.abspath(script_path))
    argv_path = sys.argv[0] if sys.argv else ""
    if argv_path and argv_path.endswith(".py"):
        return os.path.dirname(os.path.abspath(argv_path))
    cwd_candidate = os.path.join(os.getcwd(), "models", "text-to-cae")
    if os.path.exists(os.path.join(cwd_candidate, "cae_project.json")):
        return cwd_candidate
    return os.getcwd()


ROOT = script_root()
MODEL_NAME = "TextToCAE_Cantilever_Model"
JOB_NAME = "TextToCAE_Cantilever"
MANIFEST_PATH = os.path.join(ROOT, "cae_project.json")

LENGTH_MM = 120.0
WIDTH_MM = 20.0
HEIGHT_MM = 12.0
YOUNGS_MODULUS_MPA = 210000.0
POISSONS_RATIO = 0.3
TIP_FORCE_N = -800.0
SEED_SIZE_MM = 6.0


def load_manifest():
    with open(MANIFEST_PATH, "r") as handle:
        return json.load(handle)


def write_manifest(manifest):
    with open(MANIFEST_PATH, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write("\n")


def face_at_z(part, z=None):
    faces = part.faces
    if z is None:
        raise ValueError("z coordinate is required")
    return faces.findAt(((WIDTH_MM / 2.0, HEIGHT_MM / 2.0, z),))


def update_status(status, connection_status="connected", message=""):
    manifest = load_manifest()
    manifest["connection"] = {
        "status": connection_status,
        "message": message,
    }
    manifest["outputs"]["status"] = status
    write_manifest(manifest)


def build_model():
    if MODEL_NAME in mdb.models:
        del mdb.models[MODEL_NAME]

    model = mdb.Model(name=MODEL_NAME)
    sketch = model.ConstrainedSketch(name="beam_profile", sheetSize=240.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=(WIDTH_MM, HEIGHT_MM))

    part = model.Part(
        name="Beam",
        dimensionality=THREE_D,
        type=DEFORMABLE_BODY,
    )
    part.BaseSolidExtrude(sketch=sketch, depth=LENGTH_MM)
    del model.sketches["beam_profile"]

    material = model.Material(name="Steel")
    material.Elastic(table=((YOUNGS_MODULUS_MPA, POISSONS_RATIO),))
    model.HomogeneousSolidSection(name="SteelSection", material="Steel", thickness=None)
    part.SectionAssignment(
        region=regionToolset.Region(cells=part.cells),
        sectionName="SteelSection",
        offset=0.0,
        offsetType=MIDDLE_SURFACE,
        offsetField="",
        thicknessAssignment=FROM_SECTION,
    )

    part.Set(faces=face_at_z(part, z=0.0), name="fixed_end")
    part.Set(faces=face_at_z(part, z=LENGTH_MM), name="free_end")
    part.seedPart(size=SEED_SIZE_MM, deviationFactor=0.1, minSizeFactor=0.1)
    part.setMeshControls(regions=part.cells, elemShape=HEX)
    elem_type = mesh.ElemType(elemCode=C3D8R, elemLibrary=STANDARD)
    part.setElementType(regions=(part.cells,), elemTypes=(elem_type,))
    part.generateMesh()

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    instance = assembly.Instance(name="Beam-1", part=part, dependent=ON)
    assembly.Set(name="fixed_end", faces=instance.faces.findAt(((WIDTH_MM / 2.0, HEIGHT_MM / 2.0, 0.0),)))
    free_end_face = instance.faces.findAt(((WIDTH_MM / 2.0, HEIGHT_MM / 2.0, LENGTH_MM),))
    assembly.Set(name="free_end", faces=free_end_face)
    free_end_nodes = instance.nodes.getByBoundingBox(
        xMin=-1.0e-6,
        xMax=WIDTH_MM + 1.0e-6,
        yMin=-1.0e-6,
        yMax=HEIGHT_MM + 1.0e-6,
        zMin=LENGTH_MM - 1.0e-6,
        zMax=LENGTH_MM + 1.0e-6,
    )
    if len(free_end_nodes) == 0:
        raise RuntimeError("No free-end nodes found for load application.")
    assembly.Set(name="free_end_nodes", nodes=free_end_nodes)

    model.StaticStep(name="Load", previous="Initial")
    model.EncastreBC(name="Fixed", createStepName="Initial", region=assembly.sets["fixed_end"])
    model.ConcentratedForce(
        name="TipForce",
        createStepName="Load",
        region=assembly.sets["free_end_nodes"],
        cf2=TIP_FORCE_N / float(len(free_end_nodes)),
    )

    mdb.Job(
        name=JOB_NAME,
        model=MODEL_NAME,
        description="Text-to-CAE cantilever beam static analysis",
        type=ANALYSIS,
        atTime=None,
        waitMinutes=0,
        waitHours=0,
        queue=None,
        memory=90,
        memoryUnits=PERCENTAGE,
        getMemoryFromAnalysis=True,
        explicitPrecision=SINGLE,
        nodalOutputPrecision=SINGLE,
        echoPrint=OFF,
        modelPrint=OFF,
        contactPrint=OFF,
        historyPrint=OFF,
        userSubroutine="",
        scratch="",
        resultsFormat=ODB,
    )
    return model


def extract_results():
    odb_path = os.path.join(ROOT, JOB_NAME + ".odb")
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        frame = odb.steps["Load"].frames[-1]
        stress = frame.fieldOutputs["S"]
        displacement = frame.fieldOutputs["U"]
        max_mises = 0.0
        for value in stress.values:
            max_mises = max(max_mises, value.mises)
        max_umag = 0.0
        for value in displacement.values:
            squared_sum = 0.0
            for component in value.data:
                squared_sum += component * component
            max_umag = max(max_umag, math.sqrt(squared_sum))
        tip_values = displacement.getSubset(region=odb.rootAssembly.nodeSets["FREE_END_NODES"], position=NODAL).values
        tip_uy = None
        for value in tip_values:
            tip_uy = value.data[1] if tip_uy is None else min(tip_uy, value.data[1])
    finally:
        odb.close()

    manifest = load_manifest()
    manifest["connection"] = {
        "status": "connected",
        "message": "Abaqus solved the model and extracted ODB results.",
    }
    manifest["outputs"]["status"] = "complete"
    manifest["outputs"]["metrics"] = [
        {
            "label": "Max von Mises stress",
            "value": round(float(max_mises), 4),
            "unit": "MPa",
            "state": "complete",
        },
        {
            "label": "Max displacement magnitude",
            "value": round(float(max_umag), 6),
            "unit": "mm",
            "state": "complete",
        },
        {
            "label": "Tip displacement Y",
            "value": round(float(tip_uy), 6) if tip_uy is not None else None,
            "unit": "mm",
            "state": "complete" if tip_uy is not None else "unavailable",
        },
    ]
    for item in manifest["workflow"]:
        if item["step"] in ("Build Abaqus model", "Solve", "Review results"):
            item["status"] = "complete"
    write_manifest(manifest)


def main():
    os.chdir(ROOT)
    update_status("building", message="Abaqus is building the CAE model.")
    build_model()
    update_status("running", message="Abaqus job submitted.")
    job = mdb.jobs[JOB_NAME]
    job.submit(consistencyChecking=OFF)
    job.waitForCompletion()
    extract_results()
    print("Text-to-CAE complete: {}".format(MANIFEST_PATH))


if __name__ == "__main__":
    main()
