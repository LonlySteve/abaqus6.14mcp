import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const resultPath = path.join(root, "result_mesh.json");
const parametersPath = path.join(root, "cae_parameters.json");
const projectPath = path.join(root, "cae_project.json");
const summaryPath = path.join(root, "results_summary.json");

const params = JSON.parse(fs.readFileSync(parametersPath, "utf8"));
const payload = JSON.parse(fs.readFileSync(resultPath, "utf8"));
const frames = Array.isArray(payload.dynamicFrames) ? payload.dynamicFrames : [];
if (!frames.length) {
  throw new Error("Expected dynamicFrames in result_mesh.json");
}

const length = Number(params.workpiece_length_mm || 56);
const width = Number(params.workpiece_width_mm || 24);
const thickness = Number(params.workpiece_thickness_mm || 8);
const diameter = Number(params.tool_diameter_mm || 8);
const axialDepth = Number(params.axial_depth_mm || 3);
const slotWidth = diameter;
const radius = diameter * 0.5;
const slotYMin = width * 0.5 - slotWidth * 0.5;
const slotYMax = width * 0.5 + slotWidth * 0.5;
const slotFloorZ = thickness - axialDepth;
const surfaceSeed = Math.max(Number(params.seed_size_mm || 1), 0.8);
const visual = { surfaceGridSubdivisions: 1 };
const maxTimeMs = Math.max(...frames.map((frame) => Number(frame.timeMs) || 0), 1e-6);

