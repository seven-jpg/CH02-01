#!/usr/bin/env python3
"""Prepare a dev-only top_k sweep; execute retrieval only with --run.

The default writes configs and a plan, without loading an index or model.
Retrieval completion is not evidence that a candidate gives better answers.
Existing results are never overwritten: use a new --output-dir for another run.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.retrieve import (  # noqa: E402
    StructuralError, load_config, load_manifest, load_questions, read_jsonl,
    row_is_sound, select_expected,
)
from src.contracts.m3 import (  # noqa: E402
    ContractError, config_sha256, file_sha256, load_json,
)
from src.retrieval.text_retrieval import ConfigError, RetrievalConfig  # noqa: E402

QUESTION_KEYS = frozenset({"schema_version", "subset", "interaction_id",
                           "dataset_manifest_sha256", "session_id", "query"})
INDEX_PLACEHOLDER = "REPLACE_WITH_LOCAL_INDEX_DIRECTORY"


class SweepError(ValueError):
    """Invalid sweep inputs or incompatible existing artifacts."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("manifest", "questions", "config", "output-dir"):
        result.add_argument(f"--{name}", type=Path, required=True)
    result.add_argument("--top-k", nargs="+", type=int, default=[1, 3, 5],
                        help="Unique positive candidates, in execution order (default: 1 3 5)")
    result.add_argument("--index-path", type=Path,
                        help="Local writable index directory; required only for --run")
    result.add_argument("--device", choices=("auto", "cpu", "cuda"))
    result.add_argument("--run", action="store_true",
                        help="Run retrieve.py sequentially; otherwise prepare commands only")
    result.add_argument("--timeout-seconds", type=int, default=3600,
                        help="Bounded timeout for each retrieval subprocess (default: 3600)")
    return result


def _has_fetch_k(value: Any) -> bool:
    if isinstance(value, dict):
        return "fetch_k" in value or any(_has_fetch_k(item) for item in value.values())
    return isinstance(value, list) and any(_has_fetch_k(item) for item in value)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _powershell_command(command: list[str]) -> str:
    # list2cmdline quotes for CreateProcess, not for a shell. Literal PowerShell
    # arguments also protect &, $, semicolons and apostrophes in local paths.
    return "& " + " ".join("'" + item.replace("'", "''") + "'" for item in command)


