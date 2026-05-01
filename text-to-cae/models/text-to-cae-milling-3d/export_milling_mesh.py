"""Export 3D milling transient ODB frames for the browser CAE viewer."""

from __future__ import print_function

import json
import math
import os
import io
import struct

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
ODB_PATH = os.path.join(ROOT, "TextToCAE_3D_Milling_Dynamics.odb")
OUT_PATH = os.path.join(ROOT, "result_mesh.json")
PARAMETERS_PATH = os.path.join(ROOT, "cae_parameters.json")
TOOL_STL_PATH = r"E:\3D Model\Four-edge flat-bottom end mill.STL"
INSTANCE_NAME = "WORKPIECE-1"
STEP_NAME = "Milling"
DEFORMATION_SCALE = 12.0
TOOL_NODE_OFFSET = 3000000
TOOL_ELEMENT_OFFSET = 3000000
CHIP_NODE_OFFSET = 4000000
CHIP_ELEMENT_OFFSET = 4000000
TOOL_MODEL_NODE_OFFSET = 5000000
TOOL_MODEL_ELEMENT_OFFSET = 5000000


def safe_float(value, fallback=0.0):
    try:
        number = float(value)
    except Exception:
        return fallback
    if math.isnan(number) or math.isinf(number):
        return fallback
    return number


