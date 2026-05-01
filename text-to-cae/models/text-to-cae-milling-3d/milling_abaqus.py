"""Abaqus/CAE source script for 3D end-milling explicit dynamics.

Run with:
    abaqus cae noGUI=models/text-to-cae-milling-3d/milling_abaqus.py
"""

from __future__ import print_function

import json
import math
import os
import sys
import io

from abaqus import mdb
from abaqusConstants import *
import mesh
import regionToolset

try:
    from odbAccess import openOdb
except Exception:
    openOdb = None


MODEL_NAME = "TextToCAE_3D_Milling_Model"
JOB_NAME = "TextToCAE_3D_Milling_Dynamics"
DENSITY_TONNE_PER_MM3 = 2.81e-9

DEFAULT_PARAMETERS = {
    "workpiece_length_mm": 56.0,
    "workpiece_width_mm": 24.0,
    "workpiece_thickness_mm": 8.0,
    "tool_diameter_mm": 8.0,
    "flute_count": 4,
    "spindle_speed_rpm": 9000.0,
    "feed_per_tooth_mm": 0.035,
    "axial_depth_mm": 3.0,
    "radial_width_mm": 8.0,
    "step_time_s": 0.0014,
    "output_frames": 240,
    "seed_size_mm": 1.0,
    "youngs_modulus_mpa": 71000.0,
    "poissons_ratio": 0.33,
}


def script_root():
    script_path = globals().get("__file__", "")
    if script_path:
        return os.path.dirname(os.path.abspath(script_path))
    argv_path = sys.argv[0] if sys.argv else ""
    if argv_path and argv_path.endswith(".py"):
        return os.path.dirname(os.path.abspath(argv_path))
    candidate = os.path.join(os.getcwd(), "models", "text-to-cae-milling-3d")
    if os.path.exists(os.path.join(candidate, "cae_parameters.json")):
        return candidate
    return os.getcwd()


ROOT = script_root()
PARAMETERS_PATH = os.path.join(ROOT, "cae_parameters.json")
MANIFEST_PATH = os.path.join(ROOT, "cae_project.json")
SUMMARY_PATH = os.path.join(ROOT, "results_summary.json")


def bounded_float(parameters, name, lower, upper):
    try:
        value = float(parameters.get(name, DEFAULT_PARAMETERS[name]))
    except Exception:
        value = float(DEFAULT_PARAMETERS[name])
    return min(max(value, lower), upper)


def bounded_int(parameters, name, lower, upper):
    return int(round(bounded_float(parameters, name, lower, upper)))


