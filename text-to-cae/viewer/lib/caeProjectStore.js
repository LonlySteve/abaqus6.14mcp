const DEFAULT_CAE_DIRECTORY = "models/text-to-cae";
const CAE_DIRECTORY_QUERY_PARAM = "caeDir";

function readCaeDirectoryParam(directory) {
  if (directory) {
    return String(directory);
  }
  if (typeof window === "undefined") {
    return DEFAULT_CAE_DIRECTORY;
  }
  const params = new URLSearchParams(window.location.search);
  const value = String(params.get(CAE_DIRECTORY_QUERY_PARAM) || "").trim();
  return value || DEFAULT_CAE_DIRECTORY;
}

export async function fetchCaeProject(directory) {
  const dir = readCaeDirectoryParam(directory);
  const response = await fetch(`/__cae/project?dir=${encodeURIComponent(dir)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load CAE project ${dir}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function fetchCaeResultMesh(directory) {
  const dir = readCaeDirectoryParam(directory);
  const response = await fetch(`/__cae/result-mesh?dir=${encodeURIComponent(dir)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load CAE result mesh ${dir}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function fetchCaeResultSummary(directory) {
  const dir = readCaeDirectoryParam(directory);
  const response = await fetch(`/__cae/result-summary?dir=${encodeURIComponent(dir)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load CAE result summary ${dir}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function fetchCaeParameters(directory) {
  const dir = readCaeDirectoryParam(directory);
  const response = await fetch(`/__cae/parameters?dir=${encodeURIComponent(dir)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load CAE parameters ${dir}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function runCaeSimulation(directory, parameters) {
  const dir = readCaeDirectoryParam(directory);
  const response = await fetch("/__cae/run", {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({ dir, parameters }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.error || `Failed to run CAE simulation ${dir}: ${response.status} ${response.statusText}`);
  }
  return payload;
}

export { DEFAULT_CAE_DIRECTORY };
