"""Export a browser-ready dynamic preview from the bullet penetration ODB."""

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
ODB_PATH = os.path.join(ROOT, "TextToCAE_BulletPlate_Penetration_Rigid.odb")
OUT_PATH = os.path.join(ROOT, "result_mesh.json")
PARAMETERS_PATH = os.path.join(ROOT, "cae_parameters.json")
INSTANCE_NAME = "PLATE-1"
PROJECTILE_INSTANCE_NAME = "PROJECTILE-1"
STEP_NAME = "Penetration"
DEFORMATION_SCALE = 1.0
MAX_EXPORTED_FRAMES = 41
PROJECTILE_ELEMENT_OFFSET = 3000000
PROJECTILE_NODE_OFFSET = 3000000

HEX_FACE_NODE_INDICES = (
    (0, 1, 2, 3),
    (4, 7, 6, 5),
    (0, 4, 5, 1),
    (1, 5, 6, 2),
    (2, 6, 7, 3),
    (3, 7, 4, 0),
)
TET_FACE_NODE_INDICES = (
    (0, 2, 1),
    (0, 1, 3),
    (1, 2, 3),
    (2, 0, 3),
)


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
    parameters = {
        "plate_length_mm": 150.0,
        "plate_width_mm": 150.0,
        "plate_thickness_mm": 8.0,
        "bullet_diameter_mm": 7.62,
        "bullet_length_mm": 28.0,
        "impact_velocity_mps": 830.0,
    }
    if os.path.exists(PARAMETERS_PATH):
        with open(PARAMETERS_PATH, "r") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            parameters.update(payload)
    return parameters


def face_key(labels):
    return ":".join(str(label) for label in sorted(labels))


def face_indices_for_element(element):
    element_type = str(element.type).upper()
    if element_type.startswith("C3D4") or element_type.startswith("C3D10"):
        return TET_FACE_NODE_INDICES
    return HEX_FACE_NODE_INDICES


def surface_faces(instance, parameters):
    faces = {}
    face_sources = {}
    half_length = safe_float(parameters.get("plate_length_mm"), 150.0) * 0.5
    half_width = safe_float(parameters.get("plate_width_mm"), 150.0) * 0.5
    crop_x = min(half_length, 34.0)
    crop_y = min(half_width, 34.0)

    node_by_label = dict((int(node.label), node) for node in instance.nodes)
    for element in instance.elements:
        connectivity = [int(label) for label in element.connectivity]
        center_x = 0.0
        center_y = 0.0
        for label in connectivity:
            node = node_by_label[label]
            center_x += safe_float(node.coordinates[0])
            center_y += safe_float(node.coordinates[1])
        center_x /= float(max(len(connectivity), 1))
        center_y /= float(max(len(connectivity), 1))
        if abs(center_x) > crop_x or abs(center_y) > crop_y:
            continue
        for local_face in face_indices_for_element(element):
            labels = tuple(connectivity[index] for index in local_face)
            key = face_key(labels)
            if key in faces:
                del faces[key]
                del face_sources[key]
            else:
                faces[key] = labels
                face_sources[key] = int(element.label)

    surface = []
    for key, labels in faces.items():
        surface.append({
            "labels": labels,
            "sourceElement": face_sources[key],
        })
    return surface


def selected_frames(frames):
    if len(frames) <= MAX_EXPORTED_FRAMES:
        return list(enumerate(frames))
    last_index = len(frames) - 1
    indices = []
    for index in range(MAX_EXPORTED_FRAMES):
        source_index = int(round(index * last_index / float(MAX_EXPORTED_FRAMES - 1)))
        if not indices or indices[-1] != source_index:
            indices.append(source_index)
    return [(index, frames[index]) for index in indices]


def projectile_center_z(parameters, frame_time):
    length = safe_float(parameters.get("bullet_length_mm"), 28.0)
    thickness = safe_float(parameters.get("plate_thickness_mm"), 8.0)
    velocity = safe_float(parameters.get("impact_velocity_mps"), 830.0) * 1000.0
    gap = 0.35
    initial_center = 0.5 * thickness + gap + 0.5 * length
    return initial_center - velocity * safe_float(frame_time)


