#!/usr/bin/env python3
"""Dependency-free BM25/TF-IDF search over the local Abaqus Help JSONL index."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


DEFAULT_INDEX = Path(__file__).resolve().parents[1] / ".local" / "abaqus-help-index" / "index.jsonl"

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "you", "your", "abaqus",
    "analysis", "using", "will", "can", "all", "has", "have", "was", "were", "been",
    "section", "more", "information", "see", "use", "used", "define", "defined",
}

QUERY_EXPANSIONS = {
    "fpc": ["flexible", "printed", "circuit", "film", "shell", "composite", "bending"],
    "多芯片": ["multi", "chip", "component", "package", "assembly"],
    "芯片": ["chip", "die", "package", "component", "silicon"],
    "柔性": ["flexible", "film", "shell", "membrane"],
    "柔性板": ["flexible", "plate", "shell", "bending"],
    "板": ["plate", "shell"],
    "弯曲": ["bending", "bend", "curvature", "static", "riks"],
    "应力": ["stress", "mises", "principal"],
    "静力": ["static", "general", "step"],
    "接触": ["contact", "interaction", "surface"],
    "绑定": ["tie", "constraint"],
    "约束": ["constraint", "boundary", "tie"],
    "复合": ["composite", "layered", "shell", "laminate"],
    "壳": ["shell", "s4r", "continuum"],
    "材料": ["material", "elastic", "plastic"],
    "网格": ["mesh", "element", "seed"],
}


def tokenize(text: str) -> List[str]:
    tokens = [m.group(0).lower() for m in re.finditer(r"[a-zA-Z][a-zA-Z0-9_+\-]{1,}", text)]
    tokens += [m.group(0).lower() for m in re.finditer(r"\d+(?:\.\d+)?", text)]
    return [token for token in tokens if token not in STOPWORDS]


def expand_query(query: str) -> str:
    expanded = [query]
    query_lower = query.lower()
    for key, values in QUERY_EXPANSIONS.items():
        if key.lower() in query_lower:
            expanded.extend(values)
    return " ".join(expanded)


def record_search_text(record: dict) -> str:
    keywords = record.get("keywords") or []
    if isinstance(keywords, list):
        keywords_text = " ".join(str(item) for item in keywords)
    else:
        keywords_text = str(keywords)
    # Repeat high-signal fields to approximate field weighting without a separate index format.
    title = str(record.get("title") or "")
    path = str(record.get("relativePath") or record.get("path") or "")
    sample = str(record.get("textSample") or "")
    kind = str(record.get("kind") or "")
    return " ".join([title] * 4 + [path] * 2 + [keywords_text] * 3 + [kind, sample])


def load_records(index_path: Path) -> List[dict]:
    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    records: List[dict] = []
    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def build_corpus(records: Sequence[dict]) -> tuple[List[Counter], Dict[str, int], float]:
    term_counts: List[Counter] = []
    document_frequency: Dict[str, int] = {}
    total_length = 0
    for record in records:
        counts = Counter(tokenize(record_search_text(record)))
        term_counts.append(counts)
        total_length += sum(counts.values())
        for term in counts:
            document_frequency[term] = document_frequency.get(term, 0) + 1
    avgdl = float(total_length) / float(len(records)) if records else 0.0
    return term_counts, document_frequency, avgdl


def bm25_score(query_terms: Sequence[str], counts: Counter, df: Dict[str, int], total_docs: int, avgdl: float) -> float:
    if not counts or avgdl <= 0:
        return 0.0
    k1 = 1.5
    b = 0.75
    doc_len = float(sum(counts.values()))
    score = 0.0
    for term in query_terms:
        freq = counts.get(term, 0)
        if freq <= 0:
            continue
        term_df = df.get(term, 0)
        idf = math.log(1.0 + (total_docs - term_df + 0.5) / (term_df + 0.5))
        denom = freq + k1 * (1.0 - b + b * doc_len / avgdl)
        score += idf * (freq * (k1 + 1.0)) / denom
    return score


def tfidf_score(query_terms: Sequence[str], counts: Counter, df: Dict[str, int], total_docs: int) -> float:
    if not counts:
        return 0.0
    doc_len = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    query_counts = Counter(query_terms)
    query_len = math.sqrt(sum(value * value for value in query_counts.values())) or 1.0
    score = 0.0
    for term, qtf in query_counts.items():
        freq = counts.get(term, 0)
        if freq <= 0:
            continue
        idf = math.log((1.0 + total_docs) / (1.0 + df.get(term, 0))) + 1.0
        score += (freq * idf / doc_len) * (qtf * idf / query_len)
    return score


def excerpt(text: str, terms: Sequence[str], limit: int = 420) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    lower = clean.lower()
    positions = [lower.find(term) for term in terms if term and lower.find(term) >= 0]
    start = max(0, min(positions) - 90) if positions else 0
    value = clean[start:start + limit]
    if start > 0:
        value = "..." + value
    if start + limit < len(clean):
        value += "..."
    return value


def search(index_path: Path, query: str, limit: int = 5, method: str = "bm25") -> List[dict]:
    records = load_records(index_path)
    if not records:
        return []
    expanded_query = expand_query(query)
    query_terms = tokenize(expanded_query)
    if not query_terms:
        return []
    term_counts, df, avgdl = build_corpus(records)
    total_docs = len(records)

    scored = []
    for record, counts in zip(records, term_counts):
        bm25 = bm25_score(query_terms, counts, df, total_docs, avgdl)
        tfidf = tfidf_score(query_terms, counts, df, total_docs)
        if method == "tfidf":
            score = tfidf
        elif method == "hybrid":
            score = bm25 + 2.0 * tfidf
        else:
            score = bm25
        if score <= 0:
            continue
        sample = str(record.get("textSample") or "")
        result = {
            "score": round(score, 6),
            "method": method,
            "kind": record.get("kind"),
            "title": record.get("title"),
            "relativePath": record.get("relativePath"),
            "path": record.get("path"),
            "keywords": record.get("keywords") or [],
            "excerpt": excerpt(sample, query_terms),
        }
        scored.append(result)
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Search local Abaqus Help index with BM25/TF-IDF.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="Path to index.jsonl")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--method", choices=["bm25", "tfidf", "hybrid"], default="bm25")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args(argv)

    results = search(Path(args.index), args.query, args.limit, args.method)
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0
    if not results:
        print("No matches.")
        return 0
    for idx, item in enumerate(results, 1):
        print(f"[{idx}] score={item['score']} method={item['method']} kind={item.get('kind')}")
        print(f"Title: {item.get('title')}")
        print(f"Path:  {item.get('path')}")
        keywords = item.get("keywords") or []
        if keywords:
            print("Keys:  " + ", ".join(str(value) for value in keywords[:10]))
        print(f"Text:  {item.get('excerpt')}")
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
