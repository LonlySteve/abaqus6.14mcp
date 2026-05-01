"""Export Abaqus ODB transient frames for the sphere impact viewer."""

from __future__ import print_function

import json
import math
import os

from odbAccess import openOdb


def script_root():
    env_root = os.environ.get("TEXT_TO_CAE_ROOT", "")
    if env_root:
        return os.path.abspath(env_root)
    script_path = globals().get("__file__", "")
    if script_path:
        return os.path.dirname(os.path.abspath(script_path))
    return os.getcwd()


ROOT = script_root()
ODB_PATH = os.path.join(ROOT, "TextToCAE_SphereImpact.odb")
OUT_PATH = os.path.join(ROOT, "result_mesh.json")
PARAMETERS_PATH = os.path.join(ROOT, "cae_parameters.json")
INSTANCE_NAME = "PLATE-1"
SPHERE_INSTANCE_NAME = "SPHERE-1"
STEP_NAME = "Impact"
DEFORMATION_SCALE = 1.0
SPHERE_NODE_OFFSET = 1000000
SPHERE_ELEMENT_OFFSET = 1000000


def safe_float(value, fallback=0.0):
    try:
        number = float(value)
    except Exception:
        return fallback
    if math.isnan(number) or math.isinf(number):
        return fallback
    return number


def vector_magnitude(values):
    total = 0.0
    for value in values:
        value = safe_float(value)
        total += value * value
    return total ** 0.5


def load_parameters():
    defaults = {
        "ball_radius_mm": 8.0,
        "thickness_mm": 2.0,
    }
    if os.path.exists(PARAMETERS_PATH):
        with open(PARAMETERS_PATH, "r") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            defaults.update(payload)
    return defaults


def sphere_center_z(radius, step_time, frame_time):
    ratio = frame_time / step_time if step_time > 0.0 else 0.0
    ratio = min(max(ratio, 0.0), 1.0)
    initial_gap = radius * 1.15
    if ratio <= 0.42:
        return radius + initial_gap * (1.0 - ratio / 0.42)
    rebound_ratio = min(max((ratio - 0.42) / 0.58, 0.0), 1.0)
    return radius + radius * 0.38 * math.sin(rebound_ratio * math.pi)


def build_sphere_mesh(radius, center_z, stress_level):
    nodes = []
    elements = []
    latitude_count = 8
    longitude_count = 16
    label = SPHERE_NODE_OFFSET
    rings = []
    for lat_index in range(latitude_count + 1):
        phi = math.pi * float(lat_index) / float(latitude_count)
        z = center_z + radius * math.cos(phi)
        ring_radius = radius * math.sin(phi)
        ring = []
        for lon_index in range(longitude_count):
            theta = 2.0 * math.pi * float(lon_index) / float(longitude_count)
            x = ring_radius * math.cos(theta)
            y = ring_radius * math.sin(theta)
            ring.append(label)
            nodes.append({
                "label": label,
                "coordinates": [safe_float(x), safe_float(y), safe_float(z)],
                "displacement": [0.0, 0.0, 0.0],
                "deformed": [safe_float(x), safe_float(y), safe_float(z)],
                "visualOnly": True,
            })
            label += 1
        rings.append(ring)

    element_label = SPHERE_ELEMENT_OFFSET
    sphere_value = safe_float(stress_level)
    for lat_index in range(latitude_count):
        current = rings[lat_index]
        next_ring = rings[lat_index + 1]
        for lon_index in range(longitude_count):
            a = current[lon_index]
            b = current[(lon_index + 1) % longitude_count]
            c = next_ring[(lon_index + 1) % longitude_count]
            d = next_ring[lon_index]
            elements.append({
                "label": element_label,
                "type": "S4R",
                "connectivity": [a, b, c, d],
                "mises": sphere_value,
                "value": sphere_value,
                "color": "#c9ced6",
                "visualOnly": True,
            })
            element_label += 1
    return nodes, elements


def field_values_for_instance(field_output, instance):
    try:
        return field_output.getSubset(region=instance).values
    except Exception:
        return field_output.values


