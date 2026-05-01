"""Abaqus/CAE source script for the Text-to-CAE perforated plate example.

Run with:
    abaqus cae noGUI=models/text-to-cae-hole-plate/hole_plate_abaqus.py
"""

from __future__ import print_function

import json
import math
import os
import sys

from abaqus import mdb
from abaqusConstants import (
    ANALYSIS,
    CARTESIAN,
    C3D4,
    DEFORMABLE_BODY,
    DEFAULT,
    FREE,
    FROM_SECTION,
    MIDDLE_SURFACE,
    NODAL,
    ODB,
    OFF,
    ON,
    PERCENTAGE,
    SINGLE,
    STANDARD,
    TET,
    THREE_D,
    UNIFORM,
    UNSET,
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
    cwd_candidate = os.path.join(os.getcwd(), "models", "text-to-cae-hole-plate")
    if os.path.exists(os.path.join(cwd_candidate, "cae_project.json")):
        return cwd_candidate
    return os.getcwd()


ROOT = script_root()
MODEL_NAME = "TextToCAE_HolePlate_Model"
JOB_NAME = "TextToCAE_HolePlate"
MANIFEST_PATH = os.path.join(ROOT, "cae_project.json")
PARAMETERS_PATH = os.path.join(ROOT, "cae_parameters.json")
DEFAULT_PARAMETERS = {
    "length_mm": 120.0,
    "width_mm": 60.0,
    "thickness_mm": 4.0,
    "hole_radius_mm": 12.0,
    "youngs_modulus_mpa": 210000.0,
    "poissons_ratio": 0.3,
    "right_displacement_x_mm": 0.12,
    "seed_size_mm": 3.0,
}


def load_manifest():
    with open(MANIFEST_PATH, "r") as handle:
        return json.load(handle)


def parameter_number(parameters, name, minimum, maximum):
    try:
        value = float(parameters.get(name, DEFAULT_PARAMETERS[name]))
    except Exception:
        value = float(DEFAULT_PARAMETERS[name])
    return min(max(value, minimum), maximum)


def load_parameters():
    parameters = dict(DEFAULT_PARAMETERS)
    if os.path.exists(PARAMETERS_PATH):
        with open(PARAMETERS_PATH, "r") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            parameters.update(loaded)
    length = parameter_number(parameters, "length_mm", 40.0, 300.0)
    width = parameter_number(parameters, "width_mm", 20.0, 180.0)
    thickness = parameter_number(parameters, "thickness_mm", 1.0, 30.0)
    max_hole_radius = max(2.0, min(length, width) * 0.38)
    return {
        "length_mm": length,
        "width_mm": width,
        "thickness_mm": thickness,
        "hole_radius_mm": parameter_number(parameters, "hole_radius_mm", 2.0, max_hole_radius),
        "youngs_modulus_mpa": parameter_number(parameters, "youngs_modulus_mpa", 1000.0, 500000.0),
        "poissons_ratio": parameter_number(parameters, "poissons_ratio", 0.01, 0.49),
        "right_displacement_x_mm": parameter_number(parameters, "right_displacement_x_mm", 0.005, 2.0),
        "seed_size_mm": parameter_number(parameters, "seed_size_mm", 1.0, 12.0),
    }


PARAMETERS = load_parameters()
LENGTH_MM = PARAMETERS["length_mm"]
WIDTH_MM = PARAMETERS["width_mm"]
THICKNESS_MM = PARAMETERS["thickness_mm"]
HOLE_RADIUS_MM = PARAMETERS["hole_radius_mm"]
YOUNGS_MODULUS_MPA = PARAMETERS["youngs_modulus_mpa"]
POISSONS_RATIO = PARAMETERS["poissons_ratio"]
RIGHT_DISPLACEMENT_MM = PARAMETERS["right_displacement_x_mm"]
SEED_SIZE_MM = PARAMETERS["seed_size_mm"]


def write_manifest(manifest):
    with open(MANIFEST_PATH, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write("\n")


def format_number(value):
    formatted = "{:.6g}".format(float(value))
    return formatted


def apply_parameters_to_manifest(manifest):
    manifest["inputs"]["summary"] = [
        {
            "label": {"en": "Geometry", "zh": u"\u51e0\u4f55"},
            "value": {
                "en": "{} x {} x {} mm plate, {} mm radius center hole".format(
                    format_number(LENGTH_MM),
                    format_number(WIDTH_MM),
                    format_number(THICKNESS_MM),
                    format_number(HOLE_RADIUS_MM),
                ),
                "zh": u"{} x {} x {} mm \u5e73\u677f\uff0c\u4e2d\u5fc3\u5706\u5b54\u534a\u5f84 {} mm".format(
                    format_number(LENGTH_MM),
                    format_number(WIDTH_MM),
                    format_number(THICKNESS_MM),
                    format_number(HOLE_RADIUS_MM),
                ),
            },
        },
        {
            "label": {"en": "Material", "zh": u"\u6750\u6599"},
            "value": {
                "en": "Steel, E = {} MPa, nu = {}".format(format_number(YOUNGS_MODULUS_MPA), format_number(POISSONS_RATIO)),
                "zh": u"\u94a2\uff0cE = {} MPa\uff0c\u6cca\u677e\u6bd4 {}".format(format_number(YOUNGS_MODULUS_MPA), format_number(POISSONS_RATIO)),
            },
        },
        {
            "label": {"en": "Boundary and load", "zh": u"\u8fb9\u754c\u4e0e\u8f7d\u8377"},
            "value": {
                "en": "Left face fixed, right face prescribed X displacement {} mm".format(format_number(RIGHT_DISPLACEMENT_MM)),
                "zh": u"\u5de6\u7aef\u9762\u56fa\u5b9a\uff0c\u53f3\u7aef\u9762\u65bd\u52a0 X \u5411\u4f4d\u79fb {} mm".format(format_number(RIGHT_DISPLACEMENT_MM)),
            },
        },
        {
            "label": {"en": "Mesh", "zh": u"\u7f51\u683c"},
            "value": {
                "en": "C3D4 tetrahedral solid elements, {} mm seed".format(format_number(SEED_SIZE_MM)),
                "zh": u"C3D4 \u56db\u9762\u4f53\u5b9e\u4f53\u5355\u5143\uff0c{} mm \u79cd\u5b50".format(format_number(SEED_SIZE_MM)),
            },
        },
    ]
    manifest["inputs"]["geometry"] = {
        "length_mm": LENGTH_MM,
        "width_mm": WIDTH_MM,
        "thickness_mm": THICKNESS_MM,
        "hole_radius_mm": HOLE_RADIUS_MM,
    }
    manifest["inputs"]["material"] = {
        "name": "Steel",
        "youngs_modulus_mpa": YOUNGS_MODULUS_MPA,
        "poissons_ratio": POISSONS_RATIO,
    }
    manifest["inputs"]["loads"] = {
        "description": "Left face fixed; right face prescribed X displacement {} mm".format(format_number(RIGHT_DISPLACEMENT_MM)),
        "fixed_end": "x = 0 face",
        "right_displacement_x_mm": RIGHT_DISPLACEMENT_MM,
        "load_direction": "global X",
    }
    manifest["inputs"]["mesh"] = {
        "element_family": "C3D4",
        "seed_size_mm": SEED_SIZE_MM,
    }


def update_status(status, connection_status="connected", message=""):
    manifest = load_manifest()
    apply_parameters_to_manifest(manifest)
    manifest["connection"] = {
        "status": connection_status,
        "message": message,
    }
    manifest["outputs"]["status"] = status
    if status in ("building", "running"):
        for metric in manifest["outputs"].get("metrics", []):
            metric["state"] = status
    for item in manifest["workflow"]:
        if item["step"] == "Build Abaqus model" and status in ("building", "running", "complete"):
            item["status"] = "complete" if status != "building" else "building"
        if item["step"] == "Solve" and status in ("running", "complete"):
            item["status"] = "complete" if status == "complete" else "running"
    write_manifest(manifest)


def face_at_x(part, x_value):
    return part.faces.findAt(((x_value, WIDTH_MM / 2.0, THICKNESS_MM / 2.0),))


def build_model():
    if MODEL_NAME in mdb.models:
        del mdb.models[MODEL_NAME]
    if JOB_NAME in mdb.jobs:
        del mdb.jobs[JOB_NAME]

    model = mdb.Model(name=MODEL_NAME)
    sketch = model.ConstrainedSketch(name="plate_profile", sheetSize=180.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=(LENGTH_MM, WIDTH_MM))
    sketch.CircleByCenterPerimeter(
        center=(LENGTH_MM / 2.0, WIDTH_MM / 2.0),
        point1=(LENGTH_MM / 2.0 + HOLE_RADIUS_MM, WIDTH_MM / 2.0),
    )

    part = model.Part(
        name="Plate",
        dimensionality=THREE_D,
        type=DEFORMABLE_BODY,
    )
    part.BaseSolidExtrude(sketch=sketch, depth=THICKNESS_MM)
    del model.sketches["plate_profile"]

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

    part.Set(faces=face_at_x(part, 0.0), name="left_face")
    part.Set(faces=face_at_x(part, LENGTH_MM), name="right_face")
    part.seedPart(size=SEED_SIZE_MM, deviationFactor=0.1, minSizeFactor=0.1)
    part.setMeshControls(regions=part.cells, elemShape=TET, technique=FREE)
    elem_type = mesh.ElemType(elemCode=C3D4, elemLibrary=STANDARD)
    part.setElementType(regions=(part.cells,), elemTypes=(elem_type,))
    part.generateMesh()

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    instance = assembly.Instance(name="Plate-1", part=part, dependent=ON)
    assembly.Set(name="left_face", faces=instance.faces.findAt(((0.0, WIDTH_MM / 2.0, THICKNESS_MM / 2.0),)))
    assembly.Set(name="right_face", faces=instance.faces.findAt(((LENGTH_MM, WIDTH_MM / 2.0, THICKNESS_MM / 2.0),)))
    right_nodes = instance.nodes.getByBoundingBox(
        xMin=LENGTH_MM - 1.0e-6,
        xMax=LENGTH_MM + 1.0e-6,
        yMin=-1.0e-6,
        yMax=WIDTH_MM + 1.0e-6,
        zMin=-1.0e-6,
        zMax=THICKNESS_MM + 1.0e-6,
    )
    assembly.Set(name="right_face_nodes", nodes=right_nodes)

    model.StaticStep(name="Load", previous="Initial")
    model.EncastreBC(name="FixedLeft", createStepName="Initial", region=assembly.sets["left_face"])
    model.DisplacementBC(
        name="PullRight",
        createStepName="Load",
        region=assembly.sets["right_face"],
        u1=RIGHT_DISPLACEMENT_MM,
        u2=UNSET,
        u3=UNSET,
        ur1=UNSET,
        ur2=UNSET,
        ur3=UNSET,
        amplitude=UNSET,
        fixed=OFF,
        distributionType=UNIFORM,
        fieldName="",
        localCsys=None,
    )

    mdb.Job(
        name=JOB_NAME,
        model=MODEL_NAME,
        description="Text-to-CAE plate with a circular hole under tensile displacement",
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


def extract_results():
    odb_path = os.path.join(ROOT, JOB_NAME + ".odb")
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        frame = odb.steps["Load"].frames[-1]
        stress = frame.fieldOutputs["S"]
        displacement = frame.fieldOutputs["U"]
        reaction_force = frame.fieldOutputs["RF"]
        max_mises = 0.0
        for value in stress.values:
            max_mises = max(max_mises, value.mises)
        max_umag = 0.0
        for value in displacement.values:
            squared_sum = 0.0
            for component in value.data:
                squared_sum += component * component
            max_umag = max(max_umag, math.sqrt(squared_sum))
        right_values = displacement.getSubset(region=odb.rootAssembly.nodeSets["RIGHT_FACE_NODES"], position=NODAL).values
        right_ux = None
        for value in right_values:
            right_ux = value.data[0] if right_ux is None else max(right_ux, value.data[0])
        reaction_values = reaction_force.getSubset(region=odb.rootAssembly.nodeSets["RIGHT_FACE_NODES"], position=NODAL).values
        total_reaction_x = 0.0
        for value in reaction_values:
            total_reaction_x += value.data[0]
    finally:
        odb.close()

    gross_area = WIDTH_MM * THICKNESS_MM
    nominal_stress = abs(total_reaction_x) / gross_area if gross_area else 0.0
    stress_concentration = max_mises / nominal_stress if nominal_stress else None

    manifest = load_manifest()
    apply_parameters_to_manifest(manifest)
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
            "label": "Right edge displacement X",
            "value": round(float(right_ux), 6) if right_ux is not None else None,
            "unit": "mm",
            "state": "complete" if right_ux is not None else "unavailable",
        },
        {
            "label": "Stress concentration factor",
            "value": round(float(stress_concentration), 3) if stress_concentration else None,
            "unit": "",
            "state": "complete" if stress_concentration else "unavailable",
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
    print("Text-to-CAE perforated plate complete: {}".format(MANIFEST_PATH))


if __name__ == "__main__":
    main()