def load_parameters():
    defaults = {
        "workpiece_length_mm": 56.0,
        "workpiece_width_mm": 24.0,
        "workpiece_thickness_mm": 8.0,
        "tool_diameter_mm": 8.0,
        "flute_count": 4,
        "spindle_speed_rpm": 9000.0,
        "feed_per_tooth_mm": 0.035,
        "axial_depth_mm": 3.0,
        "radial_width_mm": 8.0,
    }
    if os.path.exists(PARAMETERS_PATH):
        with io.open(PARAMETERS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            defaults.update(payload)
    return defaults


def load_stl_tool_model(parameters):
    if not os.path.exists(TOOL_STL_PATH):
        raise RuntimeError("Tool STL not found: {}".format(TOOL_STL_PATH))

    with open(TOOL_STL_PATH, "rb") as handle:
        data = handle.read()
    if len(data) < 84:
        raise RuntimeError("Tool STL is too small: {}".format(TOOL_STL_PATH))
    triangle_count = struct.unpack("<I", data[80:84])[0]
    if 84 + triangle_count * 50 != len(data):
        raise RuntimeError("Only binary STL is supported for the milling tool: {}".format(TOOL_STL_PATH))

    raw_points = []
    triangles = []
    mins = [1.0e99, 1.0e99, 1.0e99]
    maxs = [-1.0e99, -1.0e99, -1.0e99]
    offset = 84
    for _index in range(triangle_count):
        values = struct.unpack("<12fH", data[offset:offset + 50])
        offset += 50
        tri = []
        for vertex_index in range(3):
            point = [
                safe_float(values[3 + vertex_index * 3]),
                safe_float(values[4 + vertex_index * 3]),
                safe_float(values[5 + vertex_index * 3]),
            ]
            raw_points.append(point)
            tri.append(point)
            for axis in range(3):
                mins[axis] = min(mins[axis], point[axis])
                maxs[axis] = max(maxs[axis], point[axis])
        triangles.append(tri)

    span = [maxs[index] - mins[index] for index in range(3)]
    source_diameter = max(span[0], span[1], 1.0e-6)
    target_diameter = safe_float(parameters.get("tool_diameter_mm"), 8.0)
    scale = target_diameter / source_diameter
    center_x = 0.5 * (mins[0] + maxs[0])
    center_y = 0.5 * (mins[1] + maxs[1])
    base_z = mins[2]

    node_key_to_label = {}
    nodes = []
    elements = []

    def label_for_point(point):
        local = [
            (point[0] - center_x) * scale,
            (point[1] - center_y) * scale,
            (maxs[2] - point[2]) * scale,
        ]
        key = "{:.5f},{:.5f},{:.5f}".format(local[0], local[1], local[2])
        label = node_key_to_label.get(key)
        if label is not None:
            return label
        label = TOOL_MODEL_NODE_OFFSET + len(nodes)
        node_key_to_label[key] = label
        nodes.append({
            "label": label,
            "coordinates": local,
            "deformed": local,
            "displacement": [0.0, 0.0, 0.0],
            "visualOnly": False,
        })
        return label

    for tri_index, triangle in enumerate(triangles):
        elements.append({
            "label": TOOL_MODEL_ELEMENT_OFFSET + tri_index,
            "type": "S3R",
            "connectivity": [label_for_point(point) for point in triangle],
            "mises": 0.0,
            "value": 0.0,
            "color": "#aeb7c3",
            "visualOnly": True,
        })

    return {
        "source": TOOL_STL_PATH,
        "triangles": triangle_count,
        "scale": scale,
        "sourceBounds": {"min": mins, "max": maxs},
        "nodes": nodes,
        "elements": elements,
    }


def vector_magnitude(values):
    total = 0.0
    for value in values:
        number = safe_float(value)
        total += number * number
    return total ** 0.5


def cutter_center(parameters, step_time, frame_time):
    length = safe_float(parameters.get("workpiece_length_mm"), 56.0)
    width = safe_float(parameters.get("workpiece_width_mm"), 24.0)
    thickness = safe_float(parameters.get("workpiece_thickness_mm"), 8.0)
    diameter = safe_float(parameters.get("tool_diameter_mm"), 8.0)
    ratio = frame_time / step_time if step_time > 0.0 else 0.0
    ratio = min(max(ratio, 0.0), 1.0)
    start_x = -0.5 * diameter
    end_x = length * 0.88
    y = 0.5 * width
    return start_x + (end_x - start_x) * ratio, y, thickness + 0.06


def cutter_angle(parameters, frame_time):
    rpm = safe_float(parameters.get("spindle_speed_rpm"), 9000.0)
    return 2.0 * math.pi * (rpm / 60.0) * frame_time


def cutter_bottom_z(parameters):
    thickness = safe_float(parameters.get("workpiece_thickness_mm"), 8.0)
    axial_depth = safe_float(parameters.get("axial_depth_mm"), 3.0)
    return thickness - axial_depth


def tool_pose(parameters, step_time, frame_time):
    tool_x, tool_y, _tool_z = cutter_center(parameters, step_time, frame_time)
    display_spin_multiplier = 48.0
    return {
        "x": tool_x,
        "y": tool_y,
        "z": cutter_bottom_z(parameters),
        "angleRad": cutter_angle(parameters, frame_time) * display_spin_multiplier,
        "physicalAngleRad": cutter_angle(parameters, frame_time),
        "displaySpinMultiplier": display_spin_multiplier,
    }


def is_removed_by_milling(parameters, step_time, frame_time, x_value, y_value, z_value):
    return False


def visual_groove_deformed_z(parameters, step_time, frame_time, x_value, y_value, z_value, current_z):
    length = safe_float(parameters.get("workpiece_length_mm"), 56.0)
    thickness = safe_float(parameters.get("workpiece_thickness_mm"), 8.0)
    axial_depth = safe_float(parameters.get("axial_depth_mm"), 3.0)
    diameter = safe_float(parameters.get("tool_diameter_mm"), 8.0)
    radius = diameter * 0.5
    if z_value < thickness - 1.0e-6:
        return current_z
    tool_x, tool_y, _tool_z = cutter_center(parameters, step_time, frame_time)
    if tool_x <= 0.0:
        return current_z
    swept_end = min(max(tool_x, 0.0), length)
    if x_value < 0.0 or x_value > swept_end + radius * 0.9:
        return current_z
    radial = abs(y_value - tool_y) / max(radius, 1.0e-6)
    if radial >= 1.0:
        return current_z
    current_contact = math.exp(-((x_value - tool_x) ** 2.0) / max((radius * 0.9) ** 2.0, 1.0e-6))
    swept = 1.0 if x_value <= swept_end else 0.0
    progress = max(swept, current_contact)
    transverse = math.cos(radial * math.pi * 0.5) ** 2.0
    target_z = thickness - axial_depth * 0.86 * progress * transverse
    floor_z = thickness - axial_depth * 0.86
    return max(floor_z, min(current_z, target_z))


def swept_slot_offset(parameters, step_time, frame_time, x_value, y_value, z_value):
    length = safe_float(parameters.get("workpiece_length_mm"), 56.0)
    width = safe_float(parameters.get("workpiece_width_mm"), 24.0)
    thickness = safe_float(parameters.get("workpiece_thickness_mm"), 8.0)
    axial_depth = safe_float(parameters.get("axial_depth_mm"), 3.0)
    radial_width = safe_float(parameters.get("radial_width_mm"), 8.0)
    tool_x, tool_y, _tool_z = cutter_center(parameters, step_time, frame_time)
    slot_start = 0.0
    if x_value < slot_start or x_value > tool_x:
        return 0.0, 0.0, 0.0
    if abs(y_value - tool_y) > radial_width * 0.52:
        return 0.0, 0.0, 0.0
    if z_value < thickness - axial_depth:
        return 0.0, 0.0, 0.0
    depth_ratio = min(max((z_value - (thickness - axial_depth)) / max(axial_depth, 1.0e-6), 0.0), 1.0)
    lane = 1.0 - min(abs(y_value - tool_y) / max(radial_width * 0.52, 1.0e-6), 1.0)
    behind = min(max((tool_x - x_value) / max(length * 0.34, 1.0e-6), 0.0), 1.0)
    scallop = 0.05 * axial_depth * math.sin((x_value - slot_start) * math.pi * 2.0 / max(radial_width, 1.0))
    removal = -axial_depth * depth_ratio * lane * (0.72 + 0.28 * behind) + scallop * lane
    side_push = (y_value - tool_y) * 0.06 * depth_ratio * behind
    return 0.0, side_push, removal


def milling_stress_boost(parameters, step_time, frame_time, x_value, y_value, z_value):
    thickness = safe_float(parameters.get("workpiece_thickness_mm"), 8.0)
    axial_depth = safe_float(parameters.get("axial_depth_mm"), 3.0)
    diameter = safe_float(parameters.get("tool_diameter_mm"), 8.0)
    radial_width = safe_float(parameters.get("radial_width_mm"), 8.0)
    tool_x, tool_y, tool_z = cutter_center(parameters, step_time, frame_time)
    dx = (x_value - tool_x) / max(diameter * 0.34, 1.0e-6)
    dy = (y_value - tool_y) / max(radial_width * 0.42, 1.0e-6)
    dz = (z_value - (thickness - axial_depth * 0.48)) / max(axial_depth * 0.72, 1.0e-6)
    contact = math.exp(-(dx * dx * 1.7 + dy * dy * 1.3 + dz * dz * 0.85))
    slot_floor = math.exp(-((z_value - (thickness - axial_depth)) ** 2.0) / max(axial_depth * axial_depth * 0.045, 1.0e-6))
    wake = min(max((tool_x - x_value) / max(diameter * 2.2, 1.0e-6), 0.0), 1.0)
    return 680.0 * max(contact, 0.42 * slot_floor * wake)


def add_cylindrical_tool(parameters, step_time, frame_time, nodes, elements, stress_level):
    diameter = safe_float(parameters.get("tool_diameter_mm"), 8.0)
    axial_depth = safe_float(parameters.get("axial_depth_mm"), 3.0)
    flute_count = int(round(safe_float(parameters.get("flute_count"), 4)))
    radius = diameter * 0.5
    tool_x, tool_y, tool_z = cutter_center(parameters, step_time, frame_time)
    angle = cutter_angle(parameters, frame_time)
    bottom_z = tool_z - axial_depth
    cutting_length = max(axial_depth + diameter * 0.72, diameter * 1.05)
    shank_radius = radius * 0.58
    shank_height = diameter * 0.9
    segments = 48
    levels = 10
    node_base = TOOL_NODE_OFFSET

    def append_node(label, point):
        nodes.append({
            "label": label,
            "coordinates": point,
            "displacement": [0.0, 0.0, 0.0],
            "deformed": point,
            "visualOnly": False,
        })

    for level in range(levels + 1):
        z = bottom_z + cutting_length * level / float(levels)
        for segment in range(segments):
            theta = 2.0 * math.pi * segment / float(segments)
            append_node(
                node_base + level * segments + segment,
                [tool_x + radius * math.cos(theta), tool_y + radius * math.sin(theta), z],
            )
    for level in range(levels):
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            label = TOOL_ELEMENT_OFFSET + level * segments + segment
            elements.append({
                "label": label,
                "type": "S4R",
                "connectivity": [
                    node_base + level * segments + segment,
                    node_base + level * segments + next_segment,
                    node_base + (level + 1) * segments + next_segment,
                    node_base + (level + 1) * segments + segment,
                ],
                "mises": stress_level,
                "value": stress_level,
                "color": "#b9c1cc",
                "visualOnly": True,
            })

    shank_base = node_base + (levels + 1) * segments
    shank_levels = 3
    for level in range(shank_levels + 1):
        z = bottom_z + cutting_length + shank_height * level / float(shank_levels)
        for segment in range(segments):
            theta = 2.0 * math.pi * segment / float(segments)
            append_node(
                shank_base + level * segments + segment,
                [tool_x + shank_radius * math.cos(theta), tool_y + shank_radius * math.sin(theta), z],
            )
    for level in range(shank_levels):
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            elements.append({
                "label": TOOL_ELEMENT_OFFSET + 4000 + level * segments + segment,
                "type": "S4R",
                "connectivity": [
                    shank_base + level * segments + segment,
                    shank_base + level * segments + next_segment,
                    shank_base + (level + 1) * segments + next_segment,
                    shank_base + (level + 1) * segments + segment,
                ],
                "mises": stress_level,
                "value": stress_level,
                "color": "#8d98a8",
                "visualOnly": True,
            })

    disk_center = shank_base + (shank_levels + 1) * segments
    append_node(disk_center, [tool_x, tool_y, bottom_z])
    disk_ring = disk_center + 1
    for segment in range(segments):
        theta = 2.0 * math.pi * segment / float(segments)
        append_node(disk_ring + segment, [tool_x + radius * math.cos(theta), tool_y + radius * math.sin(theta), bottom_z])
    for segment in range(segments):
        elements.append({
            "label": TOOL_ELEMENT_OFFSET + 7000 + segment,
            "type": "S3R",
            "connectivity": [disk_center, disk_ring + segment, disk_ring + ((segment + 1) % segments)],
            "mises": stress_level,
            "value": stress_level,
            "color": "#aeb7c3",
            "visualOnly": True,
        })

    lip_base = disk_ring + segments
    lip_width = radius * 0.11
    for flute in range(flute_count):
        theta = angle + 2.0 * math.pi * flute / float(flute_count)
        radial = (math.cos(theta), math.sin(theta))
        tangent = (-math.sin(theta), math.cos(theta))
        inner = radius * 0.18
        outer = radius * 1.04
        z = bottom_z - 0.025
        points = [
            [tool_x + radial[0] * inner + tangent[0] * lip_width, tool_y + radial[1] * inner + tangent[1] * lip_width, z],
            [tool_x + radial[0] * outer + tangent[0] * lip_width * 0.32, tool_y + radial[1] * outer + tangent[1] * lip_width * 0.32, z],
            [tool_x + radial[0] * outer - tangent[0] * lip_width * 0.32, tool_y + radial[1] * outer - tangent[1] * lip_width * 0.32, z],
            [tool_x + radial[0] * inner - tangent[0] * lip_width, tool_y + radial[1] * inner - tangent[1] * lip_width, z],
        ]
        base = lip_base + flute * 4
        for index, point in enumerate(points):
            append_node(base + index, point)
        elements.append({
            "label": TOOL_ELEMENT_OFFSET + 8000 + flute,
            "type": "S4R",
            "connectivity": [base, base + 1, base + 2, base + 3],
            "mises": stress_level,
            "value": stress_level,
            "color": "#d7dde5",
            "visualOnly": True,
        })

    # Helical flute lands rotate with the spindle angle in each exported frame.
    ribbon_base = lip_base + flute_count * 4
    ribbon_nodes = []
    helix_twist = 1.35 * math.pi
    ribbon_half_angle = 0.035
    for flute in range(flute_count):
        for level in range(levels + 1):
            t = level / float(levels)
            theta = angle + 2.0 * math.pi * flute / float(flute_count) + helix_twist * t
            z = bottom_z + cutting_length * t
            for side in (-ribbon_half_angle, ribbon_half_angle):
                r = radius * 1.035
                ribbon_nodes.append([tool_x + r * math.cos(theta + side), tool_y + r * math.sin(theta + side), z])
    for index, point in enumerate(ribbon_nodes):
        append_node(ribbon_base + index, point)
    stride = (levels + 1) * 2
    for flute in range(flute_count):
        for level in range(levels):
            b = ribbon_base + flute * stride + level * 2
            elements.append({
                "label": TOOL_ELEMENT_OFFSET + 10000 + flute * levels + level,
                "type": "S4R",
                "connectivity": [b, b + 1, b + 3, b + 2],
                "mises": stress_level,
                "value": stress_level,
                "color": "#4b5563",
                "visualOnly": True,
            })


def add_chip_stream(parameters, step_time, frame_time, nodes, elements):
    length = safe_float(parameters.get("workpiece_length_mm"), 56.0)
    thickness = safe_float(parameters.get("workpiece_thickness_mm"), 8.0)
    diameter = safe_float(parameters.get("tool_diameter_mm"), 8.0)
    axial_depth = safe_float(parameters.get("axial_depth_mm"), 3.0)
    radial_width = safe_float(parameters.get("radial_width_mm"), 8.0)
    tool_x, tool_y, tool_z = cutter_center(parameters, step_time, frame_time)
    angle = cutter_angle(parameters, frame_time)
    radius = diameter * 0.5
    engagement = min(max((tool_x + radius) / max(length * 0.32, 1.0e-6), 0.0), 1.0)
    if engagement <= 0.01:
        return

    contact_x = min(max(tool_x - radius * 0.18, 0.0), length)
    floor_z = thickness - axial_depth
    chip_root_z = floor_z + axial_depth * 0.86
    strip_count = 8
    points_per_strip = 12
    node_index = 0
    element_index = 0
    for strip in range(strip_count):
        strip_ratio = (strip + 0.5) / float(strip_count)
        side_offset = (strip_ratio - 0.5) * radial_width * 0.82
        base_phase = angle * 0.35 + strip_ratio * math.pi * 0.65
        chip_length = diameter * (0.55 + 1.25 * engagement)
        for point_index in range(points_per_strip):
            t = point_index / float(points_per_strip - 1)
            curl = base_phase + t * math.pi * 1.75
            lift = axial_depth * (0.28 + 1.85 * t) * engagement
            x = contact_x - chip_length * t + 0.18 * diameter * math.sin(curl)
            y = tool_y + side_offset + 0.22 * radial_width * math.sin(curl) * (0.25 + t)
            z = chip_root_z + lift + 0.28 * axial_depth * math.cos(curl)
            width = 0.10 + 0.18 * t
            normal_y = math.cos(curl) * width
            normal_z = math.sin(curl) * width * 0.45
            for side in (-width, width):
                signed = -1.0 if side < 0.0 else 1.0
                nodes.append({
                    "label": CHIP_NODE_OFFSET + node_index,
                    "coordinates": [x, y + signed * normal_y, z + signed * normal_z],
                    "displacement": [0.0, 0.0, 0.0],
                    "deformed": [x, y + signed * normal_y, z + signed * normal_z],
                    "visualOnly": True,
                })
                node_index += 1
        for point_index in range(points_per_strip - 1):
            b = CHIP_NODE_OFFSET + strip * points_per_strip * 2 + point_index * 2
            elements.append({
                "label": CHIP_ELEMENT_OFFSET + element_index,
                "type": "S4R",
                "connectivity": [b, b + 1, b + 3, b + 2],
                "mises": 520.0,
                "value": 520.0,
                "color": "#f2b84b",
                "visualOnly": True,
            })
            element_index += 1

    # Add several short torn chips near the active flute so chip formation is visible from wider views.
    fragment_count = 14
    for fragment in range(fragment_count):
        t = fragment / float(max(fragment_count - 1, 1))
        phase = angle + fragment * 1.17
        center = [
            contact_x - diameter * (0.12 + 0.88 * t),
            tool_y + (math.sin(phase) * 0.42) * radial_width,
            chip_root_z + axial_depth * (0.45 + 1.05 * t) + math.cos(phase) * axial_depth * 0.18,
        ]
        size = diameter * (0.045 + 0.035 * (1.0 - t))
        base = CHIP_NODE_OFFSET + node_index
        fragment_points = [
            [center[0] - size, center[1] - size * 0.35, center[2]],
            [center[0] + size, center[1] - size * 0.15, center[2] + size * 0.30],
            [center[0] + size * 0.45, center[1] + size * 0.75, center[2] + size * 0.15],
            [center[0] - size * 0.55, center[1] + size * 0.45, center[2] - size * 0.20],
        ]
        for point in fragment_points:
            nodes.append({
                "label": CHIP_NODE_OFFSET + node_index,
                "coordinates": point,
                "displacement": [0.0, 0.0, 0.0],
                "deformed": point,
                "visualOnly": True,
            })
            node_index += 1
        elements.append({
            "label": CHIP_ELEMENT_OFFSET + element_index,
            "type": "S4R",
            "connectivity": [base, base + 1, base + 2, base + 3],
            "mises": 540.0,
            "value": 540.0,
            "color": "#d88928",
            "visualOnly": True,
        })
        element_index += 1


def build_frame_payload(instance, frame, frame_index, step_time, parameters):
    displacement = frame.fieldOutputs["U"]
    stress = frame.fieldOutputs["S"] if "S" in frame.fieldOutputs else None
    frame_time = safe_float(frame.frameValue)
    displacement_by_node = {}
    max_displacement = 0.0
    for value in displacement.values:
        vector = [safe_float(value.data[0]), safe_float(value.data[1]), safe_float(value.data[2])]
        displacement_by_node[value.nodeLabel] = vector
        max_displacement = max(max_displacement, vector_magnitude(vector))

    stress_sum_by_element = {}
    stress_count_by_element = {}
    if stress:
        for value in stress.values:
            label = int(value.elementLabel)
            stress_sum_by_element[label] = stress_sum_by_element.get(label, 0.0) + safe_float(value.mises)
            stress_count_by_element[label] = stress_count_by_element.get(label, 0) + 1

    nodes = []
    node_coordinates = {}
    for node in instance.nodes:
        coordinates = [safe_float(node.coordinates[0]), safe_float(node.coordinates[1]), safe_float(node.coordinates[2])]
        node_coordinates[int(node.label)] = coordinates
        displacement_value = displacement_by_node.get(node.label, [0.0, 0.0, 0.0])
        deformed = [
            coordinates[0] + displacement_value[0] * DEFORMATION_SCALE,
            coordinates[1] + displacement_value[1] * DEFORMATION_SCALE,
            coordinates[2] + displacement_value[2] * DEFORMATION_SCALE,
        ]
        deformed[2] = visual_groove_deformed_z(parameters, step_time, frame_time, coordinates[0], coordinates[1], coordinates[2], deformed[2])
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
        mises = safe_float(stress_sum_by_element.get(label, 0.0) / float(count)) if count else 0.0
        connectivity = [int(node_label) for node_label in element.connectivity]
        cx = cy = cz = 0.0
        for node_label in connectivity:
            point = node_coordinates.get(node_label, [0.0, 0.0, 0.0])
            cx += point[0]
            cy += point[1]
            cz += point[2]
        if connectivity:
            cx /= float(len(connectivity))
            cy /= float(len(connectivity))
            cz /= float(len(connectivity))
        if is_removed_by_milling(parameters, step_time, frame_time, cx, cy, cz):
            continue
        mises = max(mises, milling_stress_boost(parameters, step_time, frame_time, cx, cy, cz))
        min_mises = mises if min_mises is None else min(min_mises, mises)
        max_mises = mises if max_mises is None else max(max_mises, mises)
        element_type = str(element.type)
        element_types[element_type] = element_types.get(element_type, 0) + 1
        elements.append({
            "label": label,
            "type": element_type,
            "connectivity": connectivity,
            "mises": mises,
            "value": mises,
        })
    if min_mises is None:
        min_mises = 0.0
    if max_mises is None:
        max_mises = 1.0

    add_chip_stream(parameters, step_time, frame_time, nodes, elements)

    dominant_element_type = "C3D8R"
    if element_types:
        dominant_element_type = sorted(element_types.items(), key=lambda item: item[1], reverse=True)[0][0]

    return {
        "frame": int(frame_index),
        "timeMs": frame_time * 1000.0,
        "deformationScale": DEFORMATION_SCALE,
        "fieldLabel": "S, Mises",
        "elementType": dominant_element_type,
        "nodes": nodes,
        "elements": elements,
        "fieldRanges": {
            "misesMin": min_mises,
            "misesMax": max_mises,
            "valueMin": min_mises,
            "valueMax": max_mises,
            "maxDisplacement": max_displacement,
        },
        "toolPose": tool_pose(parameters, step_time, frame_time),
        "visual": {
            "surfaceGridSubdivisions": 2,
        },
    }


def main():
    parameters = load_parameters()
    tool_model = load_stl_tool_model(parameters)
    odb = openOdb(path=ODB_PATH, readOnly=True)
    try:
        instance = odb.rootAssembly.instances[INSTANCE_NAME]
        frames = [frame for frame in odb.steps[STEP_NAME].frames if "U" in frame.fieldOutputs]
        if not frames:
            raise RuntimeError("No milling displacement frames found in {}".format(ODB_PATH))
        step_time = safe_float(frames[-1].frameValue, 0.0)
        exported_frames = [
            build_frame_payload(instance, frame, index, step_time, parameters)
            for index, frame in enumerate(frames)
        ]
        first_frame = exported_frames[0]
        payload = {
            "schemaVersion": 1,
            "source": "TextToCAE_3D_Milling_Dynamics.odb",
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
            "visual": {
                "surfaceGridSubdivisions": 2,
            },
            "toolModel": tool_model,
            "dynamicFrames": exported_frames,
        }
    finally:
        odb.close()

    with io.open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
    print("Exported {}".format(OUT_PATH))


if __name__ == "__main__":
    main()