def build_instance_payload(instance, frame, label_offset, include_visual_only):
    displacement = frame.fieldOutputs["U"]
    stress = frame.fieldOutputs["S"] if "S" in frame.fieldOutputs else None

    displacement_by_node = {}
    max_displacement = 0.0
    for value in field_values_for_instance(displacement, instance):
        vector = [safe_float(value.data[0]), safe_float(value.data[1]), safe_float(value.data[2])]
        displacement_by_node[value.nodeLabel] = vector
        max_displacement = max(max_displacement, vector_magnitude(vector))

    stress_sum_by_element = {}
    stress_count_by_element = {}
    if stress:
        for value in field_values_for_instance(stress, instance):
            element_label = int(value.elementLabel)
            stress_sum_by_element[element_label] = stress_sum_by_element.get(element_label, 0.0) + safe_float(value.mises)
            stress_count_by_element[element_label] = stress_count_by_element.get(element_label, 0) + 1

    nodes = []
    for node in instance.nodes:
        displacement_value = displacement_by_node.get(node.label, [0.0, 0.0, 0.0])
        coordinates = [safe_float(node.coordinates[0]), safe_float(node.coordinates[1]), safe_float(node.coordinates[2])]
        deformed = [
            coordinates[0] + displacement_value[0] * DEFORMATION_SCALE,
            coordinates[1] + displacement_value[1] * DEFORMATION_SCALE,
            coordinates[2] + displacement_value[2] * DEFORMATION_SCALE,
        ]
        nodes.append({
            "label": int(label_offset + node.label),
            "coordinates": coordinates,
            "displacement": displacement_value,
            "deformed": deformed,
            "visualOnly": bool(include_visual_only),
        })

    elements = []
    min_mises = None
    max_mises = None
    element_types = {}
    for element in instance.elements:
        label = int(element.label)
        count = stress_count_by_element.get(label, 0)
        mises = safe_float(stress_sum_by_element.get(label, 0.0) / float(count)) if count else 0.0
        min_mises = mises if min_mises is None else min(min_mises, mises)
        max_mises = mises if max_mises is None else max(max_mises, mises)
        element_type = str(element.type)
        element_types[element_type] = element_types.get(element_type, 0) + 1
        elements.append({
            "label": int(label_offset + label),
            "type": element_type,
            "connectivity": [int(label_offset + node_label) for node_label in element.connectivity],
            "mises": mises,
            "value": mises,
            "visualOnly": bool(include_visual_only),
        })

    return nodes, elements, min_mises, max_mises, max_displacement, element_types


def build_frame_payload(instance, frame, frame_index, step_time, sphere_radius, sphere_instance=None):
    nodes, elements, min_mises, max_mises, max_displacement, element_types = build_instance_payload(
        instance,
        frame,
        0,
        False,
    )
    if sphere_instance is not None:
        sphere_nodes, sphere_elements, sphere_min, sphere_max, sphere_disp, sphere_types = build_instance_payload(
            sphere_instance,
            frame,
            SPHERE_NODE_OFFSET,
            False,
        )
        nodes.extend(sphere_nodes)
        elements.extend(sphere_elements)
        max_displacement = max(max_displacement, sphere_disp)
        if sphere_min is not None:
            min_mises = sphere_min if min_mises is None else min(min_mises, sphere_min)
        if sphere_max is not None:
            max_mises = sphere_max if max_mises is None else max(max_mises, sphere_max)
        for key, value in sphere_types.items():
            element_types[key] = element_types.get(key, 0) + value
    else:
        if min_mises is None:
            min_mises = 0.0
        sphere_z = sphere_center_z(sphere_radius, step_time, safe_float(frame.frameValue))
        sphere_nodes, sphere_elements = build_sphere_mesh(sphere_radius, sphere_z, min_mises)
        nodes.extend(sphere_nodes)
        elements.extend(sphere_elements)

    if min_mises is None:
        min_mises = 0.0
    if max_mises is None:
        max_mises = max(min_mises + 1.0, 1.0)

    dominant_element_type = ""
    if element_types:
        dominant_element_type = sorted(element_types.items(), key=lambda item: item[1], reverse=True)[0][0]

    return {
        "frame": int(frame_index),
        "timeMs": safe_float(frame.frameValue) * 1000.0,
        "deformationScale": DEFORMATION_SCALE,
        "fieldLabel": "S, Mises",
        "elementType": dominant_element_type or "S4R",
        "nodes": nodes,
        "elements": elements,
        "fieldRanges": {
            "misesMin": min_mises,
            "misesMax": max_mises,
            "valueMin": min_mises,
            "valueMax": max_mises,
            "maxDisplacement": max_displacement,
        },
    }


def main():
    parameters = load_parameters()
    sphere_radius = safe_float(parameters.get("ball_radius_mm", 8.0), 8.0)
    odb = openOdb(path=ODB_PATH, readOnly=True)
    try:
        instance = odb.rootAssembly.instances[INSTANCE_NAME]
        sphere_instance = None
        if SPHERE_INSTANCE_NAME in odb.rootAssembly.instances:
            sphere_instance = odb.rootAssembly.instances[SPHERE_INSTANCE_NAME]
        frames = []
        for frame in odb.steps[STEP_NAME].frames:
            if "U" in frame.fieldOutputs:
                frames.append(frame)
        if not frames:
            raise RuntimeError("No dynamic displacement frames found in {}".format(ODB_PATH))
        step_time = safe_float(frames[-1].frameValue, 0.0)
        exported_frames = [
            build_frame_payload(instance, frame, index, step_time, sphere_radius, sphere_instance)
            for index, frame in enumerate(frames)
        ]
        first_frame = exported_frames[0]
        payload = {
            "schemaVersion": 1,
            "source": "TextToCAE_SphereImpact.odb",
            "analysisType": "dynamic",
            "instance": INSTANCE_NAME,
            "step": STEP_NAME,
            "frame": first_frame["frame"],
            "timeMs": first_frame["timeMs"],
            "deformationScale": first_frame["deformationScale"],
            "fieldLabel": first_frame["fieldLabel"],
            "elementType": first_frame["elementType"],
            "nodes": first_frame["nodes"],
            "elements": first_frame["elements"],
            "fieldRanges": first_frame["fieldRanges"],
            "dynamicFrames": exported_frames,
        }
    finally:
        odb.close()

    with open(OUT_PATH, "w") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print("Exported {}".format(OUT_PATH))


if __name__ == "__main__":
    main()
