"""Export Abaqus ODB modal mesh and all mode shapes for the perforated plate viewer."""

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
ODB_PATH = os.path.join(ROOT, "TextToCAE_HolePlate_Modal.odb")
OUT_PATH = os.path.join(ROOT, "result_mesh.json")
INSTANCE_NAME = "PLATE-1"
STEP_NAME = "Modal"
MODE_SHAPE_SCALE_RATIO = 0.12


def vector_magnitude(values):
    total = 0.0
    for value in values:
        value = safe_float(value)
        total += value * value
    return total ** 0.5


def safe_float(value, fallback=0.0):
    try:
        number = float(value)
    except Exception:
        return fallback
    if math.isnan(number) or math.isinf(number):
        return fallback
    return number


def mode_frequency(frame):
    frequency = getattr(frame, "frequency", None)
    if frequency is not None:
        return safe_float(frequency)
    description = getattr(frame, "description", "")
    marker = "Freq ="
    if marker in description:
        try:
            return safe_float(description.split(marker, 1)[1].split()[0])
        except Exception:
            return 0.0
    return 0.0


def model_size_for_instance(instance):
    coordinate_bounds = [
        [float("inf"), float("-inf")],
        [float("inf"), float("-inf")],
        [float("inf"), float("-inf")],
    ]
    for node in instance.nodes:
        for index in range(3):
            coordinate = safe_float(node.coordinates[index])
            coordinate_bounds[index][0] = min(coordinate_bounds[index][0], coordinate)
            coordinate_bounds[index][1] = max(coordinate_bounds[index][1], coordinate)
    return max([axis[1] - axis[0] for axis in coordinate_bounds] + [1.0])


def build_mode_payload(instance, frame, mode_index, visual_amplitude):
    mode_number = getattr(frame, "mode", None) or mode_index
    frequency = mode_frequency(frame)
    displacement = frame.fieldOutputs["U"]

    displacement_by_node = {}
    raw_max_displacement = 0.0
    for value in displacement.values:
        vector = [safe_float(value.data[0]), safe_float(value.data[1]), safe_float(value.data[2])]
        displacement_by_node[value.nodeLabel] = vector
        raw_max_displacement = max(raw_max_displacement, vector_magnitude(vector))
    normalization = raw_max_displacement if raw_max_displacement > 0.0 else 1.0

    nodes = []
    normalized_magnitude_by_node = {}
    for node in instance.nodes:
        raw_displacement = displacement_by_node.get(node.label, [0.0, 0.0, 0.0])
        normalized = [
            raw_displacement[0] / normalization,
            raw_displacement[1] / normalization,
            raw_displacement[2] / normalization,
        ]
        normalized_magnitude = vector_magnitude(normalized)
        normalized_magnitude_by_node[node.label] = normalized_magnitude
        coordinates = [
            safe_float(node.coordinates[0]),
            safe_float(node.coordinates[1]),
            safe_float(node.coordinates[2]),
        ]
        deformed = [
            coordinates[0] + normalized[0] * visual_amplitude,
            coordinates[1] + normalized[1] * visual_amplitude,
            coordinates[2] + normalized[2] * visual_amplitude,
        ]
        nodes.append({
            "label": int(node.label),
            "coordinates": coordinates,
            "displacement": normalized,
            "modalMagnitude": normalized_magnitude,
            "deformed": deformed,
        })

    elements = []
    min_value = None
    max_value = None
    element_types = {}
    for element in instance.elements:
        label = int(element.label)
        connectivity = [int(node_label) for node_label in element.connectivity]
        values = [normalized_magnitude_by_node.get(node_label, 0.0) for node_label in connectivity]
        field_value = safe_float(sum(values) / float(len(values))) if values else 0.0
        min_value = field_value if min_value is None else min(min_value, field_value)
        max_value = field_value if max_value is None else max(max_value, field_value)
        element_type = str(element.type)
        element_types[element_type] = element_types.get(element_type, 0) + 1
        elements.append({
            "label": label,
            "type": element_type,
            "connectivity": connectivity,
            "mises": field_value,
            "value": field_value,
        })

    dominant_element_type = ""
    if element_types:
        dominant_element_type = sorted(element_types.items(), key=lambda item: item[1], reverse=True)[0][0]

    return {
        "mode": int(mode_number),
        "frequencyHz": safe_float(frequency),
        "deformationScale": visual_amplitude,
        "fieldLabel": "U, Magnitude",
        "elementType": dominant_element_type,
        "nodes": nodes,
        "elements": elements,
        "fieldRanges": {
            "misesMin": min_value,
            "misesMax": max_value,
            "valueMin": min_value,
            "valueMax": max_value,
            "maxDisplacement": 1.0,
            "rawMaxDisplacement": raw_max_displacement,
        },
    }


def main():
    odb = openOdb(path=ODB_PATH, readOnly=True)
    try:
        instance = odb.rootAssembly.instances[INSTANCE_NAME]
        modal_frames = []
        for candidate_frame in odb.steps[STEP_NAME].frames:
            if "U" not in candidate_frame.fieldOutputs:
                continue
            candidate_raw_max = 0.0
            for value in candidate_frame.fieldOutputs["U"].values:
                candidate_raw_max = max(candidate_raw_max, vector_magnitude(value.data))
            if candidate_raw_max <= 0.0:
                continue
            modal_frames.append(candidate_frame)
        if not modal_frames:
            raise RuntimeError("No modal displacement frames found in {}".format(ODB_PATH))
        model_size = model_size_for_instance(instance)
        visual_amplitude = model_size * MODE_SHAPE_SCALE_RATIO
        exported_modes = [
            build_mode_payload(instance, frame, index + 1, visual_amplitude)
            for index, frame in enumerate(modal_frames)
        ]
        first_mode = exported_modes[0]

        payload = {
            "schemaVersion": 1,
            "source": "TextToCAE_HolePlate_Modal.odb",
            "analysisType": "modal",
            "instance": INSTANCE_NAME,
            "step": STEP_NAME,
            "frame": 1,
            "mode": first_mode["mode"],
            "frequencyHz": first_mode["frequencyHz"],
            "deformationScale": first_mode["deformationScale"],
            "fieldLabel": first_mode["fieldLabel"],
            "elementType": first_mode["elementType"],
            "nodes": first_mode["nodes"],
            "elements": first_mode["elements"],
            "fieldRanges": first_mode["fieldRanges"],
            "modalFrames": exported_modes,
        }
    finally:
        odb.close()

    with open(OUT_PATH, "w") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print("Exported {}".format(OUT_PATH))


if __name__ == "__main__":
    main()