def build_projectile_mesh(parameters, frame_time, stress_level):
    radius = safe_float(parameters.get("bullet_diameter_mm"), 7.62) * 0.5
    length = safe_float(parameters.get("bullet_length_mm"), 28.0)
    nose = safe_float(parameters.get("bullet_nose_length_mm"), 8.0)
    center_z = projectile_center_z(parameters, frame_time)
    tail_z = center_z + 0.5 * length
    shoulder_z = center_z - 0.5 * length + nose
    tip_z = center_z - 0.5 * length
    rings = []
    nodes = []
    label = PROJECTILE_NODE_OFFSET
    for z_value, ring_radius, count in (
        (tail_z, radius, 20),
        (shoulder_z, radius, 20),
        (tip_z, 0.0, 1),
    ):
        ring = []
        if count == 1:
            ring.append(label)
            nodes.append({
                "label": label,
                "coordinates": [0.0, 0.0, safe_float(z_value)],
                "displacement": [0.0, 0.0, 0.0],
                "deformed": [0.0, 0.0, safe_float(z_value)],
                "visualOnly": True,
            })
            label += 1
        else:
            for index in range(count):
                theta = 2.0 * math.pi * index / float(count)
                x_value = ring_radius * math.cos(theta)
                y_value = ring_radius * math.sin(theta)
                ring.append(label)
                nodes.append({
                    "label": label,
                    "coordinates": [safe_float(x_value), safe_float(y_value), safe_float(z_value)],
                    "displacement": [0.0, 0.0, 0.0],
                    "deformed": [safe_float(x_value), safe_float(y_value), safe_float(z_value)],
                    "visualOnly": True,
                })
                label += 1
        rings.append(ring)

    elements = []
    element_label = PROJECTILE_ELEMENT_OFFSET
    tail = rings[0]
    shoulder = rings[1]
    tip = rings[2][0]
    for index in range(len(tail)):
        next_index = (index + 1) % len(tail)
        elements.append({
            "label": element_label,
            "type": "S4R",
            "connectivity": [tail[index], tail[next_index], shoulder[next_index], shoulder[index]],
            "mises": stress_level,
            "value": stress_level,
            "color": "#c7c9ce",
            "visualOnly": True,
        })
        element_label += 1
        elements.append({
            "label": element_label,
            "type": "S3R",
            "connectivity": [shoulder[index], shoulder[next_index], tip],
            "mises": stress_level,
            "value": stress_level,
            "color": "#d9dadd",
            "visualOnly": True,
        })
        element_label += 1
    return nodes, elements


def build_frame_payload(instance, frame, frame_index, source_frame_index, surface, parameters):
    displacement = frame.fieldOutputs["U"] if "U" in frame.fieldOutputs else None
    stress = frame.fieldOutputs["S"] if "S" in frame.fieldOutputs else None

    displacement_by_node = {}
    max_displacement = 0.0
    if displacement:
        for value in displacement.values:
            vector = [safe_float(value.data[0]), safe_float(value.data[1]), safe_float(value.data[2])]
            displacement_by_node[int(value.nodeLabel)] = vector
            max_displacement = max(max_displacement, vector_magnitude(vector))

    stress_sum = {}
    stress_count = {}
    if stress:
        for value in stress.values:
            label = int(value.elementLabel)
            stress_sum[label] = stress_sum.get(label, 0.0) + safe_float(value.mises)
            stress_count[label] = stress_count.get(label, 0) + 1

    surface_node_labels = set()
    for face in surface:
        for label in face["labels"]:
            surface_node_labels.add(int(label))

    nodes = []
    node_by_label = dict((int(node.label), node) for node in instance.nodes)
    for label in sorted(surface_node_labels):
        node = node_by_label[label]
        displacement_value = displacement_by_node.get(label, [0.0, 0.0, 0.0])
        coordinates = [safe_float(node.coordinates[0]), safe_float(node.coordinates[1]), safe_float(node.coordinates[2])]
        deformed = [
            coordinates[0] + displacement_value[0] * DEFORMATION_SCALE,
            coordinates[1] + displacement_value[1] * DEFORMATION_SCALE,
            coordinates[2] + displacement_value[2] * DEFORMATION_SCALE,
        ]
        nodes.append({
            "label": label,
            "coordinates": coordinates,
            "displacement": displacement_value,
            "deformed": deformed,
        })

    elements = []
    min_mises = None
    max_mises = None
    for index, face in enumerate(surface):
        source_element = int(face["sourceElement"])
        count = stress_count.get(source_element, 0)
        mises = safe_float(stress_sum.get(source_element, 0.0) / float(count)) if count else 0.0
        min_mises = mises if min_mises is None else min(min_mises, mises)
        max_mises = mises if max_mises is None else max(max_mises, mises)
        elements.append({
            "label": index + 1,
            "type": "S4R" if len(face["labels"]) == 4 else "S3R",
            "connectivity": [int(label) for label in face["labels"]],
            "mises": mises,
            "value": mises,
        })

    if min_mises is None:
        min_mises = 0.0
    if max_mises is None or max_mises <= min_mises:
        max_mises = min_mises + 1.0

    projectile_nodes, projectile_elements = build_projectile_mesh(parameters, safe_float(frame.frameValue), min_mises)
    nodes.extend(projectile_nodes)
    elements.extend(projectile_elements)

    return {
        "frame": int(frame_index),
        "sourceFrame": int(source_frame_index),
        "timeMs": safe_float(frame.frameValue) * 1000.0,
        "deformationScale": DEFORMATION_SCALE,
        "fieldLabel": "S, Mises",
        "elementType": "S4R",
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
    odb = openOdb(path=ODB_PATH, readOnly=True)
    try:
        instance = odb.rootAssembly.instances[INSTANCE_NAME]
        frames = [frame for frame in odb.steps[STEP_NAME].frames if "U" in frame.fieldOutputs]
        if not frames:
            raise RuntimeError("No displacement frames found in {}".format(ODB_PATH))
        surface = surface_faces(instance, parameters)
        exported_frames = []
        for output_index, (source_index, frame) in enumerate(selected_frames(frames)):
            exported_frames.append(build_frame_payload(instance, frame, output_index, source_index, surface, parameters))
        first_frame = exported_frames[0]
        payload = {
            "schemaVersion": 1,
            "source": "TextToCAE_BulletPlate_Penetration_Rigid.odb",
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
        json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
        handle.write("\n")
    print("Exported {}".format(OUT_PATH))


if __name__ == "__main__":
    main()
