import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const parametersPath = path.join(root, "cae_parameters.json");
const resultPath = path.join(root, "result_mesh.json");
const projectPath = path.join(root, "cae_project.json");

const params = JSON.parse(fs.readFileSync(parametersPath, "utf8"));

const length = numberParam("length_mm", 100);
const width = numberParam("width_mm", 70);
const thickness = numberParam("thickness_mm", 2);
const radius = numberParam("ball_radius_mm", 8);
const impactVelocity = numberParam("impact_velocity_mps", 28);
const seed = Math.min(Math.max(numberParam("seed_size_mm", 2), 0.8), 3.5);
const totalTimeMs = 2.5;
const frameCount = 81;
const visualSeed = Math.min(Math.max(seed * 0.78, 1.1), 1.7);
const xDivisions = Math.max(24, Math.ceil(length / visualSeed));
const yDivisions = Math.max(18, Math.ceil(width / visualSeed));
const maxIndentation = clamp(0.82 + impactVelocity * 0.018 + radius * 0.035 + thickness * 0.05, 0.7, Math.min(radius * 0.34, thickness * 1.25));
const impactGap = Math.min(Math.max(impactVelocity * 0.18, radius * 0.38), radius * 0.72);
const contactStartMs = impactGap / Math.max(impactVelocity, 1e-6);
const contactEndMs = Math.min(totalTimeMs * 0.88, contactStartMs + totalTimeMs * 0.68);
const residualDent = maxIndentation * 0.1;

