#!/usr/bin/env python3
"""Generate audited B0/B1 predictions from text-only M3 inputs.

The command never opens answers, metadata, images, or the CRAG-MM agent. Use
``--dry-run`` to inspect requests without credentials or a model call.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.text_agent import TextAgent, retry_generate  # noqa: E402
from src.contracts.m3 import (  # noqa: E402
    ContractError,
    SCHEMA_VERSION,
    SUBSETS,
    config_sha256,
    file_sha256,
    find_secret_keys,
    load_json,
    parse_json,
    prompt_sha256,
    query_sha256,
    render_messages,
)


FORBIDDEN_INPUT_KEYS = {"answers", "ground_truth", "image", "image_url", "ocr", "caption",
                        "full_query", "history", "message_histories", "visual_entities"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    content = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)
    temp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"{path}: blank JSONL line {number}")
        value = parse_json(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}: line {number} is not an object")
        rows.append(value)
    return rows


def read_questions(path: Path, manifest_hash: str) -> tuple[str, list[dict[str, Any]]]:
    rows = read_jsonl(path)
    if not rows:
        raise ValueError("questions file is empty")
    subset = rows[0].get("subset")
    if subset not in SUBSETS:
        raise ValueError("questions must contain one valid subset")
    seen: set[str] = set()
    for row in rows:
        if row.get("schema_version") != SCHEMA_VERSION or row.get("subset") != subset:
            raise ValueError("questions schema/subset mismatch")
        ident = row.get("interaction_id")
        query = row.get("query")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError("questions contain a duplicate or invalid interaction_id")
        if not isinstance(query, str) or not query:
            raise ValueError(f"empty query for {ident}")
        if row.get("dataset_manifest_sha256") != manifest_hash:
            raise ValueError(f"manifest hash mismatch for question {ident}")
        if any(key in row for key in FORBIDDEN_INPUT_KEYS):
            raise ValueError(f"forbidden model input field in question {ident}")
        seen.add(ident)
    return subset, rows


def read_batch(path: Path | None, subset: str, manifest: dict[str, Any]) -> list[str]:
    full = manifest["subsets"][subset]["ids"]
    if path is None:
        return list(full)
    value = load_json(path)
    if (not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value)
            or len(set(value)) != len(value) or not set(value).issubset(full)):
        raise ValueError("batch-ids must be a nonempty unique list from the selected subset")
    return value


def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]*>", " ", value))
    return " ".join(value.split())


def select_evidence(row: dict[str, Any], token_budget: int) -> list[dict[str, str]]:
    hits = row.get("hits") if row.get("retrieval_status") == "ok" else []
    if not isinstance(hits, list):
        return []
    result: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_text: set[str] = set()
    used_estimated_tokens = 0
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        doc_id = str(hit.get("doc_id", "")).strip()
        text = clean_text(str(hit.get("text", "")))
        if not doc_id or not text or doc_id in seen_ids or text in seen_text:
            continue
        # The contract intentionally records an estimate, not a provider tokenizer count.
        remaining_chars = max(0, (token_budget - used_estimated_tokens) * 4)
        if remaining_chars <= 0:
            break
        text = text[:remaining_chars].strip()
        if not text:
            break
        result.append({"doc_id": doc_id, "text": text})
        seen_ids.add(doc_id)
        seen_text.add(text)
        used_estimated_tokens += max(1, (len(text) + 3) // 4)
    return result


def load_evidence(path: Path | None, manifest_hash: str, expected_ids: set[str]) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    rows = read_jsonl(path)
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        ident = row.get("interaction_id")
        if not isinstance(ident, str) or ident in indexed:
            raise ValueError("evidence contains duplicate or invalid interaction_id")
        if row.get("dataset_manifest_sha256") != manifest_hash or ident not in expected_ids:
            raise ValueError(f"evidence ID/manifest mismatch for {ident}")
        if not isinstance(row.get("query_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["query_sha256"]):
            raise ValueError(f"invalid evidence query hash for {ident}")
        if row.get("retrieval_status") not in {"ok", "empty", "error"}:
            raise ValueError(f"invalid evidence status for {ident}")
        indexed[ident] = row
    return indexed


def git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                capture_output=True, check=True)
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "working-tree-unknown"


def hardware() -> dict[str, Any]:
    return {"platform": sys.platform, "python": sys.version.split()[0], "gpu": None,
            "ram_mb": None, "measurement": "not measured"}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--questions", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--baseline", choices=("B0", "B1"), required=True)
    result.add_argument("--config", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--evidence", type=Path, help="Required for B1; omitted B1 evidence is missing/blocked.")
    result.add_argument("--batch-ids", type=Path)
    result.add_argument("--run-id", help="Reuse this ID to resume an existing output safely.")
    result.add_argument("--requests-output", type=Path)
    result.add_argument("--run-meta-output", type=Path)
    result.add_argument("--dry-run", action="store_true", help="Build requests but never call a provider.")
    result.add_argument("--no-resume", action="store_true", help="Ignore existing matching output rows.")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    started = utc_now()
    try:
        manifest = load_json(args.manifest)
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("invalid manifest")
        manifest_hash = file_sha256(args.manifest)
        subset, questions = read_questions(args.questions, manifest_hash)
        full_ids = {row["interaction_id"] for row in questions}
        batch_ids = read_batch(args.batch_ids, subset, manifest)
        expected_ids = set(batch_ids)
        if expected_ids != full_ids and args.batch_ids is None:
            raise ValueError("questions must cover the entire manifest subset when --batch-ids is omitted")
        config = load_json(args.config)
        if not isinstance(config, dict):
            raise ValueError("generation config must be a JSON object")
        if find_secret_keys(config):
            raise ValueError("generation config must not contain credential fields; use environment variables")
        generation_hash = config_sha256(config)
        if args.baseline == "B0" and args.evidence:
            raise ValueError("B0 must not receive evidence")
        evidence_rows = load_evidence(args.evidence, manifest_hash, expected_ids) if args.baseline == "B1" else {}
        retrieval_hashes = {row.get("retrieval_config_sha256") for row in evidence_rows.values()
                            if row.get("retrieval_status") in {"ok", "empty"}}
        if len(retrieval_hashes) > 1:
            raise ValueError("evidence mixes retrieval configuration hashes")
        retrieval_hash = next(iter(retrieval_hashes), None)
        if args.baseline == "B0":
            retrieval_hash = None
        suffix = f"_{args.output.stem}" if args.batch_ids else ""
        request_path = args.requests_output or args.output.with_name(f"requests_{args.baseline.lower()}{suffix}.jsonl")
        meta_path = args.run_meta_output or args.output.with_name(f"run_meta_{args.baseline.lower()}{suffix}.json")
        previous = read_jsonl(args.output) if args.output.is_file() and not args.no_resume else []
        previous_by_id: dict[str, dict[str, Any]] = {}
        for row in previous:
            ident = row.get("interaction_id")
            if ident in expected_ids:
                if ident in previous_by_id:
                    raise ValueError("existing prediction output contains duplicate interaction_id")
                previous_by_id[ident] = row
        run_id = args.run_id
        if not run_id and previous:
            run_id = str(previous[0].get("run_id", "")) or None
        run_id = run_id or f"generation-{args.baseline.lower()}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        agent = None if args.dry_run else TextAgent(config)
        templates = config.get("prompt_templates")
        if not isinstance(templates, dict):
            raise ValueError("generation config needs prompt_templates")
        question_by_id = {row["interaction_id"]: row for row in questions}
        for ident, evidence_row in evidence_rows.items():
            expected_query_hash = query_sha256(question_by_id[ident]["query"])
            if evidence_row["query_sha256"] != expected_query_hash:
                raise ValueError(f"evidence query hash mismatch for {ident}")
        old_requests = read_jsonl(request_path) if request_path.is_file() and not args.no_resume else []
        requests_by_id = {row.get("interaction_id"): row for row in old_requests if row.get("interaction_id") in expected_ids}
        predictions = dict(previous_by_id)
        retries_total = 0
        success_count = 0
        failure_count = 0
        for ident in batch_ids:
            question = question_by_id[ident]
            query = question["query"]
            q_hash = query_sha256(query)
            evidence_row = evidence_rows.get(ident)
            if args.baseline == "B0":
                evidence_status = "not_used"
                evidence_used: list[dict[str, str]] = []
                row_retrieval_hash = None
            elif evidence_row is None:
                evidence_status = "missing"
                evidence_used = []
                row_retrieval_hash = None
            else:
                evidence_status = str(evidence_row["retrieval_status"])
                evidence_used = select_evidence(evidence_row, int(config.get("evidence_token_budget", 1500)))
                row_retrieval_hash = evidence_row.get("retrieval_config_sha256")
            messages = render_messages(config, args.baseline, query, evidence_used)
            p_hash = prompt_sha256(messages)
            request = {"schema_version": SCHEMA_VERSION, "subset": subset, "interaction_id": ident,
                       "dataset_manifest_sha256": manifest_hash, "query_sha256": q_hash,
                       "baseline": args.baseline, "run_id": run_id, "prompt_sha256": p_hash,
                       "messages": messages, "evidence_used": evidence_used}
            cached = predictions.get(ident)
            cache_ok = (not args.no_resume and isinstance(cached, dict)
                        and cached.get("generation_status") == "ok"
                        and cached.get("run_id") == run_id
                        and cached.get("subset") == subset
                        and cached.get("dataset_manifest_sha256") == manifest_hash
                        and cached.get("query_sha256") == q_hash
                        and cached.get("generation_config_sha256") == generation_hash
                        and cached.get("prompt_sha256") == p_hash
                        and cached.get("baseline") == args.baseline
                        and cached.get("provider") == str(config.get("provider", ""))
                        and cached.get("model") == str(config.get("model", ""))
                        and cached.get("retrieval_config_sha256") == row_retrieval_hash)
            cached_request = requests_by_id.get(ident)
            if (cache_ok and isinstance(cached_request, dict)
                    and cached_request.get("prompt_sha256") == p_hash
                    and isinstance(cached_request.get("messages"), list)
                    and prompt_sha256(cached_request["messages"]) == p_hash):
                success_count += cached.get("generation_status") == "ok"
                failure_count += cached.get("generation_status") != "ok"
                continue
            requests_by_id[ident] = request
            write_jsonl(request_path, [requests_by_id[key] for key in batch_ids if key in requests_by_id])
            started_one = time.perf_counter()
            status = "ok"
            response = None
            error_code = None
            usage = {"input_tokens": None, "output_tokens": None}
            if args.baseline == "B1" and evidence_status in {"error", "missing"}:
                status, error_code = "blocked", f"evidence_{evidence_status}"
            elif args.dry_run:
                status, error_code = "error", "dry_run_no_api_call"
            elif agent is None:
                status, error_code = "error", "agent_not_initialized"
            else:
                result, error_code, retries = retry_generate(
                    agent, messages, max_retries=int(config.get("max_retries", 2)),
                    backoff_s=float(config.get("retry_backoff_s", 1.0)))
                retries_total += retries
                if result is None:
                    status = "error"
                else:
                    response = result.response
                    usage = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens}
                    if not response.strip():
                        status, error_code, response = "error", "empty_response", None
            latency = round((time.perf_counter() - started_one) * 1000, 3)
            prediction = {"schema_version": SCHEMA_VERSION, "subset": subset, "interaction_id": ident,
                          "dataset_manifest_sha256": manifest_hash, "query_sha256": q_hash,
                          "baseline": args.baseline, "run_id": run_id, "generation_status": status,
                          "agent_response": response, "provider": str(config.get("provider", "unknown")),
                          "model": str(config.get("model", "unconfigured")),
                          "generation_config_sha256": generation_hash,
                          "retrieval_config_sha256": row_retrieval_hash,
                          "evidence_status": evidence_status, "prompt_sha256": p_hash,
                          "usage": usage, "latency_ms": latency, "error_code": error_code}
            predictions[ident] = prediction
            write_jsonl(args.output, [predictions[key] for key in batch_ids if key in predictions])
            if status == "ok":
                success_count += 1
            else:
                failure_count += 1
        rows = [predictions[key] for key in batch_ids if key in predictions]
        if len(rows) != len(batch_ids):
            raise RuntimeError("generation ended without a row for every expected ID")
        write_jsonl(args.output, rows)
        input_hashes = {str(args.manifest.resolve()): manifest_hash,
                        str(args.questions.resolve()): file_sha256(args.questions)}
        if args.baseline == "B1" and args.evidence and args.evidence.is_file():
            input_hashes[str(args.evidence.resolve())] = file_sha256(args.evidence)
        output_hashes = {str(args.output.resolve()): file_sha256(args.output),
                         str(request_path.resolve()): file_sha256(request_path)}
        meta = {"run_id": run_id, "stage": "generation", "subset": subset, "schema_version": SCHEMA_VERSION,
                "baseline": args.baseline, "code_commit": git_commit(), "code_source_sha256": file_sha256(Path(__file__)),
                "input_files_sha256": input_hashes, "output_files_sha256": output_hashes,
                "config": config, "config_sha256": generation_hash, "started_at": started, "finished_at": utc_now(),
                "hardware": hardware(), "N_expected": len(batch_ids),
                "N_success": sum(row["generation_status"] == "ok" for row in rows),
                "N_failed": sum(row["generation_status"] != "ok" for row in rows),
                "retries": retries_total, "peak_memory_mb": None,
                "batch_ids": batch_ids if args.batch_ids else None,
                "provider_credentials_configured": bool(agent and agent.credential_configured()) if agent else False,
                "dry_run": args.dry_run}
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if not failure_count else 2
    except (OSError, ValueError, ContractError, KeyError, TypeError) as exc:
        print(f"generate error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
