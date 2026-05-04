#!/usr/bin/env python3
"""Optional local embedding search for the Abaqus Help JSONL index.

This script intentionally does not install packages. By default it only loads
locally cached models. Use --allow-download only when you explicitly want the
model library to fetch model files; Abaqus Help content is still embedded
locally and is not sent to a hosted LLM service by this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Sequence


DEFAULT_INDEX = Path(__file__).resolve().parents[1] / ".local" / "abaqus-help-index" / "index.jsonl"
DEFAULT_EMBEDDINGS = Path(__file__).resolve().parents[1] / ".local" / "abaqus-help-index" / "embeddings.jsonl"
_MODEL_CACHE = {}


def load_sentence_transformer(model_name: str, local_files_only: bool):
    cache_key = (model_name, local_files_only)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Install it explicitly when you are ready: "
            "python -m pip install sentence-transformers"
        ) from exc

    kwargs = {}
    if local_files_only:
        kwargs["local_files_only"] = True
    try:
        model = SentenceTransformer(model_name, **kwargs)
    except TypeError:
        if local_files_only:
            raise RuntimeError(
                "Installed sentence-transformers does not support local_files_only. "
                "Use a local model path to avoid network access."
            )
        model = SentenceTransformer(model_name)
    _MODEL_CACHE[cache_key] = model
    return model


def load_records(index_path: Path) -> List[dict]:
    records: List[dict] = []
    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def embedding_text(record: dict) -> str:
    keywords = record.get("keywords") or []
    if isinstance(keywords, list):
        keywords_text = " ".join(str(item) for item in keywords)
    else:
        keywords_text = str(keywords)
    return "\n".join([
        str(record.get("title") or ""),
        str(record.get("kind") or ""),
        str(record.get("relativePath") or record.get("path") or ""),
        keywords_text,
        str(record.get("textSample") or ""),
    ])


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for av, bv in zip(a, b):
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def cmd_build(args: argparse.Namespace) -> int:
    index_path = Path(args.index)
    out_path = Path(args.output)
    records = load_records(index_path)
    model = load_sentence_transformer(args.model, args.local_files_only)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        batch_size = max(1, args.batch_size)
        for start in range(0, len(records), batch_size):
            batch = records[start:start + batch_size]
            texts = [embedding_text(record) for record in batch]
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for record, vector in zip(batch, vectors):
                payload = {
                    "id": record.get("id"),
                    "title": record.get("title"),
                    "kind": record.get("kind"),
                    "path": record.get("path"),
                    "relativePath": record.get("relativePath"),
                    "keywords": record.get("keywords") or [],
                    "textSample": record.get("textSample"),
                    "model": args.model,
                    "embedding": [float(value) for value in vector],
                }
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"Wrote embeddings: {out_path}")
    print(f"Records: {len(records)}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    results = search_embeddings(
        Path(args.embeddings),
        args.query,
        model_name=args.model,
        limit=args.limit,
        local_files_only=args.local_files_only,
    )
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for idx, item in enumerate(results, 1):
            print(f"[{idx}] score={item['score']} method=embedding kind={item.get('kind')}")
            print(f"Title: {item.get('title')}")
            print(f"Path:  {item.get('path')}")
            keywords = item.get("keywords") or []
            if keywords:
                print("Keys:  " + ", ".join(str(value) for value in keywords[:10]))
            print(f"Text:  {item.get('excerpt')}")
            print("")
    return 0


def search_embeddings(
    embeddings_path: Path,
    query: str,
    model_name: str = "BAAI/bge-small-en-v1.5",
    limit: int = 5,
    local_files_only: bool = True,
) -> List[dict]:
    if not embeddings_path.exists():
        raise FileNotFoundError(f"Embeddings not found: {embeddings_path}. Run build first.")
    model = load_sentence_transformer(model_name, local_files_only)
    query_vector = [float(value) for value in model.encode(query, normalize_embeddings=True)]

    scored = []
    with embeddings_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            score = cosine_similarity(query_vector, record.get("embedding") or [])
            if score > 0:
                scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)

    results = []
    for score, record in scored[: max(1, limit)]:
        sample = str(record.get("textSample") or "")
        if len(sample) > 420:
            sample = sample[:420] + "..."
        results.append({
            "score": round(score, 6),
            "method": "embedding",
            "model": record.get("model"),
            "kind": record.get("kind"),
            "title": record.get("title"),
            "relativePath": record.get("relativePath"),
            "path": record.get("path"),
            "keywords": record.get("keywords") or [],
            "excerpt": sample,
        })
    return results


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Build/search optional local embeddings for Abaqus Help.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--index", default=str(DEFAULT_INDEX))
    build.add_argument("--output", default=str(DEFAULT_EMBEDDINGS))
    build.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    build.add_argument("--batch-size", type=int, default=32)
    build.add_argument("--local-files-only", dest="local_files_only", action="store_true", default=True)
    build.add_argument("--allow-download", dest="local_files_only", action="store_false")
    build.set_defaults(func=cmd_build)

    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--embeddings", default=str(DEFAULT_EMBEDDINGS))
    search.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--json", action="store_true")
    search.add_argument("--local-files-only", dest="local_files_only", action="store_true", default=True)
    search.add_argument("--allow-download", dest="local_files_only", action="store_false")
    search.set_defaults(func=cmd_search)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
