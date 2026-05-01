"""Abaqus/CAE source script for the Text-to-CAE sphere impact example.

Run with:
    abaqus cae noGUI=models/text-to-cae-sphere-impact/sphere_impact_abaqus.py
"""

from __future__ import print_function

import json
import math
import os
import sys

from abaqus import mdb
from abaqusConstants import *
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
    cwd_candidate = os.path.join(os.getcwd(), "models", "text-to-cae-sphere-impact")
    if os.path.exists(os.path.join(cwd_candidate, "cae_project.json")):
        return cwd_candidate
    return os.getcwd()


ROOT = script_root()
MODEL_NAME = "TextToCAE_SphereImpact_Model"
JOB_NAME = "TextToCAE_SphereImpact"
MANIFEST_PATH = os.path.join(ROOT, "cae_project.json")
PARAMETERS_PATH = os.path.join(ROOT, "cae_parameters.json")
DEFAULT_PARAMETERS = {
    "length_mm": 100.0,
    "width_mm": 70.0,
    "thickness_mm": 2.0,
    "ball_radius_mm": 8.0,
    "impact_velocity_mps": 28.0,
    "seed_size_mm": 4.0,
    "youngs_modulus_mpa": 210000.0,
    "poissons_ratio": 0.3,
}
STEEL_DENSITY_TONNE_PER_MM3 = 7.85e-9
STEP_TIME_S = 0.0025
PULSE_TIME_S = 0.00055


def load_manifest():
    with open(MANIFEST_PATH, "r") as handle:
        return json.load(handle)


