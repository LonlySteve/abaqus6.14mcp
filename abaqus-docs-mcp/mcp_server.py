#!/usr/bin/env python3
"""MCP server for local Abaqus Help search.

The server reads the user's local `.local/abaqus-help-index/index.jsonl`.
It does not ship or transmit Abaqus Help content.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP


SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from abaqus_docs_embed import DEFAULT_EMBEDDINGS, search_embeddings  # noqa: E402
from abaqus_docs_search import DEFAULT_INDEX, load_records, search  # noqa: E402


INDEX_PATH = Path(os.environ.get("ABAQUS_HELP_INDEX", str(DEFAULT_INDEX)))
EMBEDDINGS_PATH = Path(os.environ.get("ABAQUS_HELP_EMBEDDINGS", str(DEFAULT_EMBEDDINGS)))
EMBED_MODEL = os.environ.get("ABAQUS_HELP_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
mcp = FastMCP("abaqus-docs-mcp")


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _load_records():
    return load_records(INDEX_PATH)


@mcp.tool()
def search_abaqus_help(query: str, limit: int = 5, method: str = "bm25") -> str:
    """Search local Abaqus Help/examples with BM25, TF-IDF, hybrid, or embedding scoring."""
    if method in ("embedding", "semantic"):
        limit = max(1, min(int(limit), 20))
        try:
            return _json(search_embeddings(
                EMBEDDINGS_PATH,
                query,
                model_name=EMBED_MODEL,
                limit=limit,
                local_files_only=True,
            ))
        except Exception as exc:
            return _json({
                "error": str(exc),
                "hint": "Run scripts/setup-abaqus-help-embeddings.ps1 and build embeddings, then start MCP with that venv Python.",
            })
    if method not in ("bm25", "tfidf", "hybrid"):
        method = "bm25"
    limit = max(1, min(int(limit), 20))
    return _json(search(INDEX_PATH, query, limit=limit, method=method))


@mcp.tool()
def get_abaqus_doc_entry(path_or_id: str) -> str:
    """Return one indexed Abaqus Help/example entry by id, path, relative path, or title."""
    needle = str(path_or_id).strip().lower()
    if not needle:
        return _json({"error": "path_or_id is required"})
    for record in _load_records():
        candidates = [
            str(record.get("id") or ""),
            str(record.get("path") or ""),
            str(record.get("relativePath") or ""),
            str(record.get("title") or ""),
        ]
        if any(value.lower() == needle for value in candidates):
            return _json(record)
    matches = []
    for record in _load_records():
        haystack = " ".join([
            str(record.get("path") or ""),
            str(record.get("relativePath") or ""),
            str(record.get("title") or ""),
        ]).lower()
        if needle in haystack:
            matches.append(record)
        if len(matches) >= 5:
            break
    if matches:
        return _json({"matches": matches})
    return _json({"error": "No matching indexed entry", "query": path_or_id})


@mcp.tool()
def suggest_abaqus_pattern(description: str, limit: int = 5, method: str = "hybrid") -> str:
    """Suggest Abaqus modeling patterns from local docs/examples for a simulation description."""
    description_lower = str(description).lower()
    hints = []
    if any(term in description_lower for term in ("bend", "bending", "curvature", "弯曲")):
        hints.append("Consider static general step, shell/solid choice by thickness, prescribed displacement/rotation or curvature boundary conditions.")
    if any(term in description_lower for term in ("fpc", "flexible", "柔性", "composite", "layer")):
        hints.append("Check shell/composite/layered modeling patterns and validate tie constraints between components and substrate.")
    if any(term in description_lower for term in ("chip", "component", "package", "芯片", "阻容", "电容", "电阻", "电感")):
        hints.append("Use simplified component solids for early screening; tie or cohesive/contact interfaces depending on fidelity.")
    if any(term in description_lower for term in ("contact", "tie", "cohesive", "接触", "绑定", "约束")):
        hints.append("Search tie constraints and surface contact definitions before choosing interaction behavior.")
    if any(term in description_lower for term in ("thermal", "temperature", "cte", "热")):
        hints.append("Include thermal expansion and sequential/fully coupled thermal-stress only when temperature loading matters.")
    if not hints:
        hints.append("Start with a small linear static smoke test, then increase geometric/material fidelity.")

    limited = max(1, min(int(limit), 10))
    reference_query = " ".join([description] + hints)
    if method in ("embedding", "semantic"):
        try:
            results = search_embeddings(
                EMBEDDINGS_PATH,
                reference_query,
                model_name=EMBED_MODEL,
                limit=limited,
                local_files_only=True,
            )
        except Exception as exc:
            results = [{
                "error": str(exc),
                "hint": "Embedding search unavailable; falling back to hybrid lexical search.",
            }]
            results.extend(search(INDEX_PATH, reference_query, limit=limited, method="hybrid"))
    else:
        results = search(INDEX_PATH, reference_query, limit=limited, method="hybrid")
    return _json({
        "description": description,
        "method": method,
        "patternHints": hints,
        "localReferences": results,
    })


@mcp.resource("abaqus-docs://status")
def status() -> str:
    """Return local Abaqus docs index status."""
    exists = INDEX_PATH.exists()
    count = 0
    if exists:
        with INDEX_PATH.open("r", encoding="utf-8") as handle:
            count = sum(1 for line in handle if line.strip())
    return _json({
        "indexPath": str(INDEX_PATH),
        "exists": exists,
        "entries": count,
        "embeddingsPath": str(EMBEDDINGS_PATH),
        "embeddingsExists": EMBEDDINGS_PATH.exists(),
        "embeddingModel": EMBED_MODEL,
    })


if __name__ == "__main__":
    mcp.run()
