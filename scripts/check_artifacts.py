#!/usr/bin/env python3
"""Validate M3 files without importing a search index, generator, or judge.

Exit 0: structural checks pass; read unverified_checks before accepting a run.
Exit 1: malformed input or an inconsistent contract.
Exit 2: structurally valid but a technical stage failure remains.
Synthetic fixtures demonstrate the checker, never experiment performance.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.contracts.m3 import (  # noqa: E402
    ContractError, RESPONSE_TOKENIZER, SUBSETS, canonical_json, config_sha256,
    file_sha256, find_secret_keys, load_json, parse_json, prompt_sha256,
    query_sha256, render_messages,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("manifest", "questions", "answers", "metadata"):
        result.add_argument(f"--{name}", type=Path, required=True)
    for name in ("evidence", "predictions", "scores", "requests", "compare-predictions",
                 "compare-scores", "compare-requests", "batch-ids", "report"):
        result.add_argument(f"--{name}", type=Path)
    result.add_argument("--subset", choices=SUBSETS, help="Otherwise inferred from questions")
    result.add_argument("--schema", type=Path, default=ROOT / "docs/M2_M3_execution/接口字段.schema.json")
    result.add_argument("--config", action="append", default=[], metavar="STAGE=PATH",
                        help="Repeat retrieval/generation/evaluation configs; match by canonical hash")
    result.add_argument("--run-meta", action="append", default=[], metavar="STAGE=PATH",
                        help="Repeat stage run metadata sidecars")
    result.add_argument("--group-metadata", action="append", type=Path, default=[],
                        help="Other subsets' complete metadata for session/image grouping checks")
    result.add_argument("--group-questions", action="append", type=Path, default=[],
                        help="Other subsets' complete questions for duplicate-query grouping checks")
    result.add_argument("--require-provenance", action="store_true",
                        help="Fail if supplied stages lack configs, requests, or linked run metadata")
    return result


def normalized_text(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def metrics(rows: dict[str, dict[str, Any]], expected: int) -> dict[str, Any]:
    tally = Counter(row.get("verdict") for row in rows.values() if row.get("judge_status") == "ok")
    count = sum(tally.values())
    correct, wrong, missing = (tally[label] for label in ("CORRECT", "WRONG", "MISSING"))
    return {"N_fixed": expected, "N_scored": count, "C_correct": correct,
            "W_wrong": wrong, "M_missing": missing,
            "scoring_coverage": count / expected if expected else None,
            "accuracy": correct / count if count else None,
            "hallucination_rate": wrong / count if count else None,
            "missing_rate": missing / count if count else None,
            "truthfulness": (correct - wrong) / count if count else None}


class Checker:
    def __init__(self, args: argparse.Namespace, validator_class: Any):
        self.args = args
        self.validator_class = validator_class
        self.report: dict[str, Any] = {
            "schema_version": "m3.v1", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "valid": False, "errors": [], "warnings": [], "counts": {},
            "paired_comparison": None, "unverified_checks": [
                "Official dataset/index/provider authenticity requires source records and manual review.",
                "Judge semantic correctness and 75-token truncation need E's tokenizer/manual validation.",
            ], "input_files_sha256": {}, "provenance": {},
        }
        self.schema: dict[str, Any] = {}
        self.manifest: dict[str, Any] = {}
        self.manifest_hash = ""
        self.subset = ""
        self.expected: set[str] = set()
        self.full_expected: set[str] = set()
        self.configs: dict[str, dict[str, dict[str, Any]]] = {}
        self.technical_failures = 0
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.artifact_paths: dict[str, Path] = {}

    def issue(self, code: str, message: str, *, file: str | Path | None = None,
              interaction_id: str | None = None, warning: bool = False) -> None:
        item = {"code": code, "message": message}
        if file is not None:
            item["file"] = str(file)
        if interaction_id is not None:
            item["interaction_id"] = interaction_id
        self.report["warnings" if warning else "errors"].append(item)

    def read_json(self, path: Path) -> Any:
        try:
            value = load_json(path)
            self.report["input_files_sha256"][str(path)] = file_sha256(path)
            if find_secret_keys(value):
                self.issue("secret_keys", "Credential fields are forbidden; values were not printed.", file=path)
            return value
        except ContractError as exc:
            self.issue("json", str(exc), file=path)
            return None

    def validate_schema(self, value: Any, kind: str, path: Path, line: int | None = None) -> bool:
        validator = self.validator_class({"$schema": self.schema["$schema"],
            "$defs": self.schema["$defs"], "$ref": f"#/$defs/{kind}"})
        errors = sorted(validator.iter_errors(value), key=lambda error: str(list(error.absolute_path)))
        for error in errors:
            pointer = "/".join(str(part) for part in error.absolute_path)
            self.issue("schema", f"{kind} constraint {error.validator} failed at /{pointer}"
                       + (f" (line {line})" if line is not None else ""), file=path)
        return not errors

    def read_rows(self, path: Path, kind: str) -> list[dict[str, Any]]:
        try:
            content = path.read_text(encoding="utf-8")
            self.report["input_files_sha256"][str(path)] = file_sha256(path)
        except (OSError, UnicodeError):
            self.issue("read", "File could not be read as UTF-8", file=path)
            return []
        rows = []
        for line_number, line in enumerate(content.splitlines(), 1):
            try:
                if not line.strip():
                    raise ContractError("Blank JSONL line")
                value = parse_json(line)
            except ContractError as exc:
                self.issue("jsonl", f"{exc} (line {line_number})", file=path)
                continue
            valid = self.validate_schema(value, kind, path, line_number)
            if find_secret_keys(value):
                self.issue("secret_keys", "Credential fields are forbidden; values were not printed.", file=path)
            if valid:
                rows.append(value)
        return rows

    def index_rows(self, rows: list[dict[str, Any]], path: Path, *, core: bool = False,
                   request: bool = False) -> dict[str, dict[str, Any]]:
        indexed = {}
        allowed = self.full_expected if core else self.expected
        for row in rows:
            ident = row["interaction_id"]
            if ident in indexed:
                self.issue("duplicate_id", "Duplicate interaction_id", file=path, interaction_id=ident)
            indexed[ident] = row
            if row["dataset_manifest_sha256"] != self.manifest_hash:
                self.issue("manifest_hash", "Manifest byte hash differs", file=path, interaction_id=ident)
            if row["subset"] != self.subset or ident not in allowed:
                self.issue("unexpected_id", "ID/subset is outside the expected set", file=path, interaction_id=ident)
        if core:
            indexed = {key: value for key, value in indexed.items() if key in self.expected}
        missing = sorted(self.expected - indexed.keys()) if not request else []
        if missing:
            self.issue("missing_ids", f"Missing {len(missing)} expected IDs", file=path)
        if not indexed and not request:
            self.issue("empty_artifact", "An artifact cannot be empty for this run", file=path)
        self.report["counts"][str(path)] = {"expected": len(self.expected), "rows": len(indexed),
            "missing_ids": missing, "unexpected_ids": sorted(indexed.keys() - self.expected)}
        return indexed

    def uniform(self, rows: dict[str, dict[str, Any]], fields: tuple[str, ...], path: Path) -> None:
        for field in fields:
            if len({canonical_json(row.get(field)) for row in rows.values()}) > 1:
                self.issue("mixed_run", f"Mixed {field} in a single artifact", file=path)

    def initialize(self) -> bool:
        self.schema = self.read_json(self.args.schema)
        if not isinstance(self.schema, dict):
            return False
        try:
            self.validator_class.check_schema(self.schema)
        except Exception:
            self.issue("invalid_schema", "Contract schema is invalid", file=self.args.schema)
            return False
        for kind in ("questions", "answers", "metadata", "evidence", "predictions", "scores", "requests", "manifest"):
            if kind not in self.schema.get("$defs", {}):
                self.issue("invalid_schema", f"Missing definition {kind}", file=self.args.schema)
        self.manifest = self.read_json(self.args.manifest)
        if not self.validate_schema(self.manifest, "manifest", self.args.manifest):
            return False
        self.manifest_hash = file_sha256(self.args.manifest)
        seen = set()
        for subset, spec in self.manifest["subsets"].items():
            if len(spec["ids"]) != spec["count"]:
                self.issue("manifest_count", f"{subset} count differs from ID list length")
            if seen.intersection(spec["ids"]):
                self.issue("manifest_overlap", "Manifest subsets contain overlapping IDs")
            seen.update(spec["ids"])
        if not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", self.manifest["revision"]):
            self.issue("mutable_revision", "Dataset revision must be an immutable commit SHA")
        if "synthetic" in self.manifest["dataset_id"].lower() or self.manifest.get("fixture_notice"):
            self.issue("synthetic_fixture", "Synthetic development fixture; not official experiment evidence.", warning=True)
            self.report["data_classification"] = "synthetic_development"
        else:
            self.report["data_classification"] = "declared_official_unverified"
        if self.args.require_provenance and self.report["data_classification"] == "synthetic_development":
            self.issue("synthetic_provenance", "Development fixtures cannot pass formal provenance acceptance")
        questions = self.read_rows(self.args.questions, "questions")
        subsets = {row["subset"] for row in questions}
        self.subset = self.args.subset or (next(iter(subsets)) if len(subsets) == 1 else "")
        if self.subset not in SUBSETS or subsets != {self.subset}:
            self.issue("subset", "Questions must declare exactly one matching subset")
            return False
        self.full_expected = set(self.manifest["subsets"][self.subset]["ids"])
        self.expected = set(self.full_expected)
        if self.args.batch_ids:
            batch = self.read_json(self.args.batch_ids)
            if (not isinstance(batch, list) or not batch or
                any(not isinstance(item, str) or not item for item in batch) or
                len(set(batch)) != len(batch) or not set(batch).issubset(self.full_expected)):
                self.issue("batch_ids", "Batch must be unique, nonempty IDs from this subset", file=self.args.batch_ids)
                return False
            self.expected = set(batch)
        if not self.expected:
            self.issue("empty_subset", "Selected subset has no expected IDs")
            return False
        self.report.update({"subset": self.subset, "scope": "batch" if self.args.batch_ids else "full",
            "batch_ids_sha256": file_sha256(self.args.batch_ids) if self.args.batch_ids else None,
            "dataset_manifest_sha256": self.manifest_hash, "expected_ids": sorted(self.expected)})
        self.rows["questions"] = self.index_rows(questions, self.args.questions, core=True)
        for kind in ("answers", "metadata"):
            path = getattr(self.args, kind)
            self.rows[kind] = self.index_rows(self.read_rows(path, kind), path, core=True)
        for kind, field in (("questions", "query"), ("answers", "ground_truth")):
            for ident, row in self.rows[kind].items():
                if not row[field].strip():
                    self.issue("empty_text", f"{field} must not be whitespace-only", interaction_id=ident)
        for ident, meta in self.rows["metadata"].items():
            question = self.rows["questions"].get(ident)
            if question and meta["session_id"] != question["session_id"]:
                self.issue("session_id", "Question and metadata sessions differ", interaction_id=ident)
            for field, source in (("source_dataset", "dataset_id"), ("source_revision", "revision"), ("source_split", "split")):
                if meta[field] != self.manifest[source]:
                    self.issue("source_metadata", f"metadata.{field} differs from manifest", interaction_id=ident)
        return True

    def load_configs(self) -> None:
        for item in self.args.config:
            stage, separator, path_text = item.partition("=")
            if not separator or stage not in {"retrieval", "generation", "evaluation"} or not path_text:
                self.issue("config_argument", "Use --config retrieval/generation/evaluation=PATH")
                continue
            path = Path(path_text)
            value = self.read_json(path)
            if not isinstance(value, dict):
                self.issue("config", "Config must be a JSON object", file=path)
                continue
            self.configs.setdefault(stage, {})[config_sha256(value)] = value
        self.report["provenance"]["config_hashes"] = {stage: sorted(items) for stage, items in self.configs.items()}

    def config_for(self, row: dict[str, Any], stage: str) -> dict[str, Any] | None:
        field = {"generation": "generation", "retrieval": "retrieval", "evaluation": "evaluation"}[stage] + "_config_sha256"
        digest = row.get(field)
        config = self.configs.get(stage, {}).get(digest)
        if self.configs.get(stage) and config is None:
            self.issue("config_hash", f"{stage} config hash not backed by a supplied config", interaction_id=row["interaction_id"])
        return config

    def check_stage(self, path: Path, kind: str, label: str) -> dict[str, dict[str, Any]]:
        rows = self.index_rows(self.read_rows(path, kind), path)
        self.rows[label] = rows
        self.artifact_paths[label] = path
        fields = {
            "evidence": ("run_id", "retrieval_config_sha256", "index_revision", "encoder_revision"),
            "predictions": ("run_id", "baseline", "provider", "model", "generation_config_sha256", "retrieval_config_sha256"),
            "scores": ("run_id", "baseline", "source_generation_run_id", "evaluation_config_sha256", "response_tokenizer", "response_max_tokens"),
        }[kind]
        self.uniform(rows, fields, path)
        for ident, row in rows.items():
            question = self.rows["questions"].get(ident)
            if "query_sha256" in row and question and row["query_sha256"] != query_sha256(question["query"]):
                self.issue("query_hash", "Query hash differs from the original question", file=path, interaction_id=ident)
            if kind == "evidence":
                config = self.config_for(row, "retrieval")
                if config is not None:
                    for key in ("index_revision", "encoder_revision"):
                        if key in config and config[key] != row[key]:
                            self.issue("retrieval_version", f"{key} differs from supplied config", interaction_id=ident)
                    if type(config.get("top_k")) is int and len(row["hits"]) > config["top_k"]:
                        self.issue("retrieval_top_k", "More hits than configured top_k", interaction_id=ident)
                if row["retrieval_status"] == "error":
                    self.technical_failures += 1
                ranks = [hit["rank"] for hit in row["hits"]]
                if ranks != list(range(1, len(ranks) + 1)):
                    self.issue("hit_rank", "Hit ranks must be ordered and contiguous from 1", interaction_id=ident)
                for key in ("index_revision", "encoder_revision"):
                    if row[key].lower() in {"main", "master", "latest"}:
                        self.issue("mutable_revision", f"{key} cannot be a moving revision", interaction_id=ident)
            elif kind == "predictions":
                config = self.config_for(row, "generation")
                if config is not None:
                    for field in ("provider", "model"):
                        if field not in config or config[field] != row[field]:
                            self.issue("generation_config", f"{field} differs or is missing in generation config", interaction_id=ident)
                if row["generation_status"] != "ok":
                    self.technical_failures += 1
                elif not row["agent_response"].strip():
                    self.issue("empty_response", "Whitespace-only answer is not generation success", interaction_id=ident)
                if row["baseline"] == "B1":
                    evidence = self.rows.get("evidence", {}).get(ident)
                    if evidence:
                        if row["evidence_status"] != evidence["retrieval_status"]:
                            self.issue("evidence_status", "Prediction does not match retrieval status", interaction_id=ident)
                        if row["retrieval_config_sha256"] != evidence["retrieval_config_sha256"]:
                            self.issue("retrieval_config", "Prediction and evidence configs differ", interaction_id=ident)
                        if evidence["retrieval_status"] == "error" and row["generation_status"] != "blocked":
                            self.issue("generation_blocked", "Retrieval failure must block B1 generation", interaction_id=ident)
                    elif self.args.evidence:
                        if row["evidence_status"] != "missing" or row["generation_status"] != "blocked":
                            self.issue("missing_evidence", "Missing evidence must block B1", interaction_id=ident)
                    if row["evidence_status"] in {"error", "missing"} and row["generation_status"] != "blocked":
                        self.issue("generation_blocked", "Unavailable evidence must block B1", interaction_id=ident)
                    if row["generation_status"] == "blocked" and row["evidence_status"] not in {"error", "missing"}:
                        self.issue("blocked_reason", "B1 blocked requires unavailable evidence", interaction_id=ident)
                elif row["generation_status"] == "blocked":
                    self.issue("blocked_reason", "B0 has no retrieval prerequisite; technical failures use error", interaction_id=ident)
            else:
                config = self.config_for(row, "evaluation")
                if config is not None:
                    for key in ("response_tokenizer", "response_max_tokens"):
                        if key in config and config[key] != row[key]:
                            self.issue("evaluation_config", f"{key} differs from supplied config", interaction_id=ident)
                    if row["scoring_method"] == "llm" and config.get("judge_model") != row["judge_model"]:
                        self.issue("judge_model", "Judge model differs from supplied config", interaction_id=ident)
                if row["response_tokenizer"] != RESPONSE_TOKENIZER:
                    self.issue("tokenizer", "Scoring tokenizer differs from the M3 contract", interaction_id=ident)
                if row["judge_status"] != "ok":
                    self.technical_failures += 1
                if row["judge_status"] == "ok" and row["scoring_method"] == "unscored":
                    self.issue("scoring_method", "Successful score cannot use unscored method", interaction_id=ident)
                if row["judge_status"] == "unscored" and row["scoring_method"] != "unscored":
                    self.issue("scoring_method", "Unscored row must use unscored method", interaction_id=ident)
                if row["scoring_method"] == "llm" and not row["judge_model"]:
                    self.issue("judge_model", "LLM scoring must record the judge model", interaction_id=ident)
        if kind == "scores":
            self.report["counts"][label] = metrics(rows, len(self.expected))
        else:
            status_key = "retrieval_status" if kind == "evidence" else "generation_status"
            self.report["counts"][label] = dict(Counter(row[status_key] for row in rows.values()))
        return rows

    def link_scores(self, scores: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]], label: str) -> None:
        count = sum(row["generation_status"] == "ok" for row in predictions.values())
        self.report["counts"][label].update({"N_generated": count,
            "generation_coverage": count / len(self.expected) if self.expected else None})
        for ident, score in scores.items():
            pred = predictions.get(ident)
            if not pred:
                continue
            if score["baseline"] != pred["baseline"] or score["source_generation_run_id"] != pred["run_id"]:
                self.issue("score_source", "Score references a different baseline/generation run", interaction_id=ident)
            if pred["generation_status"] != "ok":
                if score["judge_status"] != "unscored" or score["agent_response_scored"] is not None:
                    self.issue("score_failure", "Generation failure must remain unscored with no scoring text", interaction_id=ident)
            elif score["judge_status"] == "unscored":
                self.issue("score_failure", "Successful generation cannot be skipped as unscored", interaction_id=ident)
            elif not isinstance(score["agent_response_scored"], str) or not score["agent_response_scored"].strip():
                self.issue("scoring_text", "Attempted evaluation must retain scoring text", interaction_id=ident)
            if score["scoring_method"] == "exact_match" and score["verdict"] != "CORRECT":
                self.issue("scoring_method", "Exact match must be CORRECT", interaction_id=ident)
            answer = self.rows["answers"].get(ident)
            if score["scoring_method"] == "exact_match" and answer and isinstance(score["agent_response_scored"], str):
                if score["agent_response_scored"].strip().lower() != answer["ground_truth"].strip().lower():
                    self.issue("exact_match", "Claimed exact match differs from the reference answer", interaction_id=ident)
            if score["scoring_method"] == "idk" and score["verdict"] != "MISSING":
                self.issue("scoring_method", "IDK method must be MISSING", interaction_id=ident)
            if score["scoring_method"] == "idk" and isinstance(score["agent_response_scored"], str):
                # Same clean_text/substring rule as the imported evaluator.
                clean = re.sub(r"[^a-z0-9\s]", "", score["agent_response_scored"].lower())
                if "i dont know" not in clean and "i do not know" not in clean:
                    self.issue("idk", "Claimed abstention does not match the official IDK rule", interaction_id=ident)

    def check_requests(self, path: Path, predictions: dict[str, dict[str, Any]], label: str) -> None:
        rows = self.index_rows(self.read_rows(path, "requests"), path, request=True)
        for ident, pred in predictions.items():
            if pred["prompt_sha256"] is not None and ident not in rows:
                self.issue("missing_request", "An attempted prompt is missing from the request log", interaction_id=ident)
        audited = 0
        for ident, row in rows.items():
            pred = predictions.get(ident)
            question = self.rows["questions"].get(ident)
            if not pred or not question:
                self.issue("orphan_request", "Request has no corresponding prediction/question", interaction_id=ident)
                continue
            if pred["generation_status"] == "blocked":
                self.issue("blocked_request", "Blocked generation cannot have a model request", interaction_id=ident)
            for field in ("baseline", "run_id", "query_sha256", "prompt_sha256"):
                if row[field] != pred[field]:
                    self.issue("request_source", f"Request {field} differs from prediction", interaction_id=ident)
            messages = row["messages"]
            if [item["role"] for item in messages] != ["system", "user"]:
                self.issue("request_roles", "Only one system and one user message are allowed", interaction_id=ident)
            if prompt_sha256(messages) != row["prompt_sha256"]:
                self.issue("prompt_hash", "Prompt hash differs from actual messages", interaction_id=ident)
            if row["query_sha256"] != query_sha256(question["query"]):
                self.issue("query_hash", "Request query differs from question", interaction_id=ident)
            if question["query"] not in "\n".join(item["content"] for item in messages if item["role"] == "user"):
                self.issue("request_query", "Original query is absent from the user input", interaction_id=ident)
            used = row["evidence_used"]
            if row["baseline"] == "B0" and used:
                self.issue("request_evidence", "B0 cannot include evidence", interaction_id=ident)
            if row["baseline"] == "B1":
                evidence = self.rows.get("evidence", {}).get(ident)
                if not evidence:
                    self.report["unverified_checks"].append(f"{label}: selected evidence provenance not supplied")
                else:
                    hits = {hit["doc_id"]: hit for hit in evidence["hits"]}
                    if evidence["retrieval_status"] == "empty" and used:
                        self.issue("request_evidence", "Empty retrieval cannot provide evidence text", interaction_id=ident)
                    for selected in used:
                        raw = hits.get(selected["doc_id"])
                        if (not raw or not normalized_text(selected["text"]) or
                            normalized_text(selected["text"]) not in normalized_text(raw["title"] + "\n" + raw["text"])):
                            self.issue("evidence_provenance", "Selected text is not traceable to the returned hit", interaction_id=ident)
            config = self.config_for(pred, "generation")
            if not config or not config.get("prompt_templates"):
                continue
            try:
                expected = render_messages(config, row["baseline"], question["query"], used)
                if messages != expected:
                    self.issue("request_content", "Messages differ from the frozen query/evidence template", interaction_id=ident)
                else:
                    audited += 1
            except ContractError as exc:
                self.issue("prompt_template", str(exc), interaction_id=ident)
        self.report["provenance"][label] = {"logged": len(rows), "template_reconstructed": audited}
        if audited != len(rows):
            self.report["unverified_checks"].append(f"{label}: not all messages reconstructed from frozen templates")
            if self.args.require_provenance:
                self.issue("request_provenance", "All messages must be reconstructed for strict acceptance")

    def check_groups(self) -> None:
        metadata = list(self.rows["metadata"].values())
        questions = list(self.rows["questions"].values())
        for kind, paths, target in (("metadata", self.args.group_metadata, metadata),
                                    ("questions", self.args.group_questions, questions)):
            for path in paths:
                target.extend(self.read_rows(path, kind))
        for kind, rows in (("metadata", metadata), ("questions", questions)):
            seen_ids = set()
            for row in rows:
                ident, subset = row["interaction_id"], row["subset"]
                if row["dataset_manifest_sha256"] != self.manifest_hash or ident not in self.manifest["subsets"][subset]["ids"]:
                    self.issue("group_source", "Grouping row does not belong to this manifest", interaction_id=ident)
                if ident in seen_ids:
                    self.issue("duplicate_group_id", f"Repeated ID in {kind} grouping inputs", interaction_id=ident)
                seen_ids.add(ident)
            checks = ("session_id", "image_group_id") if kind == "metadata" else ("query",)
            for field in checks:
                seen = {}
                for row in rows:
                    value = row.get(field)
                    if value is None:
                        continue
                    key = " ".join(value.casefold().split()) if field == "query" else value
                    if key in seen and seen[key] != row["subset"]:
                        self.issue("group_overlap", f"{field} group spans subsets", interaction_id=row["interaction_id"])
                    seen[key] = row["subset"]
            all_ids = {ident for spec in self.manifest["subsets"].values() for ident in spec["ids"]}
            if seen_ids != all_ids:
                self.report["unverified_checks"].append(f"Cross-subset {kind} grouping incomplete: only {len(seen_ids)}/{len(all_ids)} IDs supplied")
        if any(row.get("image_group_id") is None for row in metadata):
            self.report["unverified_checks"].append("Shared-image grouping cannot be proved for null image_group_id")

    def compare(self) -> None:
        primary, other = self.rows.get("predictions"), self.rows.get("compare_predictions")
        if other and not primary:
            self.issue("comparison", "Comparison requires primary predictions")
            return
        if primary and other:
            baselines = {next(iter(rows.values()))["baseline"] for rows in (primary, other) if rows}
            if baselines != {"B0", "B1"}:
                self.issue("comparison", "Comparison must include exactly B0 and B1")
            for ident in self.expected.intersection(primary, other):
                for field in ("provider", "model"):
                    if primary[ident][field] != other[ident][field]:
                        self.issue("comparison_model", f"B0/B1 {field} differs", interaction_id=ident)
            configs = [self.config_for(next(iter(rows.values())), "generation") for rows in (primary, other)]
            if all(configs):
                def common(config: dict[str, Any]) -> dict[str, Any]:
                    result = dict(config)
                    for key in ("baseline", "evidence_budget_tokens", "evidence_processing", "evidence_template"):
                        result.pop(key, None)
                    return result
                if canonical_json(common(configs[0])) != canonical_json(common(configs[1])):
                    self.issue("comparison_config", "B0/B1 common generation settings differ")
            else:
                self.report["unverified_checks"].append("B0/B1 common generation parameters not verified against actual configs")
        first, second = self.rows.get("scores"), self.rows.get("compare_scores")
        if second and not first:
            self.issue("comparison", "Comparison requires primary scores")
        if first and second:
            for ident in self.expected.intersection(first, second):
                for field in ("evaluation_config_sha256", "response_tokenizer", "response_max_tokens"):
                    if first[ident][field] != second[ident][field]:
                        self.issue("comparison_evaluation", f"B0/B1 {field} differs", interaction_id=ident)
            common_ids = sorted(ident for ident in first.keys() & second.keys()
                                if first[ident]["judge_status"] == second[ident]["judge_status"] == "ok")
            by_baseline = {}
            for rows in (first, second):
                if rows:
                    baseline = next(iter(rows.values()))["baseline"]
                    by_baseline[baseline] = metrics({key: rows[key] for key in common_ids}, len(common_ids))
            if set(by_baseline) == {"B0", "B1"}:
                b0, b1 = by_baseline["B0"], by_baseline["B1"]
                self.report["paired_comparison"] = {"n_common_scored": len(common_ids), "common_ids": common_ids,
                    "b0": b0, "b1": b1,
                    "accuracy_delta": b1["accuracy"] - b0["accuracy"] if common_ids else None,
                    "truthfulness_delta": b1["truthfulness"] - b0["truthfulness"] if common_ids else None}
            else:
                self.issue("comparison", "Scores comparison must include B0 and B1")

    def check_run_meta(self) -> None:
        supplied = []
        for item in self.args.run_meta:
            stage, separator, path_text = item.partition("=")
            if not separator or stage not in {"retrieval", "generation", "evaluation"}:
                self.issue("run_meta_argument", "Use --run-meta STAGE=PATH")
                continue
            path = Path(path_text)
            value = self.read_json(path)
            if not isinstance(value, dict):
                self.issue("run_meta", "Run metadata must be an object", file=path)
                continue
            required = ("run_id", "stage", "subset", "schema_version", "code_commit", "input_files_sha256",
                        "output_files_sha256", "config", "config_sha256", "started_at", "finished_at",
                        "hardware", "N_expected", "N_success", "N_failed", "retries", "peak_memory_mb")
            if any(key not in value for key in required):
                self.issue("run_meta", "Run metadata is missing required fields", file=path)
                continue
            if value["stage"] != stage or value["subset"] != self.subset or value["schema_version"] != "m3.v1":
                self.issue("run_meta", "Run metadata stage/subset/schema differs", file=path)
            for field in ("run_id", "code_commit"):
                if not isinstance(value[field], str) or not value[field].strip():
                    self.issue("run_meta", f"{field} must be a nonempty string", file=path)
            if not isinstance(value["hardware"], dict):
                self.issue("run_meta", "Hardware must be a JSON object", file=path)
            start, finish = None, None
            try:
                start = datetime.fromisoformat(value["started_at"].replace("Z", "+00:00"))
                finish = datetime.fromisoformat(value["finished_at"].replace("Z", "+00:00"))
                if start.tzinfo is None or finish.tzinfo is None or finish < start:
                    raise ValueError
            except (AttributeError, TypeError, ValueError):
                self.issue("run_meta_time", "Use ordered ISO timestamps with a timezone", file=path)
            if value["peak_memory_mb"] is not None and (
                type(value["peak_memory_mb"]) not in (int, float) or value["peak_memory_mb"] < 0):
                self.issue("run_meta_memory", "Peak memory must be nonnegative or null (not measured)", file=path)
            if not isinstance(value["config"], dict) or config_sha256(value["config"]) != value["config_sha256"]:
                self.issue("run_meta_config", "Embedded config hash differs", file=path)
            for field in ("N_expected", "N_success", "N_failed", "retries"):
                if type(value[field]) is not int or value[field] < 0:
                    self.issue("run_meta_count", "Run counts must be nonnegative integers", file=path)
            if all(type(value[key]) is int for key in ("N_expected", "N_success", "N_failed")):
                if value["N_expected"] != value["N_success"] + value["N_failed"]:
                    self.issue("run_meta_count", "Run success/failure counts do not sum to expected", file=path)
                if value["N_expected"] != len(self.expected):
                    self.issue("run_meta_count", "Run expected count differs from selected scope", file=path)
            if self.args.batch_ids:
                batch = value.get("batch_ids")
                if not isinstance(batch, list) or set(batch) != self.expected or len(batch) != len(self.expected):
                    self.issue("run_meta_batch", "Batch metadata must include the exact selected ID list", file=path)
            for field in ("input_files_sha256", "output_files_sha256"):
                mapping = value[field]
                if not isinstance(mapping, dict) or not mapping:
                    self.issue("run_meta_hash", "Run file hashes must be nonempty objects", file=path)
                    continue
                for filename, digest in mapping.items():
                    target = Path(filename)
                    if not target.is_absolute():
                        target = path.parent / target
                    if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
                        self.issue("run_meta_hash", "Invalid run file SHA256", file=path)
                    elif target.is_file():
                        if file_sha256(target) != digest:
                            self.issue("run_meta_hash", "Referenced file bytes differ", file=target)
                    else:
                        self.issue("run_meta_path", "Referenced file is unavailable", file=target,
                                   warning=not self.args.require_provenance)
            supplied.append((stage, value))
        for label, rows in self.rows.items():
            stage = {"evidence": "retrieval", "predictions": "generation", "compare_predictions": "generation",
                     "scores": "evaluation", "compare_scores": "evaluation"}.get(label)
            if not stage or not rows:
                continue
            sample = next(iter(rows.values()))
            linked = [value for kind, value in supplied if kind == stage and value["run_id"] == sample["run_id"]
                      and (value.get("baseline") is None or value["baseline"] == sample.get("baseline"))]
            output_digest = file_sha256(self.artifact_paths[label])
            matching = [value for value in linked if isinstance(value["output_files_sha256"], dict)
                        and output_digest in value["output_files_sha256"].values()]
            if matching:
                linked = matching
            if not linked:
                self.report["unverified_checks"].append(f"{label}: linked run metadata not supplied")
                if self.args.require_provenance:
                    self.issue("run_meta_missing", f"{label} needs linked run metadata")
            for value in linked:
                if value["config_sha256"] != sample[f"{stage}_config_sha256"]:
                    self.issue("run_meta_config", f"{label} and linked config hashes differ")
                if value.get("baseline") is not None and value["baseline"] != sample.get("baseline"):
                    self.issue("run_meta_baseline", f"{label} baseline differs from run metadata")
                output_hashes = value["output_files_sha256"]
                if not isinstance(output_hashes, dict) or file_sha256(self.artifact_paths[label]) not in output_hashes.values():
                    self.issue("run_meta_output", f"{label} bytes are not recorded by linked run metadata")
                input_hashes = value["input_files_sha256"]
                if not isinstance(input_hashes, dict):
                    continue
                for path in (self.args.manifest, self.args.questions):
                    if file_sha256(path) not in input_hashes.values():
                        self.issue("run_meta_input", f"{label} does not record the inspected manifest/questions")
                if stage == "evaluation" and file_sha256(self.args.answers) not in input_hashes.values():
                    self.issue("run_meta_input", f"{label} does not record the reference answers")
                if stage == "evaluation":
                    source = "compare_predictions" if label == "compare_scores" else "predictions"
                    if source in self.artifact_paths and file_sha256(self.artifact_paths[source]) not in input_hashes.values():
                        self.issue("run_meta_stage_input", f"{label} does not record the inspected predictions")
                if stage == "generation" and sample["baseline"] == "B1" and "evidence" in self.artifact_paths:
                    if file_sha256(self.artifact_paths["evidence"]) not in input_hashes.values():
                        self.issue("run_meta_stage_input", f"{label} does not record the inspected evidence")
                if stage in {"retrieval", "generation"} and file_sha256(self.args.answers) in input_hashes.values():
                    self.issue("run_meta_answer_leakage", f"{label} must not read reference answers")
                status = {"retrieval": "retrieval_status", "generation": "generation_status", "evaluation": "judge_status"}[stage]
                success = sum(row[status] in ({"ok", "empty"} if stage == "retrieval" else {"ok"}) for row in rows.values())
                if value["N_success"] != success or value["N_failed"] != len(self.expected) - success:
                    self.issue("run_meta_count", f"{label} counts differ from artifact status rows")

    def run(self) -> dict[str, Any]:
        if not self.initialize():
            return self.finish()
        self.load_configs()
        if self.args.evidence:
            self.check_stage(self.args.evidence, "evidence", "evidence")
        for label in ("predictions", "compare_predictions"):
            path = getattr(self.args, label)
            if path:
                self.check_stage(path, "predictions", label)
        for label, source in (("scores", "predictions"), ("compare_scores", "compare_predictions")):
            path = getattr(self.args, label)
            if path:
                scores = self.check_stage(path, "scores", label)
                if source not in self.rows:
                    self.report["unverified_checks"].append(f"{label}: source predictions not supplied")
                    if self.args.require_provenance:
                        self.issue("score_source", f"{label} requires source predictions")
                else:
                    self.link_scores(scores, self.rows[source], label)
        for label, source in (("requests", "predictions"), ("compare_requests", "compare_predictions")):
            path = getattr(self.args, label)
            if path and source not in self.rows:
                self.issue("request_source", f"{label} requires {source}")
            elif path:
                self.check_requests(path, self.rows[source], label)
            elif source in self.rows:
                self.report["unverified_checks"].append(f"{source}: actual request inputs not inspected")
                if self.args.require_provenance:
                    self.issue("requests_missing", f"{source} requires request logs")
        for label, rows in self.rows.items():
            stage = {"evidence": "retrieval", "predictions": "generation", "compare_predictions": "generation",
                     "scores": "evaluation", "compare_scores": "evaluation"}.get(label)
            if stage and not self.configs.get(stage):
                self.report["unverified_checks"].append(f"{label}: actual {stage} config not supplied")
                if self.args.require_provenance:
                    self.issue("config_missing", f"{label} requires actual config")
            if label in {"predictions", "compare_predictions"} and any(row["baseline"] == "B1" for row in rows.values()) and not self.args.evidence:
                self.report["unverified_checks"].append(f"{label}: B1 evidence not inspected")
                if self.args.require_provenance:
                    self.issue("evidence_missing", f"{label} requires B1 evidence")
        self.check_groups()
        self.compare()
        self.check_run_meta()
        return self.finish()

    def finish(self) -> dict[str, Any]:
        self.report["unverified_checks"] = sorted(set(self.report["unverified_checks"]))
        self.report["warnings"].extend({"code": "unverified", "message": message}
                                       for message in self.report["unverified_checks"])
        self.report["valid"] = not self.report["errors"]
        self.report["technical_failures"] = self.technical_failures
        self.report["exit_code"] = 1 if self.report["errors"] else (2 if self.technical_failures else 0)
        self.report["acceptance"] = "invalid" if self.report["errors"] else (
            "technical_failures_remaining" if self.technical_failures else "checked_scope_only")
        return self.report


def main(argv: list[str] | None = None) -> int:
    # Windows pipes otherwise use the local ANSI code page for Chinese paths.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("Install requirements-integration.txt in your Python environment.", file=sys.stderr)
        return 1
    checker = Checker(args, Draft202012Validator)
    try:
        report = checker.run()
    except (ContractError, OSError, ValueError, KeyError, TypeError) as exc:
        checker.issue("validation_error", f"Validation could not finish ({type(exc).__name__}); no input values printed.")
        report = checker.finish()
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.report:
        if args.report.resolve() in {Path(path).resolve() for path in report["input_files_sha256"]}:
            checker.issue("report_path", "Report must not overwrite an input file", file=args.report)
            report = checker.finish()
            print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
            return 1
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(serialized, encoding="utf-8")
        except OSError:
            print("Validation report could not be written.", file=sys.stderr)
            return 1
    print(serialized, end="")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
