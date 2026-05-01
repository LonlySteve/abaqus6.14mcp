"""Abaqus/CAE source script for 3D bullet penetration of a steel plate.

Run with:
    abaqus cae noGUI=models/text-to-cae-bullet-plate/bullet_plate_penetration_abaqus.py
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

try:
    from odbAccess import openOdb
except Exception:
    openOdb = None


MODEL_NAME = "TextToCAE_BulletPlate_Model"
JOB_NAME = "TextToCAE_BulletPlate_Penetration_Rigid"

DEFAULT_PARAMETERS = {
    "plate_length_mm": 150.0,
    "plate_width_mm": 150.0,
    "plate_thickness_mm": 8.0,
    "bullet_diameter_mm": 7.62,
    "bullet_length_mm": 28.0,
    "bullet_nose_length_mm": 8.0,
    "bullet_mass_g": 9.6,
    "impact_velocity_mps": 830.0,
    "impact_time_s": 8.0e-5,
    "plate_seed_mm": 1.25,
    "bullet_seed_mm": 0.65,
    "rigid_projectile": True,
    "output_frames": 240,
    "friction_coefficient": 0.16,
}


def script_root():
    script_path = globals().get("__file__", "")
    if script_path:
        return os.path.dirname(os.path.abspath(script_path))
    argv_path = sys.argv[0] if sys.argv else ""
    if argv_path and argv_path.endswith(".py"):
        return os.path.dirname(os.path.abspath(argv_path))
    candidate = os.path.join(os.getcwd(), "models", "text-to-cae-bullet-plate")
    if os.path.exists(os.path.join(candidate, "cae_parameters.json")):
        return candidate
    return os.getcwd()


ROOT = script_root()
PARAMETERS_PATH = os.path.join(ROOT, "cae_parameters.json")
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
        with open(PARAMETERS_PATH, "r") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            parameters.update(loaded)

    plate_length = bounded_float(parameters, "plate_length_mm", 80.0, 350.0)
    plate_width = bounded_float(parameters, "plate_width_mm", 80.0, 350.0)
    plate_thickness = bounded_float(parameters, "plate_thickness_mm", 3.0, 30.0)
    bullet_diameter = bounded_float(parameters, "bullet_diameter_mm", 4.0, 20.0)
    bullet_length = bounded_float(parameters, "bullet_length_mm", bullet_diameter * 2.0, bullet_diameter * 8.0)
    bullet_nose = bounded_float(parameters, "bullet_nose_length_mm", bullet_diameter * 0.4, bullet_length * 0.55)

    return {
        "plate_length_mm": plate_length,
        "plate_width_mm": plate_width,
        "plate_thickness_mm": plate_thickness,
        "bullet_diameter_mm": bullet_diameter,
        "bullet_length_mm": bullet_length,
        "bullet_nose_length_mm": bullet_nose,
        "bullet_mass_g": bounded_float(parameters, "bullet_mass_g", 1.0, 80.0),
        "impact_velocity_mps": bounded_float(parameters, "impact_velocity_mps", 50.0, 1800.0),
        "impact_time_s": bounded_float(parameters, "impact_time_s", 1.0e-5, 5.0e-4),
        "plate_seed_mm": bounded_float(parameters, "plate_seed_mm", 0.35, 4.0),
        "bullet_seed_mm": bounded_float(parameters, "bullet_seed_mm", 0.2, 2.0),
        "rigid_projectile": bool(parameters.get("rigid_projectile", DEFAULT_PARAMETERS["rigid_projectile"])),
        "output_frames": bounded_int(parameters, "output_frames", 40, 600),
        "friction_coefficient": bounded_float(parameters, "friction_coefficient", 0.0, 0.6),
    }


PARAMETERS = load_parameters()


def bullet_volume_mm3(radius, length, nose_length):
    cylinder_length = max(length - nose_length, 0.01)
    cylinder_volume = math.pi * radius * radius * cylinder_length
    cone_volume = math.pi * radius * radius * nose_length / 3.0
    return cylinder_volume + cone_volume


def projectile_density_tonne_per_mm3():
    radius = PARAMETERS["bullet_diameter_mm"] * 0.5
    volume = bullet_volume_mm3(radius, PARAMETERS["bullet_length_mm"], PARAMETERS["bullet_nose_length_mm"])
    mass_tonne = PARAMETERS["bullet_mass_g"] * 1.0e-6
    return mass_tonne / volume


def create_projectile_part(model):
    radius = PARAMETERS["bullet_diameter_mm"] * 0.5
    length = PARAMETERS["bullet_length_mm"]
    nose = PARAMETERS["bullet_nose_length_mm"]
    tail_y = -0.5 * length
    shoulder_y = 0.5 * length - nose
    tip_y = 0.5 * length

    sketch = model.ConstrainedSketch(name="projectile_profile", sheetSize=length * 3.0)
    sketch.ConstructionLine(point1=(0.0, -length), point2=(0.0, length))
    sketch.Line(point1=(0.0, tail_y), point2=(radius, tail_y))
    sketch.Line(point1=(radius, tail_y), point2=(radius, shoulder_y))
    sketch.Line(point1=(radius, shoulder_y), point2=(0.0, tip_y))
    sketch.Line(point1=(0.0, tip_y), point2=(0.0, tail_y))

    part = model.Part(name="Projectile", dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidRevolve(sketch=sketch, angle=360.0, flipRevolveDirection=OFF)
    del model.sketches["projectile_profile"]

    projectile_seed = PARAMETERS["bullet_seed_mm"]
    if PARAMETERS["rigid_projectile"]:
        projectile_seed = max(projectile_seed, 1.15)
    part.seedPart(size=projectile_seed, deviationFactor=0.08, minSizeFactor=0.08)
    try:
        part.setMeshControls(regions=part.cells, elemShape=TET, technique=FREE)
    except Exception:
        pass
    elem_type = mesh.ElemType(elemCode=C3D4, elemLibrary=EXPLICIT)
    part.setElementType(regions=(part.cells,), elemTypes=(elem_type,))
    part.generateMesh()
    return part


def create_plate_part(model):
    length = PARAMETERS["plate_length_mm"]
    width = PARAMETERS["plate_width_mm"]
    thickness = PARAMETERS["plate_thickness_mm"]

    sketch = model.ConstrainedSketch(name="plate_profile", sheetSize=max(length, width) * 1.4)
    sketch.rectangle(point1=(-0.5 * length, -0.5 * width), point2=(0.5 * length, 0.5 * width))

    part = model.Part(name="ArmorSteelPlate", dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=thickness)
    del model.sketches["plate_profile"]

    part.seedPart(size=PARAMETERS["plate_seed_mm"], deviationFactor=0.08, minSizeFactor=0.08)
    elem_type = mesh.ElemType(elemCode=C3D8R, elemLibrary=EXPLICIT)
    part.setElementType(regions=(part.cells,), elemTypes=(elem_type,))
    part.generateMesh()
    return part


def add_johnson_cook_materials(model):
    steel = model.Material(name="ArmorSteel_JC")
    steel.Density(table=((7.85e-9,),))
    steel.Elastic(table=((210000.0, 0.30),))
    try:
        steel.Plastic(
            hardening=JOHNSON_COOK,
            table=((792.0, 510.0, 0.26, 1.03, 1793.0, 293.0),),
        )
        steel.RateDependent(type=JOHNSON_COOK, table=((0.014, 1.0),))
    except Exception:
        steel.Plastic(table=((900.0, 0.0), (1150.0, 0.06), (1300.0, 0.16), (1450.0, 0.30)))
    try:
        steel.DuctileDamageInitiation(table=((0.23, -0.33, 0.0), (0.16, 0.33, 0.0), (0.11, 0.66, 0.0)))
        steel.ductileDamageInitiation.DamageEvolution(type=DISPLACEMENT, table=((0.045,),))
    except Exception:
        pass

    projectile = model.Material(name="Projectile_Equivalent")
    projectile.Density(table=((projectile_density_tonne_per_mm3(),),))
    projectile.Elastic(table=((72000.0, 0.34),))
    try:
        projectile.Plastic(
            hardening=JOHNSON_COOK,
            table=((250.0, 480.0, 0.35, 1.05, 1356.0, 293.0),),
        )
        projectile.RateDependent(type=JOHNSON_COOK, table=((0.025, 1.0),))
    except Exception:
        projectile.Plastic(table=((250.0, 0.0), (420.0, 0.10), (560.0, 0.35), (650.0, 0.65)))


def make_sections(model, plate_part, projectile_part):
    try:
        model.SectionControls(name="DeletionControls", elemDeletion=ON, maxDegradation=0.98)
        controls_name = "DeletionControls"
    except Exception:
        controls_name = ""

    try:
        model.HomogeneousSolidSection(name="PlateSection", material="ArmorSteel_JC", controls=controls_name)
        model.HomogeneousSolidSection(name="ProjectileSection", material="Projectile_Equivalent", controls=controls_name)
    except Exception:
        model.HomogeneousSolidSection(name="PlateSection", material="ArmorSteel_JC")
        model.HomogeneousSolidSection(name="ProjectileSection", material="Projectile_Equivalent")

    plate_part.SectionAssignment(
        region=regionToolset.Region(cells=plate_part.cells),
        sectionName="PlateSection",
        offset=0.0,
        offsetType=MIDDLE_SURFACE,
        offsetField="",
    )
    projectile_part.SectionAssignment(
        region=regionToolset.Region(cells=projectile_part.cells),
        sectionName="ProjectileSection",
        offset=0.0,
        offsetType=MIDDLE_SURFACE,
        offsetField="",
    )


def set_from_node_labels(assembly, instance, name, labels):
    labels = tuple(sorted(set(int(label) for label in labels)))
    if not labels:
        raise RuntimeError("No nodes found for set {}".format(name))
    assembly.Set(name=name, nodes=instance.nodes.sequenceFromLabels(labels))


def build_model():
    if MODEL_NAME in mdb.models:
        del mdb.models[MODEL_NAME]
    if JOB_NAME in mdb.jobs:
        del mdb.jobs[JOB_NAME]

    model = mdb.Model(name=MODEL_NAME)
    add_johnson_cook_materials(model)

    plate_part = create_plate_part(model)
    projectile_part = create_projectile_part(model)
    make_sections(model, plate_part, projectile_part)

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)

    plate = assembly.Instance(name="Plate-1", part=plate_part, dependent=ON)
    projectile = assembly.Instance(name="Projectile-1", part=projectile_part, dependent=ON)

    thickness = PARAMETERS["plate_thickness_mm"]
    bullet_length = PARAMETERS["bullet_length_mm"]
    gap = max(PARAMETERS["plate_seed_mm"] * 0.25, 0.12)

    assembly.translate(instanceList=("Plate-1",), vector=(0.0, 0.0, -0.5 * thickness))
    assembly.rotate(instanceList=("Projectile-1",), axisPoint=(0.0, 0.0, 0.0), axisDirection=(1.0, 0.0, 0.0), angle=-90.0)
    assembly.translate(
        instanceList=("Projectile-1",),
        vector=(0.0, 0.0, 0.5 * thickness + gap + 0.5 * bullet_length),
    )

    edge_tolerance = max(PARAMETERS["plate_seed_mm"] * 0.55, 0.05)
    fixed_labels = []
    for node in plate.nodes:
        x, y, z = node.coordinates
        if (
            abs(x - 0.5 * PARAMETERS["plate_length_mm"]) <= edge_tolerance
            or abs(x + 0.5 * PARAMETERS["plate_length_mm"]) <= edge_tolerance
            or abs(y - 0.5 * PARAMETERS["plate_width_mm"]) <= edge_tolerance
            or abs(y + 0.5 * PARAMETERS["plate_width_mm"]) <= edge_tolerance
        ):
            fixed_labels.append(node.label)

    set_from_node_labels(assembly, plate, "PLATE_CLAMPED_EDGE_NODES", fixed_labels)
    assembly.Set(name="PLATE_CELLS", cells=plate.cells[:])
    assembly.Set(name="PROJECTILE_CELLS", cells=projectile.cells[:])
    assembly.Set(name="PROJECTILE_NODES", nodes=projectile.nodes[:])
    if PARAMETERS["rigid_projectile"]:
        rp_feature = assembly.ReferencePoint(point=(0.0, 0.0, 0.5 * thickness + gap + 0.5 * bullet_length))
        reference_point = assembly.referencePoints[rp_feature.id]
        assembly.Set(name="PROJECTILE_RP", referencePoints=(reference_point,))

    model.ExplicitDynamicsStep(
        name="Penetration",
        previous="Initial",
        timePeriod=PARAMETERS["impact_time_s"],
        improvedDtMethod=ON,
    )
    model.EncastreBC(
        name="ClampedPlateEdges",
        createStepName="Initial",
        region=assembly.sets["PLATE_CLAMPED_EDGE_NODES"],
    )
    velocity_region = assembly.sets["PROJECTILE_RP"] if PARAMETERS["rigid_projectile"] else assembly.sets["PROJECTILE_CELLS"]
    model.Velocity(
        name="ProjectileInitialVelocity",
        region=velocity_region,
        velocity1=0.0,
        velocity2=0.0,
        velocity3=-PARAMETERS["impact_velocity_mps"] * 1000.0,
        omega=0.0,
    )

    model.ContactProperty("PenetrationContact")
    contact_property = model.interactionProperties["PenetrationContact"]
    try:
        contact_property.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON, constraintEnforcementMethod=DEFAULT)
        contact_property.TangentialBehavior(
            formulation=PENALTY,
            directionality=ISOTROPIC,
            slipRateDependency=OFF,
            pressureDependency=OFF,
            temperatureDependency=OFF,
            dependencies=0,
            table=((PARAMETERS["friction_coefficient"],),),
            shearStressLimit=None,
            maximumElasticSlip=FRACTION,
            fraction=0.005,
            elasticSlipStiffness=None,
        )
    except Exception:
        pass
    try:
        model.ContactExp(name="GeneralContact", createStepName="Penetration")
        model.interactions["GeneralContact"].includedPairs.setValuesInStep(stepName="Penetration", useAllstar=ON)
        model.interactions["GeneralContact"].contactPropertyAssignments.appendInStep(
            stepName="Penetration",
            assignments=((GLOBAL_SELF, "PenetrationContact"),),
        )
    except Exception:
        pass

    mdb.Job(
        name=JOB_NAME,
        model=MODEL_NAME,
        description="3D Abaqus/Explicit bullet penetration through an armor steel plate",
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
        "** High-frame output inserted for smooth penetration animation\n",
        "*Output, field, number interval={}\n".format(PARAMETERS["output_frames"]),
        "*Node Output\n",
        "U, V, A\n",
        "*Element Output, directions=YES\n",
        "S, PEEQ, STATUS\n",
    ]
    result = []
    inserted = False
    rigid_inserted = False
    inside_penetration = False
    for line in lines:
        stripped = line.strip().lower()
        if PARAMETERS["rigid_projectile"] and stripped.startswith("*end assembly") and not rigid_inserted:
            result.extend([
                "** Rigid projectile body inserted for feasible high-speed penetration runtime\n",
                "*Rigid Body, ref node=PROJECTILE_RP, elset=PROJECTILE_CELLS\n",
            ])
            rigid_inserted = True
        if stripped.startswith("*step") and "name=penetration" in stripped.replace(" ", ""):
            inside_penetration = True
        if inside_penetration and stripped.startswith("*end step") and not inserted:
            result.extend(output_block)
            inserted = True
            inside_penetration = False
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
    summary = {
        "job": JOB_NAME,
        "parameters": PARAMETERS,
        "frames_requested": PARAMETERS["output_frames"],
        "projectile_density_tonne_per_mm3": projectile_density_tonne_per_mm3(),
    }
    try:
        step = odb.steps["Penetration"]
        summary["frames_written"] = len(step.frames)
        peak_mises = 0.0
        final_mean_v3 = 0.0
        final_count = 0
        for frame in step.frames:
            if "S" in frame.fieldOutputs:
                for value in frame.fieldOutputs["S"].values:
                    try:
                        peak_mises = max(peak_mises, float(value.mises))
                    except Exception:
                        pass
        if step.frames and "V" in step.frames[-1].fieldOutputs:
            velocity_values = step.frames[-1].fieldOutputs["V"].getSubset(
                region=odb.rootAssembly.nodeSets["PROJECTILE_NODES"],
                position=NODAL,
            ).values
            for value in velocity_values:
                final_mean_v3 += float(value.data[2])
                final_count += 1
        if final_count:
            final_mean_v3 = final_mean_v3 / float(final_count)
        summary["peak_mises_mpa"] = peak_mises
        summary["final_projectile_mean_v3_mps"] = final_mean_v3 / 1000.0
    finally:
        odb.close()

    with open(SUMMARY_PATH, "w") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main():
    os.chdir(ROOT)
    build_model()
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
    print("Bullet plate penetration complete: {}".format(SUMMARY_PATH))


if __name__ == "__main__":
    main()
