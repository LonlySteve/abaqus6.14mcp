"""Export Abaqus ODB mesh and result fields for the perforated plate viewer."""

from __future__ import print_function

import json
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
ODB_PATH = os.path.join(ROOT, "TextToCAE_HolePlate.odb")
OUT_PATH = os.path.join(ROOT, "result_mesh.json")
INSTANCE_NAME = "PLATE-1"
STEP_NAME = "Load"
DEFORMATION_SCALE = 18.0


def vector_magnitude(values):
    total = 0.0
    for value in values:
        total += value * value
    return total ** 0.5


def main():
    odb = openOdb(path=ODB_PATH, readOnly=True)
    try:
        instance = odb.rootAssembly.instances[INSTANCE_NAME]
        frame = odb.steps[STEP_NAME].frames[-1]
        displacement = frame.fieldOutputs["U"]
        stress = frame.fieldOutputs["S"]

        displacement_by_node = {}
        for value in displacement.values:
            displacement_by_node[value.nodeLabel] = [float(value.data[0]), float(value.data[1]), float(value.data[2])]

        stress_sum_by_element = {}
        stress_count_by_element = {}
        for value in stress.values:
            label = value.elementLabel
            stress_sum_by_element[label] = stress_sum_by_element.get(label, 0.0) + float(value.mises)
            stress_count_by_element[label] = stress_count_by_element.get(label, 0) + 1

        nodes = []
        max_displacement = 0.0
        for node in instance.nodes:
            displacement_value = displacement_by_node.get(node.label, [0.0, 0.0, 0.0])
            max_displacement = max(max_displacement, vector_magnitude(displacement_value))
            coordinates = [float(node.coordinates[0]), float(node.coordinates[1]), float(node.coordinates[2])]
            deformed = [
                coordinates[0] + displacement_value[0] * DEFORMATION_SCALE,
                coordinates[1] + displacement_value[1] * DEFORMATION_SCALE,
                coordinates[2] + displacement_value[2] * DEFORMATION_SCALE,
            ]
            nodes.append({
                "label": int(node.label),
                "coordinates": coordinates,
                "displacement": displacement_value,
                "deformed": deformed,
            })

        elements = []
        min_mises = None
        max_mises = None
        element_types = {}
        for element in instance.elements:
            label = int(element.label)
            count = stress_count_by_element.get(label, 0)
            mises = stress_sum_by_element.get(label, 0.0) / float(count) if count else 0.0
            min_mises = mises if min_mises is None else min(min_mises, mises)
            max_mises = mises if max_mises is None else max(max_mises, mises)
            element_type = str(element.type)
            element_types[element_type] = element_types.get(element_type, 0) + 1
            elements.append({
                "label": label,
                "type": element_type,
                "connectivity": [int(node_label) for node_label in element.connectivity],
                "mises": mises,
            })

        dominant_element_type = ""
        if element_types:
            dominant_element_type = sorted(element_types.items(), key=lambda item: item[1], reverse=True)[0][0]

        payload = {
            "schemaVersion": 1,
            "source": "TextToCAE_HolePlate.odb",
            "instance": INSTANCE_NAME,
            "step": STEP_NAME,
            "frame": len(odb.steps[STEP_NAME].frames) - 1,
            "deformationScale": DEFORMATION_SCALE,
            "elementType": dominant_element_type,
            "nodes": nodes,
            "elements": elements,
            "fieldRanges": {
                "misesMin": min_mises,
                "misesMax": max_mises,
                "maxDisplacement": max_displacement,
            },
        }
    finally:
        odb.close()

    with open(OUT_PATH, "w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print("Exported {}".format(OUT_PATH))


if __name__ == "__main__":
    main()