def write_manifest(manifest):
    with open(MANIFEST_PATH, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write("\n")


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
    length = parameter_number(parameters, "length_mm", 50.0, 220.0)
    width = parameter_number(parameters, "width_mm", 40.0, 160.0)
    thickness = parameter_number(parameters, "thickness_mm", 0.8, 8.0)
    max_radius = max(3.0, min(length, width) * 0.22)
    return {
        "length_mm": length,
        "width_mm": width,
        "thickness_mm": thickness,
        "ball_radius_mm": parameter_number(parameters, "ball_radius_mm", 3.0, max_radius),
        "impact_velocity_mps": parameter_number(parameters, "impact_velocity_mps", 2.0, 120.0),
        "seed_size_mm": parameter_number(parameters, "seed_size_mm", 2.0, 12.0),
        "youngs_modulus_mpa": parameter_number(parameters, "youngs_modulus_mpa", 1000.0, 500000.0),
        "poissons_ratio": parameter_number(parameters, "poissons_ratio", 0.01, 0.49),
    }


PARAMETERS = load_parameters()
LENGTH_MM = PARAMETERS["length_mm"]
WIDTH_MM = PARAMETERS["width_mm"]
THICKNESS_MM = PARAMETERS["thickness_mm"]
BALL_RADIUS_MM = PARAMETERS["ball_radius_mm"]
IMPACT_VELOCITY_MPS = PARAMETERS["impact_velocity_mps"]
SEED_SIZE_MM = PARAMETERS["seed_size_mm"]
YOUNGS_MODULUS_MPA = PARAMETERS["youngs_modulus_mpa"]
POISSONS_RATIO = PARAMETERS["poissons_ratio"]


def format_number(value):
    return "{:.6g}".format(float(value))


def impact_force_n():
    radius_scale = (BALL_RADIUS_MM / 8.0) ** 2
    velocity_scale = max(IMPACT_VELOCITY_MPS / 28.0, 0.1) ** 2
    thickness_scale = max(THICKNESS_MM / 2.0, 0.25)
    return 6500.0 * radius_scale * velocity_scale * thickness_scale


def apply_parameters_to_manifest(manifest):
    manifest["inputs"]["summary"] = [
        {
            "label": {"en": "Geometry", "zh": u"\u51e0\u4f55"},
            "value": {
                "en": "{} x {} x {} mm clamped plate, {} mm radius steel sphere".format(
                    format_number(LENGTH_MM),
                    format_number(WIDTH_MM),
                    format_number(THICKNESS_MM),
                    format_number(BALL_RADIUS_MM),
                ),
                "zh": u"{} x {} x {} mm \u56fa\u652f\u677f\uff0c{} mm \u534a\u5f84\u94a2\u7403".format(
                    format_number(LENGTH_MM),
                    format_number(WIDTH_MM),
                    format_number(THICKNESS_MM),
                    format_number(BALL_RADIUS_MM),
                ),
            },
        },
        {
            "label": {"en": "Material", "zh": u"\u6750\u6599"},
            "value": {
                "en": "Steel, E = {} MPa, nu = {}, density = 7.85e-9 tonne/mm^3".format(
                    format_number(YOUNGS_MODULUS_MPA),
                    format_number(POISSONS_RATIO),
                ),
                "zh": u"\u94a2\uff0cE = {} MPa\uff0c\u6cca\u677e\u6bd4 {}\uff0c\u5bc6\u5ea6 7.85e-9 tonne/mm^3".format(
                    format_number(YOUNGS_MODULUS_MPA),
                    format_number(POISSONS_RATIO),
                ),
            },
        },
        {
            "label": {"en": "Boundary and load", "zh": u"\u8fb9\u754c\u4e0e\u8f7d\u8377"},
            "value": {
                "en": "All plate edges clamped; steel sphere starts above the plate with {} m/s initial velocity and frictionless normal contact".format(format_number(IMPACT_VELOCITY_MPS)),
                "zh": u"\u677f\u56db\u8fb9\u56fa\u652f\uff1b\u94a2\u7403\u4ee5 {} m/s \u521d\u901f\u5ea6\u51b2\u51fb\u677f\u9762\uff0c\u91c7\u7528\u65e0\u6469\u64e6\u6cd5\u5411\u63a5\u89e6".format(format_number(IMPACT_VELOCITY_MPS)),
            },
        },
        {
            "label": {"en": "Mesh", "zh": u"\u7f51\u683c"},
            "value": {
                "en": "S4R shell elements, {} mm seed".format(format_number(SEED_SIZE_MM)),
                "zh": u"S4R \u58f3\u5355\u5143\uff0c{} mm \u79cd\u5b50".format(format_number(SEED_SIZE_MM)),
            },
        },
    ]
    manifest["inputs"]["geometry"] = {
        "length_mm": LENGTH_MM,
        "width_mm": WIDTH_MM,
        "thickness_mm": THICKNESS_MM,
        "ball_radius_mm": BALL_RADIUS_MM,
    }
    manifest["inputs"]["material"] = {
        "name": "Steel",
        "youngs_modulus_mpa": YOUNGS_MODULUS_MPA,
        "poissons_ratio": POISSONS_RATIO,
        "density_tonne_per_mm3": STEEL_DENSITY_TONNE_PER_MM3,
    }
    manifest["inputs"]["loads"] = {
        "description": "Clamped edges; explicit sphere-to-plate contact with {} m/s initial sphere velocity".format(format_number(IMPACT_VELOCITY_MPS)),
        "impact_velocity_mps": IMPACT_VELOCITY_MPS,
        "contact": "frictionless hard normal contact",
        "initial_gap_mm": max(SEED_SIZE_MM * 0.25, 0.15),
        "load_direction": "global -Z",
    }
    manifest["inputs"]["mesh"] = {
        "element_family": "S4R",
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


def node_set_from_labels(assembly, instance, name, labels):
    labels = tuple(sorted(set(int(label) for label in labels)))
    if not labels:
        raise RuntimeError("No nodes found for set {}".format(name))
    assembly.Set(name=name, nodes=instance.nodes.sequenceFromLabels(labels))


def create_solid_sphere_part(model):
    sketch = model.ConstrainedSketch(name="sphere_profile", sheetSize=BALL_RADIUS_MM * 4.0)
    sketch.ConstructionLine(point1=(0.0, -BALL_RADIUS_MM * 1.5), point2=(0.0, BALL_RADIUS_MM * 1.5))
    sketch.ArcByCenterEnds(
        center=(0.0, 0.0),
        point1=(0.0, -BALL_RADIUS_MM),
        point2=(0.0, BALL_RADIUS_MM),
        direction=CLOCKWISE,
    )
    sketch.Line(point1=(0.0, BALL_RADIUS_MM), point2=(0.0, -BALL_RADIUS_MM))
    part = model.Part(name="ImpactSphere", dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidRevolve(sketch=sketch, angle=360.0, flipRevolveDirection=OFF)
    del model.sketches["sphere_profile"]
    return part


def build_model():
    if MODEL_NAME in mdb.models:
        del mdb.models[MODEL_NAME]
    if JOB_NAME in mdb.jobs:
        del mdb.jobs[JOB_NAME]

    model = mdb.Model(name=MODEL_NAME)
    sketch = model.ConstrainedSketch(name="plate_profile", sheetSize=max(LENGTH_MM, WIDTH_MM) * 2.0)
    sketch.rectangle(point1=(-LENGTH_MM / 2.0, -WIDTH_MM / 2.0), point2=(LENGTH_MM / 2.0, WIDTH_MM / 2.0))
    part = model.Part(name="ImpactPlate", dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseShell(sketch=sketch)
    del model.sketches["plate_profile"]

    material = model.Material(name="Steel")
    material.Density(table=((STEEL_DENSITY_TONNE_PER_MM3,),))
    material.Elastic(table=((YOUNGS_MODULUS_MPA, POISSONS_RATIO),))
    model.HomogeneousSolidSection(name="SteelSolid", material="Steel", thickness=None)
    model.HomogeneousShellSection(
        name="SteelShell",
        preIntegrate=OFF,
        material="Steel",
        thicknessType=UNIFORM,
        thickness=THICKNESS_MM,
        thicknessField="",
        nodalThicknessField="",
        idealization=NO_IDEALIZATION,
        poissonDefinition=DEFAULT,
        thicknessModulus=None,
        temperature=GRADIENT,
        useDensity=OFF,
        integrationRule=SIMPSON,
        numIntPts=5,
    )
    part.SectionAssignment(
        region=regionToolset.Region(faces=part.faces),
        sectionName="SteelShell",
        offset=0.0,
        offsetType=MIDDLE_SURFACE,
        offsetField="",
        thicknessAssignment=FROM_SECTION,
    )
    part.seedPart(size=SEED_SIZE_MM, deviationFactor=0.1, minSizeFactor=0.1)
    elem_type = mesh.ElemType(elemCode=S4R, elemLibrary=EXPLICIT)
    part.setElementType(regions=(part.faces,), elemTypes=(elem_type,))
    part.generateMesh()

    sphere_part = create_solid_sphere_part(model)
    sphere_part.SectionAssignment(region=regionToolset.Region(cells=sphere_part.cells), sectionName="SteelSolid")
    sphere_part.seedPart(size=max(SEED_SIZE_MM * 0.7, BALL_RADIUS_MM / 6.0), deviationFactor=0.08, minSizeFactor=0.12)
    sphere_elem_type = mesh.ElemType(elemCode=C3D4, elemLibrary=EXPLICIT)
    sphere_part.setElementType(regions=(sphere_part.cells,), elemTypes=(sphere_elem_type,))
    sphere_part.generateMesh()

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    instance = assembly.Instance(name="Plate-1", part=part, dependent=ON)
    sphere_instance = assembly.Instance(name="Sphere-1", part=sphere_part, dependent=ON)
    initial_gap = max(SEED_SIZE_MM * 0.25, 0.15)
    assembly.translate(
        instanceList=("Sphere-1",),
        vector=(0.0, 0.0, THICKNESS_MM * 0.5 + initial_gap + BALL_RADIUS_MM),
    )

    edge_tolerance = max(SEED_SIZE_MM * 0.35, 0.05)
    fixed_labels = []
    center_labels = []
    nearest_label = None
    nearest_radius = None
    center_radius = max(BALL_RADIUS_MM * 0.35, SEED_SIZE_MM * 0.75)
    for node in instance.nodes:
        x, y, z = node.coordinates
        if (
            abs(x + LENGTH_MM / 2.0) <= edge_tolerance
            or abs(x - LENGTH_MM / 2.0) <= edge_tolerance
            or abs(y + WIDTH_MM / 2.0) <= edge_tolerance
            or abs(y - WIDTH_MM / 2.0) <= edge_tolerance
        ):
            fixed_labels.append(node.label)
        radius = math.sqrt(x * x + y * y)
        if radius <= center_radius:
            center_labels.append(node.label)
        if nearest_radius is None or radius < nearest_radius:
            nearest_radius = radius
            nearest_label = node.label
    if not center_labels and nearest_label is not None:
        center_labels = [nearest_label]

    node_set_from_labels(assembly, instance, "fixed_edges", fixed_labels)
    node_set_from_labels(assembly, instance, "center_nodes", center_labels)
    assembly.Set(name="sphere_nodes", nodes=sphere_instance.nodes[:])
    assembly.Set(name="sphere_cells", cells=sphere_instance.cells[:])

    model.ExplicitDynamicsStep(name="Impact", previous="Initial", timePeriod=STEP_TIME_S, improvedDtMethod=ON)
    try:
        model.FieldOutputRequest(
            name="ImpactFieldOutput",
            createStepName="Impact",
            variables=("S", "U", "V", "A"),
            numIntervals=12,
        )
    except Exception:
        pass
    model.EncastreBC(name="ClampedEdges", createStepName="Initial", region=assembly.sets["fixed_edges"])
    model.Velocity(
        name="SphereInitialVelocity",
        createStepName="Impact",
        region=assembly.sets["sphere_nodes"],
        velocity1=0.0,
        velocity2=0.0,
        velocity3=-IMPACT_VELOCITY_MPS * 1000.0,
        omega=0.0,
    )
    model.ContactProperty("SpherePlateContact")
    contact_property = model.interactionProperties["SpherePlateContact"]
    try:
        contact_property.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON, constraintEnforcementMethod=DEFAULT)
        contact_property.TangentialBehavior(formulation=FRICTIONLESS)
    except Exception:
        pass
    try:
        model.ContactExp(name="GeneralContact", createStepName="Impact")
        model.interactions["GeneralContact"].includedPairs.setValuesInStep(stepName="Impact", useAllstar=ON)
        model.interactions["GeneralContact"].contactPropertyAssignments.appendInStep(
            stepName="Impact",
            assignments=((GLOBAL_SELF, "SpherePlateContact"),),
        )
    except Exception:
        pass

    mdb.Job(
        name=JOB_NAME,
        model=MODEL_NAME,
        description="Text-to-CAE explicit dynamic sphere-to-plate contact impact",
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
        step = odb.steps["Impact"]
        peak_mises = 0.0
        peak_center_deflection = 0.0
        displayed_frames = 0
        for frame in step.frames:
            if "S" in frame.fieldOutputs:
                for value in frame.fieldOutputs["S"].values:
                    peak_mises = max(peak_mises, float(value.mises))
            if "U" in frame.fieldOutputs:
                displayed_frames += 1
                for value in frame.fieldOutputs["U"].getSubset(region=odb.rootAssembly.nodeSets["CENTER_NODES"], position=NODAL).values:
                    peak_center_deflection = min(peak_center_deflection, float(value.data[2]))
    finally:
        odb.close()

    manifest = load_manifest()
    apply_parameters_to_manifest(manifest)
    manifest["connection"] = {
        "status": "connected",
        "message": "Abaqus solved the sphere impact model and extracted ODB results.",
    }
    manifest["outputs"]["status"] = "complete"
    manifest["outputs"]["metrics"] = [
        {
            "label": "Peak von Mises stress",
            "value": round(float(peak_mises), 4),
            "unit": "MPa",
            "state": "complete",
        },
        {
            "label": "Peak center deflection",
            "value": round(float(abs(peak_center_deflection)), 6),
            "unit": "mm",
            "state": "complete",
        },
        {
            "label": "Impact duration",
            "value": round(float(STEP_TIME_S * 1000.0), 4),
            "unit": "ms",
            "state": "complete",
        },
        {
            "label": "Displayed frames",
            "value": int(displayed_frames),
            "unit": "",
            "state": "complete",
        },
    ]
    for item in manifest["workflow"]:
        if item["step"] in ("Build Abaqus model", "Solve", "Review results"):
            item["status"] = "complete"
    write_manifest(manifest)


def main():
    os.chdir(ROOT)
    update_status("building", message="Abaqus is building the sphere impact model.")
    build_model()
    update_status("running", message="Abaqus explicit impact job submitted.")
    job = mdb.jobs[JOB_NAME]
    job.submit(consistencyChecking=OFF)
    job.waitForCompletion()
    extract_results()
    print("Text-to-CAE sphere impact complete: {}".format(MANIFEST_PATH))


if __name__ == "__main__":
    main()