def load_parameters():
    parameters = dict(DEFAULT_PARAMETERS)
    if os.path.exists(PARAMETERS_PATH):
        with io.open(PARAMETERS_PATH, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            parameters.update(loaded)
    length = bounded_float(parameters, "workpiece_length_mm", 24.0, 80.0)
    width = bounded_float(parameters, "workpiece_width_mm", 10.0, 45.0)
    thickness = bounded_float(parameters, "workpiece_thickness_mm", 3.0, 14.0)
    tool_diameter = bounded_float(parameters, "tool_diameter_mm", 3.0, min(18.0, width * 0.85))
    return {
        "workpiece_length_mm": length,
        "workpiece_width_mm": width,
        "workpiece_thickness_mm": thickness,
        "tool_diameter_mm": tool_diameter,
        "flute_count": bounded_int(parameters, "flute_count", 2, 6),
        "spindle_speed_rpm": bounded_float(parameters, "spindle_speed_rpm", 1000.0, 30000.0),
        "feed_per_tooth_mm": bounded_float(parameters, "feed_per_tooth_mm", 0.005, 0.18),
        "axial_depth_mm": bounded_float(parameters, "axial_depth_mm", 0.4, min(thickness * 0.85, 8.0)),
        "radial_width_mm": bounded_float(parameters, "radial_width_mm", 0.6, min(tool_diameter, width * 0.75)),
        "step_time_s": bounded_float(parameters, "step_time_s", 2.0e-4, 4.0e-3),
        "output_frames": bounded_int(parameters, "output_frames", 80, 500),
        "seed_size_mm": bounded_float(parameters, "seed_size_mm", 0.8, 3.5),
        "youngs_modulus_mpa": bounded_float(parameters, "youngs_modulus_mpa", 1000.0, 500000.0),
        "poissons_ratio": bounded_float(parameters, "poissons_ratio", 0.01, 0.49),
    }


PARAMETERS = load_parameters()


def format_number(value):
    return "{:.6g}".format(float(value))


def cutting_force_n():
    diameter = PARAMETERS["tool_diameter_mm"]
    chip_area = PARAMETERS["axial_depth_mm"] * PARAMETERS["feed_per_tooth_mm"]
    radial_scale = max(PARAMETERS["radial_width_mm"] / max(diameter, 1.0e-6), 0.05)
    material_scale = max(PARAMETERS["youngs_modulus_mpa"] / 71000.0, 0.1) ** 0.35
    speed_scale = max(PARAMETERS["spindle_speed_rpm"] / 9000.0, 0.1) ** 0.22
    # Approximate tangential tooth force using a specific cutting pressure near 1200 N/mm2.
    return 1200.0 * chip_area * radial_scale * material_scale * speed_scale


def read_manifest():
    with io.open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_manifest(manifest):
    with io.open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write("\n")


def apply_parameters_to_manifest(manifest):
    manifest["inputs"]["geometry"] = {
        "workpiece_length_mm": PARAMETERS["workpiece_length_mm"],
        "workpiece_width_mm": PARAMETERS["workpiece_width_mm"],
        "workpiece_thickness_mm": PARAMETERS["workpiece_thickness_mm"],
        "tool_diameter_mm": PARAMETERS["tool_diameter_mm"],
        "axial_depth_mm": PARAMETERS["axial_depth_mm"],
        "radial_width_mm": PARAMETERS["radial_width_mm"],
    }
    manifest["inputs"]["material"] = {
        "name": "AA7075-T6 aluminum",
        "youngs_modulus_mpa": PARAMETERS["youngs_modulus_mpa"],
        "poissons_ratio": PARAMETERS["poissons_ratio"],
        "density_tonne_per_mm3": DENSITY_TONNE_PER_MM3,
    }
    manifest["inputs"]["loads"] = {
        "description": "Rotating {}-flute milling load, peak tooth force {} N".format(
            PARAMETERS["flute_count"], format_number(cutting_force_n())
        ),
        "spindle_speed_rpm": PARAMETERS["spindle_speed_rpm"],
        "feed_per_tooth_mm": PARAMETERS["feed_per_tooth_mm"],
        "flute_count": PARAMETERS["flute_count"],
    }
    manifest["inputs"]["mesh"] = {
        "element_family": "C3D8R",
        "seed_size_mm": PARAMETERS["seed_size_mm"],
    }
    manifest["inputs"]["summary"] = [
        {
            "label": {"en": "Geometry", "zh": u"\u51e0\u4f55"},
            "value": {
                "en": "{} x {} x {} mm workpiece, {} mm {}-flute end mill".format(
                    format_number(PARAMETERS["workpiece_length_mm"]),
                    format_number(PARAMETERS["workpiece_width_mm"]),
                    format_number(PARAMETERS["workpiece_thickness_mm"]),
                    format_number(PARAMETERS["tool_diameter_mm"]),
                    PARAMETERS["flute_count"],
                ),
                "zh": u"{} x {} x {} mm \u5de5\u4ef6\uff0c{} mm {} \u5203\u7acb\u94e3\u5200".format(
                    format_number(PARAMETERS["workpiece_length_mm"]),
                    format_number(PARAMETERS["workpiece_width_mm"]),
                    format_number(PARAMETERS["workpiece_thickness_mm"]),
                    format_number(PARAMETERS["tool_diameter_mm"]),
                    PARAMETERS["flute_count"],
                ),
            },
        },
        {
            "label": {"en": "Cutting condition", "zh": u"\u5207\u524a\u53c2\u6570"},
            "value": {
                "en": "{} rpm, {} mm/tooth, {} mm axial depth".format(
                    format_number(PARAMETERS["spindle_speed_rpm"]),
                    format_number(PARAMETERS["feed_per_tooth_mm"]),
                    format_number(PARAMETERS["axial_depth_mm"]),
                ),
                "zh": u"{} rpm\uff0c{} mm/\u9f7f\uff0c{} mm \u8f74\u5411\u5207\u6df1".format(
                    format_number(PARAMETERS["spindle_speed_rpm"]),
                    format_number(PARAMETERS["feed_per_tooth_mm"]),
                    format_number(PARAMETERS["axial_depth_mm"]),
                ),
            },
        },
        {
            "label": {"en": "Boundary and load", "zh": u"\u8fb9\u754c\u4e0e\u8f7d\u8377"},
            "value": {
                "en": "Fixture sides and bottom constrained; rotating tooth load sweeps through the slot",
                "zh": u"\u5de5\u88c5\u4fa7\u9762\u4e0e\u5e95\u9762\u7ea6\u675f\uff1b\u65cb\u8f6c\u5200\u9f7f\u8f7d\u8377\u6cbf\u69fd\u626b\u8fc7",
            },
        },
        {
            "label": {"en": "Mesh", "zh": u"\u7f51\u683c"},
            "value": {
                "en": "C3D8R solid elements, {} mm seed".format(format_number(PARAMETERS["seed_size_mm"])),
                "zh": u"C3D8R \u4e09\u7ef4\u5b9e\u4f53\u5355\u5143\uff0c{} mm \u79cd\u5b50".format(format_number(PARAMETERS["seed_size_mm"])),
            },
        },
    ]


def update_status(status, message):
    manifest = read_manifest()
    apply_parameters_to_manifest(manifest)
    manifest["connection"] = {"status": "connected", "message": message}
    manifest["outputs"]["status"] = status
    for item in manifest["workflow"]:
        if item["step"] == "Build Abaqus model" and status in ("building", "running", "complete"):
            item["status"] = "complete" if status != "building" else "building"
        if item["step"] == "Solve" and status in ("running", "complete"):
            item["status"] = "complete" if status == "complete" else "running"
    write_manifest(manifest)


def node_set_from_labels(assembly, instance, name, labels):
    labels = tuple(sorted(set(int(label) for label in labels)))
    if labels:
        assembly.Set(name=name, nodes=instance.nodes.sequenceFromLabels(labels))


def zone_amplitude_data(x_index, y_index, zone_x_count, zone_y_count):
    step_time = PARAMETERS["step_time_s"]
    spindle_hz = PARAMETERS["spindle_speed_rpm"] / 60.0
    tooth_period = 1.0 / max(spindle_hz * PARAMETERS["flute_count"], 1.0e-9)
    travel_fraction = (x_index + 0.5) / float(zone_x_count)
    radial_fraction = (y_index + 0.5) / float(zone_y_count)
    center = travel_fraction * step_time
    engagement_width = min(step_time * 0.22, max(tooth_period * 0.42, step_time / float(zone_x_count) * 1.25))
    radial_delay = (0.5 - radial_fraction) * tooth_period * 0.22
    center = min(max(center + radial_delay, 0.0), step_time)
    start = max(center - engagement_width * 0.62, 0.0)
    rise = max(center - engagement_width * 0.18, 0.0)
    fall = min(center + engagement_width * 0.24, step_time)
    end = min(center + engagement_width * 0.72, step_time)
    values = [(0.0, 0.0), (start, 0.0), (rise, 0.55), (center, 1.0), (fall, 0.42), (end, 0.0), (step_time, 0.0)]
    filtered = []
    for time_value, amplitude in values:
        if filtered and abs(filtered[-1][0] - time_value) <= 1.0e-12:
            filtered[-1] = (time_value, amplitude)
        else:
            filtered.append((time_value, amplitude))
    return tuple(filtered)


def build_model():
    if MODEL_NAME in mdb.models:
        del mdb.models[MODEL_NAME]
    if JOB_NAME in mdb.jobs:
        del mdb.jobs[JOB_NAME]

    model = mdb.Model(name=MODEL_NAME)

    length = PARAMETERS["workpiece_length_mm"]
    width = PARAMETERS["workpiece_width_mm"]
    thickness = PARAMETERS["workpiece_thickness_mm"]
    seed = PARAMETERS["seed_size_mm"]

    sketch = model.ConstrainedSketch(name="workpiece_profile", sheetSize=max(length, width) * 1.6)
    sketch.rectangle(point1=(0.0, 0.0), point2=(length, width))
    part = model.Part(name="Workpiece", dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=thickness)
    del model.sketches["workpiece_profile"]

    material = model.Material(name="AA7075_T6")
    material.Density(table=((DENSITY_TONNE_PER_MM3,),))
    material.Elastic(table=((PARAMETERS["youngs_modulus_mpa"], PARAMETERS["poissons_ratio"]),))
    try:
        material.Plastic(hardening=JOHNSON_COOK, table=((503.0, 476.0, 0.52, 1.34, 775.0, 293.0),))
        material.RateDependent(type=JOHNSON_COOK, table=((0.024, 1.0),))
    except Exception:
        material.Plastic(table=((503.0, 0.0), (570.0, 0.04), (625.0, 0.10), (690.0, 0.22)))
    model.HomogeneousSolidSection(name="WorkpieceSection", material="AA7075_T6")
    part.SectionAssignment(region=regionToolset.Region(cells=part.cells), sectionName="WorkpieceSection")

    try:
        part.seedPart(size=seed, deviationFactor=0.08, minSizeFactor=0.1)
        part.setMeshControls(regions=part.cells, elemShape=HEX, technique=STRUCTURED)
    except Exception:
        part.seedPart(size=seed, deviationFactor=0.08, minSizeFactor=0.1)
    elem_type = mesh.ElemType(elemCode=C3D8R, elemLibrary=EXPLICIT)
    part.setElementType(regions=(part.cells,), elemTypes=(elem_type,))
    part.generateMesh()

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    instance = assembly.Instance(name="Workpiece-1", part=part, dependent=ON)

    tolerance = max(seed * 0.58, 0.08)
    fixed_labels = []
    top_slot_labels = []
    zone_x_count = 24
    zone_y_count = 7
    zone_labels = [[[] for _ in range(zone_y_count)] for _ in range(zone_x_count)]
    slot_width = PARAMETERS["radial_width_mm"]
    slot_y_min = 0.5 * width - 0.5 * slot_width
    slot_y_max = 0.5 * width + 0.5 * slot_width
    top_z = thickness
    for node in instance.nodes:
        x, y, z = node.coordinates
        if z <= tolerance or x <= tolerance or x >= length - tolerance or y <= tolerance or y >= width - tolerance:
            fixed_labels.append(node.label)
        if z >= top_z - tolerance and slot_y_min - tolerance <= y <= slot_y_max + tolerance:
            top_slot_labels.append(node.label)
            xi = int(min(max(math.floor(x / length * zone_x_count), 0), zone_x_count - 1))
            yi = int(min(max(math.floor((y - slot_y_min) / max(slot_width, 1.0e-6) * zone_y_count), 0), zone_y_count - 1))
            zone_labels[xi][yi].append(node.label)

    node_set_from_labels(assembly, instance, "FIXTURE_NODES", fixed_labels)
    node_set_from_labels(assembly, instance, "TOP_SLOT_NODES", top_slot_labels)
    for xi in range(zone_x_count):
        for yi in range(zone_y_count):
            node_set_from_labels(assembly, instance, "CUT_ZONE_{}_{}".format(xi + 1, yi + 1), zone_labels[xi][yi])

    model.ExplicitDynamicsStep(
        name="Milling",
        previous="Initial",
        timePeriod=PARAMETERS["step_time_s"],
        improvedDtMethod=ON,
    )
    try:
        model.fieldOutputRequests["F-Output-1"].setValues(
            variables=("S", "U", "V", "A", "PEEQ"),
            numIntervals=PARAMETERS["output_frames"],
        )
    except Exception:
        pass
    model.EncastreBC(name="Fixture", createStepName="Initial", region=assembly.sets["FIXTURE_NODES"])

    peak_force = cutting_force_n()
    for xi in range(zone_x_count):
        for yi in range(zone_y_count):
            labels = zone_labels[xi][yi]
            if not labels:
                continue
            amplitude_name = "ToothPulse_{}_{}".format(xi + 1, yi + 1)
            model.TabularAmplitude(name=amplitude_name, timeSpan=STEP, data=zone_amplitude_data(xi, yi, zone_x_count, zone_y_count))
            radial_position = (yi + 0.5) / float(zone_y_count) - 0.5
            force_per_node = peak_force / float(max(len(labels), 1))
            tangential = -force_per_node * (0.72 + 0.28 * math.cos(radial_position * math.pi))
            radial = force_per_node * radial_position * 0.55
            normal = -force_per_node * 0.42
            model.ConcentratedForce(
                name="MillingToothForce_{}_{}".format(xi + 1, yi + 1),
                createStepName="Milling",
                region=assembly.sets["CUT_ZONE_{}_{}".format(xi + 1, yi + 1)],
                cf1=tangential,
                cf2=radial,
                cf3=normal,
                amplitude=amplitude_name,
                distributionType=UNIFORM,
                field="",
                localCsys=None,
            )

    mdb.Job(
        name=JOB_NAME,
        model=MODEL_NAME,
        description="3D Abaqus/Explicit tooth-resolved end milling dynamics",
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


def inject_high_frame_output(inp_path):
    with open(inp_path, "r") as handle:
        lines = handle.readlines()
    output_block = [
        "** High-frame output inserted for smooth 3D milling animation\n",
        "*Output, field, number interval={}\n".format(PARAMETERS["output_frames"]),
        "*Node Output\n",
        "U, V, A\n",
        "*Element Output, directions=YES\n",
        "S, PEEQ\n",
    ]
    result = []
    inserted = False
    inside_milling = False
    for line in lines:
        stripped = line.strip().lower().replace(" ", "")
        if stripped.startswith("*step") and "name=milling" in stripped:
            inside_milling = True
        if inside_milling and stripped.startswith("*endstep") and not inserted:
            result.extend(output_block)
            inserted = True
            inside_milling = False
        result.append(line)
    if not inserted:
        raise RuntimeError("Could not insert high-frame output block into {}".format(inp_path))
    with open(inp_path, "w") as handle:
        handle.writelines(result)


def extract_summary():
    if openOdb is None:
        return
    odb_path = os.path.join(ROOT, JOB_NAME + ".odb")
    if not os.path.exists(odb_path):
        return
    odb = openOdb(path=odb_path, readOnly=True)
    peak_mises = 0.0
    max_disp = 0.0
    frame_count = 0
    try:
        step = odb.steps["Milling"]
        frame_count = len(step.frames)
        for frame in step.frames:
            if "S" in frame.fieldOutputs:
                for value in frame.fieldOutputs["S"].values:
                    try:
                        peak_mises = max(peak_mises, float(value.mises))
                    except Exception:
                        pass
            if "U" in frame.fieldOutputs:
                for value in frame.fieldOutputs["U"].values:
                    try:
                        max_disp = max(max_disp, math.sqrt(sum(float(x) * float(x) for x in value.data)))
                    except Exception:
                        pass
    finally:
        odb.close()

    summary = {
        "job": JOB_NAME,
        "parameters": PARAMETERS,
        "peak_mises_mpa": peak_mises,
        "max_displacement_mm": max_disp,
        "frames_written": frame_count,
        "peak_tooth_force_n": cutting_force_n(),
    }
    with io.open(SUMMARY_PATH, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    manifest = read_manifest()
    apply_parameters_to_manifest(manifest)
    manifest["connection"] = {
        "status": "connected",
        "message": "Abaqus solved the 3D milling dynamics model and extracted ODB results.",
    }
    manifest["outputs"]["status"] = "complete"
    manifest["outputs"]["metrics"] = [
        {"label": "Peak milling stress", "value": round(float(peak_mises), 4), "unit": "MPa", "state": "complete"},
        {"label": "Max workpiece displacement", "value": round(float(max_disp), 6), "unit": "mm", "state": "complete"},
        {"label": "Spindle speed", "value": round(float(PARAMETERS["spindle_speed_rpm"]), 2), "unit": "rpm", "state": "complete"},
        {"label": "Displayed frames", "value": int(frame_count), "unit": "", "state": "complete"},
    ]
    for item in manifest["workflow"]:
        if item["step"] in ("Build Abaqus model", "Solve", "Review results"):
            item["status"] = "complete"
    write_manifest(manifest)


def main():
    os.chdir(ROOT)
    update_status("building", "Abaqus is building the 3D milling dynamics model.")
    build_model()
    update_status("running", "Abaqus explicit 3D milling job submitted.")
    model_job = mdb.jobs[JOB_NAME]
    model_job.writeInput(consistencyChecking=OFF)
    inp_path = os.path.join(ROOT, JOB_NAME + ".inp")
    inject_high_frame_output(inp_path)
    del mdb.jobs[JOB_NAME]
    job = mdb.JobFromInputFile(
        name=JOB_NAME,
        inputFileName=inp_path,
        type=ANALYSIS,
        memory=90,
        memoryUnits=PERCENTAGE,
        explicitPrecision=SINGLE,
        nodalOutputPrecision=SINGLE,
    )
    job.submit(consistencyChecking=OFF)
    job.waitForCompletion()
    extract_summary()
    print("3D milling dynamics complete: {}".format(SUMMARY_PATH))


if __name__ == "__main__":
    main()