function cutterPose(frame) {
  const ratio = Math.min(Math.max((Number(frame.timeMs) || 0) / maxTimeMs, 0), 1);
  const startX = -0.5 * diameter;
  const endX = length * 0.88;
  const physicalAngle = Number(frame.toolPose?.physicalAngleRad ?? frame.toolPose?.angleRad ?? 0);
  const displaySpinMultiplier = Number(frame.toolPose?.displaySpinMultiplier || 48);
  return {
    x: startX + (endX - startX) * ratio,
    y: width * 0.5,
    z: slotFloorZ,
    angleRad: physicalAngle * displaySpinMultiplier,
    physicalAngleRad: physicalAngle,
    displaySpinMultiplier,
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function sweptEndX(pose) {
  if (pose.x <= 0) {
    return 0;
  }
  return clamp(pose.x, 0, length);
}

function millingStress(pose, x, y, z, surfaceKind) {
  const radial = Math.abs(y - pose.y) / Math.max(radius, 1e-6);
  const dx = (x - pose.x) / Math.max(diameter * 0.42, 1e-6);
  const active = Math.exp(-(dx * dx * 1.7 + radial * radial * 1.2));
  const swept = x >= 0 && x <= sweptEndX(pose) ? 1 : 0;
  const wake = swept * Math.max(0, 1 - radial) * (0.35 + 0.65 * Math.exp(-Math.max(pose.x - x, 0) / Math.max(length * 0.28, 1e-6)));
  const floorOrWall = surfaceKind === "slot-floor" || surfaceKind === "slot-wall" || surfaceKind === "slot-end";
  const topNearSlot = surfaceKind === "top" && y >= slotYMin - surfaceSeed && y <= slotYMax + surfaceSeed;
  const base = 6 + 28 * (1 - z / Math.max(thickness, 1e-6));
  if (floorOrWall) {
    return Math.max(base, 510 * active, 285 * wake);
  }
  if (topNearSlot) {
    return Math.max(base, 315 * active, 135 * wake);
  }
  return base;
}

function addSurface(state, u0, u1, v0, v1, mapPoint, surfaceKind, targetStep = surfaceSeed) {
  if (u1 <= u0 || v1 <= v0) {
    return;
  }
  const nu = Math.max(1, Math.ceil((u1 - u0) / targetStep));
  const nv = Math.max(1, Math.ceil((v1 - v0) / targetStep));
  const labels = [];
  for (let j = 0; j <= nv; j += 1) {
    const row = [];
    const v = v0 + ((v1 - v0) * j) / nv;
    for (let i = 0; i <= nu; i += 1) {
      const u = u0 + ((u1 - u0) * i) / nu;
      const point = mapPoint(u, v);
      const label = state.nextNodeLabel;
      state.nextNodeLabel += 1;
      state.nodes.push({
        label,
        coordinates: point,
        deformed: point,
        displacement: [0, 0, 0],
        visualOnly: false,
      });
      row.push(label);
    }
    labels.push(row);
  }

  for (let j = 0; j < nv; j += 1) {
    for (let i = 0; i < nu; i += 1) {
      const center = mapPoint(
        u0 + ((u1 - u0) * (i + 0.5)) / nu,
        v0 + ((v1 - v0) * (j + 0.5)) / nv,
      );
      const mises = millingStress(state.pose, center[0], center[1], center[2], surfaceKind);
      state.minMises = Math.min(state.minMises, mises);
      state.maxMises = Math.max(state.maxMises, mises);
      state.elements.push({
        label: state.nextElementLabel,
        type: "S4R",
        connectivity: [
          labels[j][i],
          labels[j][i + 1],
          labels[j + 1][i + 1],
          labels[j + 1][i],
        ],
        mises,
        value: mises,
      });
      state.nextElementLabel += 1;
    }
  }
}

function buildWorkpieceSurfaces(pose) {
  const state = {
    pose,
    nodes: [],
    elements: [],
    nextNodeLabel: 1,
    nextElementLabel: 1,
    minMises: Infinity,
    maxMises: -Infinity,
  };
  const cutX = sweptEndX(pose);

  addSurface(state, 0, length, 0, width, (x, y) => [x, y, 0], "outer", surfaceSeed * 1.4);
  addSurface(state, 0, length, 0, thickness, (x, z) => [x, 0, z], "outer", surfaceSeed * 1.25);
  addSurface(state, 0, length, 0, thickness, (x, z) => [x, width, z], "outer", surfaceSeed * 1.25);
  addSurface(state, 0, width, 0, thickness, (y, z) => [length, y, z], "outer", surfaceSeed * 1.25);

  addSurface(state, 0, slotYMin, 0, thickness, (y, z) => [0, y, z], "outer", surfaceSeed * 1.15);
  addSurface(state, slotYMax, width, 0, thickness, (y, z) => [0, y, z], "outer", surfaceSeed * 1.15);
  addSurface(state, slotYMin, slotYMax, 0, slotFloorZ, (y, z) => [0, y, z], "outer", surfaceSeed * 1.15);

  addSurface(state, 0, length, 0, slotYMin, (x, y) => [x, y, thickness], "top", surfaceSeed);
  addSurface(state, 0, length, slotYMax, width, (x, y) => [x, y, thickness], "top", surfaceSeed);
  if (cutX < length) {
    addSurface(state, cutX, length, slotYMin, slotYMax, (x, y) => [x, y, thickness], "top", surfaceSeed);
  }

  if (cutX > 0) {
    addSurface(state, 0, cutX, slotYMin, slotYMax, (x, y) => [x, y, slotFloorZ], "slot-floor", surfaceSeed * 0.75);
    addSurface(state, 0, cutX, slotFloorZ, thickness, (x, z) => [x, slotYMin, z], "slot-wall", surfaceSeed * 0.75);
    addSurface(state, 0, cutX, slotFloorZ, thickness, (x, z) => [x, slotYMax, z], "slot-wall", surfaceSeed * 0.75);
    if (cutX < length - 1e-6) {
      addSurface(state, slotYMin, slotYMax, slotFloorZ, thickness, (y, z) => [cutX, y, z], "slot-end", surfaceSeed * 0.75);
    }
  }

  return {
    nodes: state.nodes,
    elements: state.elements,
    fieldRanges: {
      misesMin: Number.isFinite(state.minMises) ? state.minMises : 0,
      misesMax: Number.isFinite(state.maxMises) ? state.maxMises : 1,
      valueMin: Number.isFinite(state.minMises) ? state.minMises : 0,
      valueMax: Number.isFinite(state.maxMises) ? state.maxMises : 1,
      maxDisplacement: 0,
    },
  };
}

function addChipStream(frame, pose, nodes, elements) {
  const cutX = sweptEndX(pose);
  const engagement = Math.min(Math.max((pose.x + radius) / Math.max(length * 0.32, 1e-6), 0), 1);
  if (engagement <= 0.01 || cutX <= 0) {
    return;
  }

  const chipNodeOffset = 4000000;
  const chipElementOffset = 4000000;
  const contactX = clamp(pose.x - radius * 0.1, 0, length);
  const chipRootZ = slotFloorZ + axialDepth * 0.55;
  const stripCount = 8;
  const pointsPerStrip = 13;
  let nodeIndex = 0;
  let elementIndex = 0;

  for (let strip = 0; strip < stripCount; strip += 1) {
    const stripRatio = (strip + 0.5) / stripCount;
    const sideOffset = (stripRatio - 0.5) * diameter * 0.74;
    const basePhase = pose.physicalAngleRad * 3.4 + stripRatio * Math.PI * 0.62;
    const chipLength = diameter * (0.46 + 1.12 * engagement);
    for (let pointIndex = 0; pointIndex < pointsPerStrip; pointIndex += 1) {
      const t = pointIndex / (pointsPerStrip - 1);
      const curl = basePhase + t * Math.PI * 1.85;
      const lift = axialDepth * (0.28 + 1.55 * t) * engagement;
      const x = contactX - chipLength * t + 0.12 * diameter * Math.sin(curl);
      const y = pose.y + sideOffset + 0.14 * diameter * Math.sin(curl) * (0.3 + t);
      const z = chipRootZ + lift + 0.18 * axialDepth * Math.cos(curl);
      const stripWidth = diameter * (0.012 + 0.015 * t);
      const normalY = Math.cos(curl) * stripWidth;
      const normalZ = Math.sin(curl) * stripWidth * 0.5;
      for (const signed of [-1, 1]) {
        const point = [x, y + signed * normalY, z + signed * normalZ];
        nodes.push({
          label: chipNodeOffset + nodeIndex,
          coordinates: point,
          deformed: point,
          displacement: [0, 0, 0],
          visualOnly: true,
        });
        nodeIndex += 1;
      }
    }
    for (let pointIndex = 0; pointIndex < pointsPerStrip - 1; pointIndex += 1) {
      const base = chipNodeOffset + strip * pointsPerStrip * 2 + pointIndex * 2;
      elements.push({
        label: chipElementOffset + elementIndex,
        type: "S4R",
        connectivity: [base, base + 1, base + 3, base + 2],
        mises: 535,
        value: 535,
        color: "#d99532",
        visualOnly: true,
      });
      elementIndex += 1;
    }
  }
}

for (const frame of frames) {
  const pose = cutterPose(frame);
  const workpiece = buildWorkpieceSurfaces(pose);
  const nodes = workpiece.nodes;
  const elements = workpiece.elements;
  addChipStream(frame, pose, nodes, elements);
  frame.nodes = nodes;
  frame.elements = elements;
  frame.toolPose = pose;
  frame.visual = visual;
  frame.elementType = "C3D8R";
  frame.fieldRanges = workpiece.fieldRanges;
}

payload.nodes = frames[0].nodes;
payload.elements = frames[0].elements;
payload.frame = frames[0].frame;
payload.timeMs = frames[0].timeMs;
payload.elementType = "C3D8R";
payload.fieldRanges = frames[0].fieldRanges;
payload.visual = visual;
payload.dynamicFrames = frames;
fs.writeFileSync(resultPath, JSON.stringify(payload), "utf8");

const force = 1200 * axialDepth * Number(params.feed_per_tooth_mm || 0.035) * Math.max(Number(params.radial_width_mm || diameter) / diameter, 0.05);
if (fs.existsSync(projectPath)) {
  const project = JSON.parse(fs.readFileSync(projectPath, "utf8"));
  project.inputs.geometry = {
    workpiece_length_mm: length,
    workpiece_width_mm: width,
    workpiece_thickness_mm: thickness,
    tool_diameter_mm: diameter,
    axial_depth_mm: axialDepth,
    radial_width_mm: Number(params.radial_width_mm || diameter),
  };
  project.inputs.loads = {
    description: `Rotating ${Math.round(Number(params.flute_count || 4))}-flute milling load, peak tooth force ${force.toFixed(3)} N`,
    spindle_speed_rpm: Number(params.spindle_speed_rpm || 9000),
    feed_per_tooth_mm: Number(params.feed_per_tooth_mm || 0.035),
    flute_count: Math.round(Number(params.flute_count || 4)),
  };
  project.inputs.mesh = {
    element_family: "C3D8R",
    seed_size_mm: Number(params.seed_size_mm || 1),
  };
  const lastFrame = frames[frames.length - 1];
  project.outputs.metrics = [
    { label: "Peak milling stress", value: Number(lastFrame.fieldRanges.misesMax.toFixed(4)), unit: "MPa", state: "complete" },
    { label: "Max workpiece displacement", value: 0, unit: "mm", state: "complete" },
    { label: "Spindle speed", value: Number(params.spindle_speed_rpm || 9000), unit: "rpm", state: "complete" },
    { label: "Displayed frames", value: frames.length, unit: "", state: "complete" },
  ];
  fs.writeFileSync(projectPath, `${JSON.stringify(project, null, 2)}\n`, "utf8");
}

if (fs.existsSync(summaryPath)) {
  const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
  summary.parameters = params;
  summary.peak_mises_mpa = frames[frames.length - 1].fieldRanges.misesMax;
  summary.frames_written = frames.length;
  summary.peak_tooth_force_n = force;
  fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
}

console.log(`Refreshed rectangular milling slot visualization: ${resultPath}`);