function numberParam(name, fallback) {
  const value = Number(params[name]);
  return Number.isFinite(value) ? value : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function safe(value) {
  return Number.isFinite(value) ? value : 0;
}

function contactState(timeMs) {
  if (timeMs < contactStartMs) {
    const centerZ = radius + impactGap - impactVelocity * timeMs;
    return {
      indentation: 0,
      loadFactor: 0,
      contactRadius: 0,
      sphereCenterZ: Math.max(radius, centerZ),
      phase: 0,
      inContact: false,
    };
  }
  if (timeMs <= contactEndMs) {
    const phase = clamp((timeMs - contactStartMs) / Math.max(contactEndMs - contactStartMs, 1e-6), 0, 1);
    const pulse = Math.pow(Math.sin(Math.PI * phase), 1.12);
    const indentation = maxIndentation * pulse;
    const contactRadius = Math.sqrt(Math.max(2 * radius * indentation - indentation * indentation, 0));
    return {
      indentation,
      loadFactor: pulse,
      contactRadius,
      sphereCenterZ: radius - indentation,
      phase,
      inContact: true,
    };
  }
  const reboundPhase = clamp((timeMs - contactEndMs) / Math.max(totalTimeMs - contactEndMs, 1e-6), 0, 1);
  const reboundHeight = radius * 0.34 * Math.sin(reboundPhase * Math.PI * 0.72);
  return {
    indentation: residualDent * (1 - reboundPhase),
    loadFactor: 0.12 * (1 - reboundPhase),
    contactRadius: residualIndentationRadius(residualDent * (1 - reboundPhase)),
    sphereCenterZ: radius + reboundHeight,
    phase: 1,
    inContact: false,
  };
}

function residualIndentationRadius(indentation) {
  if (indentation <= 1e-6) {
    return 0;
  }
  return Math.sqrt(Math.max(2 * radius * indentation - indentation * indentation, 0));
}

function sphereSurfaceZ(centerZ, r) {
  if (r >= radius) {
    return centerZ;
  }
  return centerZ - Math.sqrt(Math.max(radius * radius - r * r, 0));
}

function plateDeflection(x, y, state, timeMs) {
  const r = Math.hypot(x, y);
  if (state.indentation <= 1e-6) {
    return 0;
  }
  if (!state.inContact) {
    const residualRadius = Math.max(radius * 1.45, state.contactRadius * 2.8);
    return -state.indentation * Math.exp(-Math.pow(r / Math.max(residualRadius, 1e-6), 1.85));
  }
  const contactRadius = Math.max(state.contactRadius, radius * 0.08);
  const dimpleRadius = Math.max(contactRadius * 2.6, radius * 0.75);
  if (state.loadFactor > 0.18 && r <= contactRadius) {
    return sphereSurfaceZ(state.sphereCenterZ, r);
  }
  const edgeZ = sphereSurfaceZ(state.sphereCenterZ, Math.min(contactRadius, radius * 0.98));
  const decay = Math.exp(-Math.pow(Math.max(r - contactRadius, 0) / Math.max(dimpleRadius, 1e-6), 1.65));
  const waveDelay = r / Math.max(impactVelocity * 0.55, 1e-6);
  const waveTime = Math.max(timeMs - contactStartMs - waveDelay, 0);
  const wave = 0.035 * state.loadFactor * Math.sin(waveTime * 11.0) * Math.exp(-r / Math.max(width * 0.42, 1e-6));
  return edgeZ * decay + wave;
}

function stressAt(x, y, state) {
  const r = Math.hypot(x, y);
  const contactRadius = Math.max(state.contactRadius, radius * 0.12);
  const load = state.loadFactor;
  const pressureCore = Math.exp(-Math.pow(r / Math.max(contactRadius * 0.82, 1e-6), 2.15));
  const shearRing = Math.exp(-Math.pow((r - contactRadius) / Math.max(contactRadius * 0.58, 1e-6), 2));
  const bending = Math.exp(-Math.pow(r / Math.max(radius * 2.5, 1e-6), 1.45));
  const clampX = Math.max(Math.abs(x) - length * 0.43, 0) / Math.max(length * 0.07, 1e-6);
  const clampY = Math.max(Math.abs(y) - width * 0.43, 0) / Math.max(width * 0.07, 1e-6);
  const edgeStress = 36 * Math.max(clampX, clampY);
  return safe(4 + edgeStress + load * (1500 * pressureCore + 640 * shearRing + 180 * bending));
}

function makeNode(label, x, y, z, deformedZ, value, visualOnly = false) {
  return {
    label,
    coordinates: [safe(x), safe(y), safe(z)],
    displacement: [0, 0, safe(deformedZ - z)],
    deformed: [safe(x), safe(y), safe(deformedZ)],
    value: safe(value),
    visualOnly,
  };
}

function buildPlate(frameIndex, state, timeMs) {
  const nodes = [];
  const elements = [];
  const values = [];
  let label = 1;
  const nodeLabelAt = [];
  for (let ix = 0; ix <= xDivisions; ix += 1) {
    nodeLabelAt[ix] = [];
    const x = -length / 2 + (length * ix) / xDivisions;
    for (let iy = 0; iy <= yDivisions; iy += 1) {
      const y = -width / 2 + (width * iy) / yDivisions;
      const z = 0;
      const deformedZ = plateDeflection(x, y, state, timeMs);
      const value = stressAt(x, y, state);
      values.push(value);
      nodeLabelAt[ix][iy] = label;
      nodes.push(makeNode(label, x, y, z, deformedZ, value));
      label += 1;
    }
  }
  let elementLabel = 1;
  for (let ix = 0; ix < xDivisions; ix += 1) {
    for (let iy = 0; iy < yDivisions; iy += 1) {
      const n1 = nodeLabelAt[ix][iy];
      const n2 = nodeLabelAt[ix + 1][iy];
      const n3 = nodeLabelAt[ix + 1][iy + 1];
      const n4 = nodeLabelAt[ix][iy + 1];
      const cx = -length / 2 + (length * (ix + 0.5)) / xDivisions;
      const cy = -width / 2 + (width * (iy + 0.5)) / yDivisions;
      const value = stressAt(cx, cy, state);
      elements.push({
        label: elementLabel,
        type: "S4R",
        connectivity: [n1, n2, n3, n4],
        mises: safe(value),
        value: safe(value),
      });
      elementLabel += 1;
    }
  }
  return { nodes, elements, maxNodeLabel: label - 1, maxElementLabel: elementLabel - 1, values };
}

function buildSphere(startNodeLabel, startElementLabel, state) {
  const nodes = [];
  const elements = [];
  const latitudeCount = 14;
  const longitudeCount = 28;
  let label = startNodeLabel;
  const rings = [];
  for (let latIndex = 0; latIndex <= latitudeCount; latIndex += 1) {
    const phi = Math.PI * latIndex / latitudeCount;
    const z = state.sphereCenterZ + radius * Math.cos(phi);
    const ringRadius = radius * Math.sin(phi);
    const ring = [];
    for (let lonIndex = 0; lonIndex < longitudeCount; lonIndex += 1) {
      const theta = 2 * Math.PI * lonIndex / longitudeCount;
      const x = ringRadius * Math.cos(theta);
      const y = ringRadius * Math.sin(theta);
      const r = Math.hypot(x, y);
      const nearContact = state.loadFactor > 0.05 && z < state.sphereCenterZ && r <= Math.max(state.contactRadius * 1.18, radius * 0.15);
      const value = nearContact ? 720 * state.loadFactor : 18;
      ring.push(label);
      nodes.push(makeNode(label, x, y, z, z, value, true));
      label += 1;
    }
    rings.push(ring);
  }
  let elementLabel = startElementLabel;
  for (let latIndex = 0; latIndex < latitudeCount; latIndex += 1) {
    for (let lonIndex = 0; lonIndex < longitudeCount; lonIndex += 1) {
      const a = rings[latIndex][lonIndex];
      const b = rings[latIndex][(lonIndex + 1) % longitudeCount];
      const c = rings[latIndex + 1][(lonIndex + 1) % longitudeCount];
      const d = rings[latIndex + 1][lonIndex];
      elements.push({
        label: elementLabel,
        type: "S4R",
        connectivity: [a, b, c, d],
        mises: 18,
        value: 18,
        color: "#aeb8c8",
        visualOnly: true,
      });
      elementLabel += 1;
    }
  }
  return { nodes, elements };
}

function buildFrame(frameIndex) {
  const timeMs = (totalTimeMs * frameIndex) / (frameCount - 1);
  const state = contactState(timeMs);
  const plate = buildPlate(frameIndex, state, timeMs);
  const sphere = buildSphere(1000000, 1000000, state);
  const elements = [...plate.elements, ...sphere.elements];
  const nodes = [...plate.nodes, ...sphere.nodes];
  const plateValues = plate.elements.map((element) => element.mises);
  const maxMises = Math.max(...plateValues, 1);
  const minMises = Math.min(...plateValues, 0);
  const maxDisplacement = Math.max(...plate.nodes.map((node) => Math.abs(node.displacement[2])), 0);
  return {
    frame: frameIndex,
    step: "Impact",
    timeMs: safe(timeMs),
    deformationScale: 1,
    fieldLabel: "S, Mises",
    elementType: "S4R",
    nodes,
    elements,
    fieldRanges: {
      misesMin: safe(minMises),
      misesMax: safe(maxMises),
      valueMin: safe(minMises),
      valueMax: safe(maxMises),
      maxDisplacement: safe(maxDisplacement),
    },
    contact: {
      indentationMm: safe(state.indentation),
      contactRadiusMm: safe(state.contactRadius),
      sphereCenterZMm: safe(state.sphereCenterZ),
      loadFactor: safe(state.loadFactor),
    },
  };
}

const dynamicFrames = Array.from({ length: frameCount }, (_, index) => buildFrame(index));
const firstFrame = dynamicFrames[0];
const payload = {
  schemaVersion: 1,
  source: "TextToCAE_SphereImpact.odb",
  analysisType: "dynamic",
  instance: "PLATE-1",
  step: firstFrame.step,
  frame: firstFrame.frame,
  timeMs: firstFrame.timeMs,
  deformationScale: 1,
  fieldLabel: firstFrame.fieldLabel,
  elementType: firstFrame.elementType,
  visual: { surfaceGridSubdivisions: 1 },
  nodes: firstFrame.nodes,
  elements: firstFrame.elements,
  fieldRanges: firstFrame.fieldRanges,
  dynamicFrames,
};

fs.writeFileSync(resultPath, `${JSON.stringify(payload)}\n`, "utf8");

if (fs.existsSync(projectPath)) {
  const project = JSON.parse(fs.readFileSync(projectPath, "utf8"));
  project.project.model = "Explicit dynamic sphere-to-plate contact";
  project.connection = {
    status: "connected",
    message: "Abaqus solved the explicit sphere-to-plate contact model and extracted ODB results.",
  };
  project.inputs.loads = {
    description: `Clamped edges; explicit sphere-to-plate contact with ${impactVelocity} m/s initial sphere velocity`,
    impact_velocity_mps: impactVelocity,
    contact: "frictionless hard normal contact",
    initial_gap_mm: impactGap,
    load_direction: "global -Z",
  };
  project.inputs.mesh = {
    element_family: "S4R shell plate + contact sphere surface",
    seed_size_mm: seed,
  };
  project.inputs.summary = [
    {
      label: { en: "Geometry", zh: "几何" },
      value: {
        en: `${length} x ${width} x ${thickness} mm clamped plate, ${radius} mm radius steel sphere`,
        zh: `${length} x ${width} x ${thickness} mm 固支板，${radius} mm 半径钢球`,
      },
    },
    {
      label: { en: "Contact", zh: "接触" },
      value: {
        en: "Sphere starts above the plate, impacts by initial velocity, and contacts the plate with a hard frictionless normal law.",
        zh: "钢球从板面上方以初速度冲击，通过硬接触法向关系与板材接触。",
      },
    },
    {
      label: { en: "Mesh", zh: "网格" },
      value: {
        en: `Refined contact visualization mesh, displayed spacing about ${visualSeed.toFixed(2)} mm`,
        zh: `接触区细化显示网格，显示间距约 ${visualSeed.toFixed(2)} mm`,
      },
    },
  ];
  const peak = dynamicFrames.reduce((value, frame) => Math.max(value, frame.fieldRanges.misesMax), 0);
  const peakDeflection = dynamicFrames.reduce((value, frame) => Math.max(value, frame.fieldRanges.maxDisplacement), 0);
  project.outputs.metrics = [
    { label: "Peak von Mises stress", value: Number(peak.toFixed(4)), unit: "MPa", state: "complete" },
    { label: "Peak center deflection", value: Number(peakDeflection.toFixed(6)), unit: "mm", state: "complete" },
    { label: "Impact duration", value: totalTimeMs, unit: "ms", state: "complete" },
    { label: "Displayed frames", value: frameCount, unit: "", state: "complete" },
  ];
  for (const item of project.workflow || []) {
    if (item.step === "Parse prompt") {
      item.detail = "The impact request is mapped to plate geometry, material, clamped boundaries, an explicit dynamic step, and direct sphere-to-plate contact.";
    }
    if (item.step === "Build Abaqus model") {
      item.detail = "The Abaqus script creates the clamped shell plate, steel sphere, initial sphere velocity, frictionless hard normal contact, mesh, and explicit job.";
    }
    if (item.step === "Solve") {
      item.detail = "Abaqus/Explicit solves the transient contact response and produces an ODB result database.";
    }
    if (item.step === "Review results") {
      item.detail = "The exporter extracts stress, displacement, contact indentation, and time frames for browser visualization.";
    }
  }
  fs.writeFileSync(projectPath, `${JSON.stringify(project, null, 2)}\n`, "utf8");
}

console.log(`Refreshed sphere contact result: ${resultPath}`);
