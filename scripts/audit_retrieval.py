#!/usr/bin/env python3
"""Inspect a complete dev retrieval cache without loading models or answers.

This is a diagnostic, not an answer-quality evaluation or a fresh k sweep.
Use check_artifacts.py separately for the full schema/provenance acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import html
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.retrieve import (StructuralError, load_config, load_manifest,
                              load_questions, manifest_id_union, read_jsonl,
                              row_is_sound, select_expected)
from src.contracts.m3 import config_sha256, file_sha256
from src.retrieval.text_retrieval import RetrievalConfig


def normalize(text):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", text)).split())


def inspect(manifest_path, questions_path, evidence_path, config_path):
    manifest, manifest_hash = load_manifest(manifest_path)
    subset, queries = load_questions(questions_path, manifest_hash, manifest_id_union(manifest))
    if subset != "dev":
        raise StructuralError("Parameter diagnostics must use dev, never eval")
    expected, _ = select_expected(manifest, "dev", None)
    if set(queries) != set(expected):
        raise StructuralError("questions must cover the complete dev ID set")
    config = load_config(config_path)
    parsed = RetrievalConfig.from_dict(config)
    config_hash = config_sha256(config)
    rows = read_jsonl(evidence_path)
    indexed = {}
    for row in rows:
        ident = row.get("interaction_id")
        if ident in indexed or ident not in queries or not row_is_sound(row, queries):
            raise StructuralError("Invalid, duplicate or unexpected evidence row")
        if (row["subset"] != "dev" or row["dataset_manifest_sha256"] != manifest_hash
                or row["retrieval_config_sha256"] != config_hash
                or row["index_revision"] != parsed.index_revision
                or row["encoder_revision"] != parsed.encoder_revision):
            raise StructuralError("Evidence config, dataset or revision mismatch")
        if len(row["hits"]) > parsed.top_k:
            raise StructuralError("Evidence has more hits than configured top_k")
        indexed[ident] = row
    if set(indexed) != set(expected) or len({r["run_id"] for r in rows}) != 1:
        raise StructuralError("Evidence must cover dev with one consistent run_id")
    rows = [indexed[ident] for ident in expected]
    hits = [hit for row in rows for hit in row["hits"]]
    score_values = [h["score"] for h in hits if h["score"] is not None]
    duplicate_ids = []
    duplicate_text_ids = []
    title_only_ids = []
    for row in rows:
        bases = [h["doc_id"].split("_chunk")[0] for h in row["hits"]]
        texts = [normalize(h["text"]) for h in row["hits"]]
        if len(bases) != len(set(bases)):
            duplicate_ids.append(row["interaction_id"])
        if len(texts) != len(set(texts)):
            duplicate_text_ids.append(row["interaction_id"])
        if any(normalize(h["text"]) == normalize(h["title"]) for h in row["hits"]):
            title_only_ids.append(row["interaction_id"])
    sample_ids = expected[::5]
    nonempty = [row for row in rows if row["hits"] and row["hits"][0]["score"] is not None]
    if nonempty:
        sample_ids.append(min(nonempty, key=lambda r: r["hits"][0]["score"])["interaction_id"])
    sample_ids = list(dict.fromkeys(sample_ids))
    samples = [{"interaction_id": ident, "query": queries[ident],
                "selection": "manifest_every_fifth_plus_lowest_top1_score",
                "review_status": "unreviewed", "hits": indexed[ident]["hits"][:2]}
               for ident in sample_ids]
    counts = Counter(r["retrieval_status"] for r in rows)
    report = {
        "record_type": "dev_retrieval_diagnostic", "schema_version": "m3.v1",
        "subset": "dev", "N_expected": len(expected),
        "dataset_manifest_sha256": manifest_hash,
        "retrieval_config_sha256": config_hash, "top_k": parsed.top_k,
        "fetch_k": "not_implemented", "run_id": rows[0]["run_id"],
        "input_files_sha256": {"manifest": manifest_hash,
            "questions": file_sha256(questions_path), "evidence": file_sha256(evidence_path),
            "config_raw_bytes": file_sha256(config_path)},
        "statuses": {key: counts[key] for key in ("ok", "empty", "error")},
        "total_hits": len(hits),
        "hits_per_question": dict(sorted(Counter(len(r["hits"]) for r in rows).items())),
        "mean_hits": statistics.mean(len(r["hits"]) for r in rows),
        "fewer_than_top_k": sum(len(r["hits"]) < parsed.top_k for r in rows),
        "title_only_hits": sum(normalize(h["text"]) == normalize(h["title"]) for h in hits),
        "title_only_question_ids": title_only_ids,
        "duplicate_page_question_ids": duplicate_ids,
        "duplicate_text_question_ids": duplicate_text_ids,
        "score_kinds": dict(Counter(h["score_kind"] for h in hits)),
        "scores": {"min": min(score_values), "median": statistics.median(score_values),
                   "max": max(score_values)} if score_values else None,
        "total_evidence_characters": sum(len(h["text"]) for h in hits),
        "cached_prefix_hit_counts": {str(k): sum(min(k, len(r["hits"])) for r in rows)
                                      for k in (1, 3, 5)},
        "limitations": ["Cached prefixes are evidence-budget candidates, not fresh Chroma k runs.",
                         "Cosine scores and hit counts do not prove answer quality or Recall@k.",
                         "No answers, image inputs, online source fetch, model or judge was used.",
                         "Source inspection samples require a separate recorded manual review."],
    }
    return report, samples


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "questions", "evidence", "config", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report, samples = inspect(args.manifest, args.questions, args.evidence, args.config)
        destinations = [(args.output_dir / "diagnostic.json", report),
                        (args.output_dir / "source_review_samples.json", samples)]
        for path, value in destinations:
            text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            if path.exists() and path.read_text(encoding="utf-8") != text:
                raise StructuralError("Output exists with different content; use a new output directory")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for path, value in destinations:
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                            encoding="utf-8", newline="\n")
        print(json.dumps({"status": "diagnostic_written", "N": report["N_expected"],
                          "statuses": report["statuses"], "total_hits": report["total_hits"]}))
        return 2 if report["statuses"]["error"] else 0
    except (ValueError, OSError, StructuralError, KeyError, TypeError) as exc:
        print(f"Diagnostic failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