def _write_new_or_same(path: Path, content: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise SweepError("Existing preparation differs; use a new --output-dir")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != content:
            raise SweepError("Concurrent preparation differs; use a new --output-dir") from None


def inputs(args: argparse.Namespace) -> tuple[dict[str, Any], str, dict[str, str], dict[str, Any]]:
    if any(type(value) is not int or value < 1 for value in args.top_k) or len(set(args.top_k)) != len(args.top_k):
        raise SweepError("--top-k must contain unique positive integers")
    if type(args.timeout_seconds) is not int or args.timeout_seconds < 1:
        raise SweepError("--timeout-seconds must be a positive integer")
    manifest, manifest_hash = load_manifest(args.manifest)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", manifest["revision"]):
        raise SweepError("Dataset revision must be a full immutable commit SHA")
    seen: set[str] = set()
    for name in ("smoke", "dev", "eval"):
        spec = manifest["subsets"][name]
        if not isinstance(spec, dict):
            raise SweepError("Manifest subset specification must be an object")
        ids, count = spec.get("ids"), spec.get("count")
        if (not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids)
                or type(count) is not int or count != len(ids) or len(set(ids)) != len(ids)
                or seen.intersection(ids)):
            raise SweepError("Manifest subset IDs/counts must be unique, consistent and disjoint")
        seen.update(ids)
    expected, _ = select_expected(manifest, "dev", None)
    if not expected:
        raise SweepError("The frozen dev subset must have a positive sample count")
    # The C loader validates hashes and IDs. Check the strict question envelope first,
    # so answers, images, captions and history cannot be handed to this sweep.
    for row in read_jsonl(args.questions):
        if (set(row) != QUESTION_KEYS or row.get("subset") != "dev"
                or not isinstance(row.get("session_id"), str) or not row["session_id"].strip()
                or not isinstance(row.get("dataset_manifest_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["dataset_manifest_sha256"])):
            raise SweepError("Questions must use the strict dev-only text question envelope")
    subset, queries = load_questions(args.questions, manifest_hash, expected)
    if subset != "dev" or set(queries) != set(expected):
        raise SweepError("Questions must cover exactly the complete frozen dev ID set")
    config = load_config(args.config)
    if _has_fetch_k(config):
        raise SweepError("fetch_k is unsupported; sweep only top_k")
    RetrievalConfig.from_dict(config)
    for key in ("index_revision", "encoder_revision"):
        if not re.fullmatch(r"[0-9a-fA-F]{40}", config[key]):
            raise SweepError("Index and encoder revisions must be full immutable commit SHAs")
    if args.device:
        config = {**config, "device": args.device}
    return manifest, manifest_hash, queries, config


def build_plan(args: argparse.Namespace, manifest: dict[str, Any], manifest_hash: str,
               queries: dict[str, str], config: dict[str, Any]) -> tuple[dict[str, Any], dict[Path, bytes]]:
    destination = args.output_dir.resolve()
    index = str(args.index_path.resolve()) if args.index_path else INDEX_PLACEHOLDER
    variants, files = [], {}
    for candidate in args.top_k:
        candidate_config = {**config, "top_k": candidate}
        digest = config_sha256(candidate_config)
        directory = destination / f"top_k_{candidate}"
        config_path = directory / "retrieval.json"
        evidence_path = directory / "evidence.jsonl"
        run_meta_path = directory / "run_meta_retrieval.json"
        command = [sys.executable, str(ROOT / "scripts/retrieve.py"),
                   "--manifest", str(args.manifest.resolve()),
                   "--questions", str(args.questions.resolve()), "--subset", "dev",
                   "--config", str(config_path), "--output", str(evidence_path),
                   "--run-meta", str(run_meta_path), "--index-path", index]
        variants.append({"top_k": candidate, "retrieval_config_sha256": digest,
            "run_id": f"retrieval-dev-{digest[:12]}-{manifest_hash[:8]}",
            "config_path": str(config_path), "evidence_path": str(evidence_path),
            "run_meta_path": str(run_meta_path), "command": command,
            "powershell_command": _powershell_command(command)})
        files[config_path] = _json_bytes(candidate_config)
    plan = {"schema_version": "m3.retrieval_sweep.v1", "subset": "dev",
        "scope": "full", "N_expected": len(queries),
        "data_classification": "synthetic_development" if manifest.get("fixture_notice") else "declared_official_unverified",
        "input_files_sha256": {str(path.resolve()): file_sha256(path)
                               for path in (args.manifest, args.questions, args.config)},
        "dataset_manifest_sha256": manifest_hash, "index_path": index,
        "timeout_seconds": args.timeout_seconds, "variants": variants,
        "retrieval_execution": "not_run_by_preparation",
        "answer_quality_evaluation": "not_run", "optimal_top_k": None,
        "execution_report": str(destination / "execution.json"),
        "notice": "Preparation is not a retrieval result. Execution, if requested, is recorded separately; successful retrieval does not select the best top_k. Existing outputs require a new --output-dir."}
    files[destination / "plan.json"] = _json_bytes(plan)
    return plan, files


def prepare(files: dict[Path, bytes]) -> None:
    # Check all existing destinations before writing even the first config.
    for path, content in files.items():
        if path.exists() and (not path.is_file() or path.read_bytes() != content):
            raise SweepError("Existing preparation differs; use a new --output-dir")
    for path, content in files.items():
        _write_new_or_same(path, content)


def preflight(args: argparse.Namespace) -> None:
    if args.index_path is None or not args.index_path.is_dir():
        raise SweepError("--run requires an existing local --index-path; use prepare-only without an index")
    if not (args.index_path / "chroma.sqlite3").is_file():
        raise SweepError("--index-path must contain the Chroma index chroma.sqlite3")
    missing = [name for name in ("torch", "transformers", "chromadb", "numpy", "huggingface_hub")
               if importlib.util.find_spec(name) is None]
    if missing:
        raise SweepError("--run dependencies missing: " + ", ".join(missing))


def verify_result(variant: dict[str, Any], plan: dict[str, Any], queries: dict[str, str],
                  config: dict[str, Any]) -> dict[str, int]:
    evidence_path, meta_path = Path(variant["evidence_path"]), Path(variant["run_meta_path"])
    rows = read_jsonl(evidence_path)
    identifiers = [row.get("interaction_id") for row in rows]
    if (not rows or len(rows) != len(queries) or len(set(identifiers)) != len(identifiers)
            or set(identifiers) != set(queries)):
        raise SweepError("Retrieval did not produce exactly one evidence row per frozen dev ID")
    required = {"subset": "dev", "dataset_manifest_sha256": plan["dataset_manifest_sha256"],
        "retrieval_config_sha256": variant["retrieval_config_sha256"], "run_id": variant["run_id"],
        "index_revision": config["index_revision"], "encoder_revision": config["encoder_revision"]}
    for row in rows:
        if (not row_is_sound(row, queries) or any(row.get(key) != value for key, value in required.items())
                or row["retrieval_status"] not in {"ok", "empty"} or len(row["hits"]) > variant["top_k"]):
            raise SweepError("Retrieval evidence is invalid, mismatched or contains technical failures")
    meta = load_json(meta_path)
    if (not isinstance(meta, dict) or meta.get("stage") != "retrieval" or meta.get("subset") != "dev"
            or meta.get("schema_version") != "m3.v1" or meta.get("run_id") != variant["run_id"]
            or meta.get("config_sha256") != variant["retrieval_config_sha256"]
            or not isinstance(meta.get("config"), dict)
            or config_sha256(meta["config"]) != variant["retrieval_config_sha256"]):
        raise SweepError("Retrieval run metadata does not match the candidate")
    for field, value in (("N_expected", len(queries)), ("N_success", len(queries)), ("N_failed", 0)):
        if type(meta.get(field)) is not int or meta[field] != value:
            raise SweepError("Retrieval run counts do not match complete successful traversal")
    inputs_recorded, outputs_recorded = meta.get("input_files_sha256"), meta.get("output_files_sha256")
    if (not isinstance(inputs_recorded, dict) or not isinstance(outputs_recorded, dict)
            or any(plan["input_files_sha256"][str(path.resolve())] not in inputs_recorded.values()
                   for path in (Path(variant["command"][variant["command"].index(flag) + 1])
                                for flag in ("--manifest", "--questions")))
            or file_sha256(evidence_path) not in outputs_recorded.values()):
        raise SweepError("Retrieval run metadata does not link the inspected input/output bytes")
    return dict(Counter(row["retrieval_status"] for row in rows))


def execute(args: argparse.Namespace, plan: dict[str, Any], queries: dict[str, str],
            config: dict[str, Any]) -> int:
    execution_path = Path(plan["execution_report"])
    for variant in plan["variants"]:
        directory = Path(variant["config_path"]).parent
        if any((directory / name).exists() for name in ("evidence.jsonl", "run_meta_retrieval.json", "stdout.log", "stderr.log")):
            raise SweepError("Run outputs already exist; use a new --output-dir. This sweep does not resume.")
    if execution_path.exists():
        raise SweepError("Execution report already exists; use a new --output-dir")
    report: dict[str, Any] = {"schema_version": plan["schema_version"], "subset": "dev",
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running", "candidates": [],
        "answer_quality_evaluation": "not_run", "optimal_top_k": None}
    exit_code = 0
    for variant in plan["variants"]:
        record: dict[str, Any] = {"top_k": variant["top_k"], "status": "failed"}
        stdout, stderr = "", ""
        started = time.monotonic()
        try:
            if any(file_sha256(path) != digest for path, digest in plan["input_files_sha256"].items()):
                raise SweepError("Sweep inputs changed after preparation")
            actual_config = load_config(Path(variant["config_path"]))
            if config_sha256(actual_config) != variant["retrieval_config_sha256"]:
                raise SweepError("Prepared candidate config changed")
            child = subprocess.run(variant["command"], cwd=ROOT, capture_output=True,
                                   encoding="utf-8", errors="replace", timeout=args.timeout_seconds,
                                   shell=False)
            stdout, stderr = child.stdout or "", child.stderr or ""
            record["returncode"] = child.returncode
            if child.returncode:
                raise SweepError("Retrieval subprocess failed; inspect the candidate logs")
            record["counts"] = verify_result(variant, plan, queries, config)
            record["status"] = "retrieval_complete"
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = exc.stdout or "", exc.stderr or ""
            record["error"] = "Retrieval subprocess timed out"
            exit_code = 2
        except (SweepError, StructuralError, ContractError, OSError, TypeError, ValueError) as exc:
            record["error"] = str(exc) if isinstance(exc, SweepError) else f"Retrieval validation failed ({type(exc).__name__})"
            exit_code = 2
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["candidates"].append(record)
        for name, content in (("stdout.log", stdout), ("stderr.log", stderr)):
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            _write_new_or_same(Path(variant["config_path"]).parent / name, content.encode("utf-8"))
        if exit_code:
            break
    report["status"] = "retrieval_complete" if not exit_code else "failed"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["not_run_top_k"] = [row["top_k"] for row in plan["variants"][len(report["candidates"]):]]
    _write_new_or_same(execution_path, _json_bytes(report))
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        manifest, digest, queries, config = inputs(args)
        if args.run:
            preflight(args)
        plan, files = build_plan(args, manifest, digest, queries, config)
        prepare(files)
        if args.run:
            result = execute(args, plan, queries, config)
            print("Retrieval execution recorded; answer quality and optimal top_k remain unevaluated.")
            return result
        print(f"Prepared only: {args.output_dir.resolve() / 'plan.json'}")
        print("No retrieval/model/API was run. Replace the local index path before execution.")
        for variant in plan["variants"]:
            print(variant["powershell_command"])
        return 0
    except (SweepError, StructuralError, ConfigError, ContractError, OSError, TypeError, ValueError) as exc:
        # Config loaders do not print credential values; do not echo arbitrary OS errors.
        print(f"Sweep error: {exc}" if isinstance(exc, (SweepError, StructuralError, ConfigError, ContractError))
              else f"Sweep error ({type(exc).__name__}); no input values printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
