#!/usr/bin/env python3
"""E: independent m3.v1 scoring. Default blocks paid API; --dry-run is fully offline."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("questions", "answers", "metadata", "manifest", "predictions", "output-dir"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--config", default="experiments/m3/evaluation.json")
    p.add_argument("--batch-ids")
    p.add_argument("--generation-run-meta")
    p.add_argument("--run-id", required=True, help="Unique evaluation identity; use the same ID for resume")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-paid-api", action="store_true")
    p.add_argument("--max-api-requests", type=int)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--cache", help="Shared append-only judge response journal, relative to repository root")
    return p


@contextmanager
def exclusive(path):
    """Persistent OS lock file, with automatic release and no file deletion/moving."""
    from src.contracts.m3 import ContractError
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ContractError("Evaluation output/cache is already in use") from None
        yield
    finally:
        stream.close()


def execute(args):
    from src.contracts.m3 import ContractError, config_sha256, file_sha256, load_json
    from src.evaluation.inputs import Inputs, relative, resolve
    from src.evaluation.score import (Judge, cache_key, csv_text, deterministic, load_tokenizer,
        local_settings, messages, official_check, read_rows, score_row, summary, truncate,
        validate_config, write_new, append_event)
    if args.dry_run and args.allow_paid_api:
        raise ContractError("--dry-run cannot be combined with --allow-paid-api")
    if not args.dry_run and (not args.allow_paid_api or args.max_api_requests is None or args.max_api_requests < 1):
        raise ContractError("Paid scoring requires --allow-paid-api and a positive --max-api-requests; use --dry-run first")
    if not args.run_id.strip() or any(c in args.run_id for c in "/\\"):
        raise ContractError("run-id must be a nonempty identifier")
    config_path = resolve(args.config)
    config = load_json(config_path)
    validate_config(config)
    paths = {name: resolve(getattr(args, name)) for name in ("questions", "answers", "metadata", "manifest", "predictions")}
    data = Inputs(paths, resolve(args.batch_ids) if args.batch_ids else None)
    provenance = data.provenance(resolve(args.generation_run_meta) if args.generation_run_meta else None)
    settings = local_settings(config)
    tokenizer = load_tokenizer(settings)
    generated = [i for i in data.ids if data.rows["predictions"][i]["generation_status"] == "ok"]
    scored_text = dict(zip(generated, truncate(tokenizer, [data.rows["predictions"][i]["agent_response"] for i in generated])))
    if any(not text.strip() for text in scored_text.values()):
        raise ContractError("Response becomes empty after official truncation; m3.v1 successful scores require nonempty text. Ask A to resolve before scoring")
    output = resolve(args.output_dir)
    cache = resolve(args.cache) if args.cache else output / "judge_journal.jsonl"
    # All output/control paths must be distinct from inputs and from one another.
    protected = {p.resolve() for p in paths.values()} | {config_path.resolve(), (ROOT / ".env").resolve(), resolve(settings["RESPONSE_TOKENIZER_PATH"])}
    names = ("run_identity.json", "precheck.json", "pending_judge.jsonl", "prepared.jsonl", "deterministic.jsonl",
             "provenance.json", "progress.jsonl", "official_check.json", "summary.csv", "run_meta_eval_" + data.baseline.lower() + ".json",
             "scores_" + data.baseline.lower() + ".jsonl")
    targets = {output / name for name in names} | {cache, cache.with_name(cache.name + ".lock"), output / "evaluation.lock"}
    if targets & protected or cache.parent == output and cache.name in names:
        raise ContractError("Output/cache would overwrite an input or reserved artifact")
    identity = {"run_id": args.run_id, "dry_run": args.dry_run, "input_hashes": data.hashes,
                "input_paths": {name: relative(p, ROOT) for name, p in paths.items()},
                "config_sha256": config_sha256(config), "cache": relative(cache, ROOT),
                "evaluation_source_sha256": {relative(p, ROOT): file_sha256(p) for p in
                    (Path(__file__), ROOT / "src/evaluation/score.py", ROOT / "src/evaluation/inputs.py", ROOT / "src/contracts/m3.py")}}
    with exclusive(output / "evaluation.lock"), exclusive(cache.with_name(cache.name + ".lock")):
        identity_path = output / "run_identity.json"
        if identity_path.exists():
            if not args.resume or load_json(identity_path) != identity:
                raise ContractError("Existing run differs or --resume is missing; use a new output directory/run ID")
        else:
            if args.resume:
                raise ContractError("No matching run identity to resume")
            if any((output / name).exists() for name in names):
                raise ContractError("Output directory has existing artifacts; use a new directory")
            write_new(identity_path, identity)
        judge = Judge(config, settings, cache, args.run_id, allow_paid=args.allow_paid_api, max_requests=args.max_api_requests)
        prepared, pending, direct = [], [], []
        for i in data.ids:
            p, q, a = (data.rows[k][i] for k in ("predictions", "questions", "answers"))
            text = scored_text.get(i)
            item = {"interaction_id": i, "subset": data.subset, "baseline": data.baseline,
                    "dataset_manifest_sha256": data.manifest_hash, "evaluation_config_sha256": config_sha256(config),
                    "source_generation_run_id": p["run_id"], "query": q["query"], "ground_truth": a["ground_truth"],
                    "agent_response": p["agent_response"], "agent_response_scored": text,
                    "generation_status": p["generation_status"], "rule": None, "judge_key": None}
            if p["generation_status"] == "ok":
                rule = deterministic(text, a["ground_truth"])
                if rule:
                    item["rule"] = rule[1]
                    direct.append({**item, "verdict": rule[0]})
                else:
                    item["judge_key"] = cache_key(data.manifest_hash, i, q["query"], a["ground_truth"], text, config)
                    request = messages(config, q["query"], a["ground_truth"], text)
                    pending.append({**item, "messages": request,
                                    "prompt_characters": sum(len(m["content"]) for m in request),
                                    "prompt_utf8_bytes": sum(len(m["content"].encode("utf-8")) for m in request),
                                    "max_output_tokens": config["max_tokens"], "billing_tokens": None})
            prepared.append(item)
        unique = {item["judge_key"] for item in pending}
        reused = sum(bool(judge.cached(k)) and not judge.cached(k).get("error_code") for k in unique)
        precheck = {"kind": "offline_precheck" if args.dry_run else "paid_run_precheck",
                    "is_formal_result": False, "subset": data.subset, "baseline": data.baseline,
                    "N_fixed": len(data.ids), "N_generated": len(generated), "N_deterministic": len(direct),
                    "N_missing": sum(r["verdict"] == "MISSING" for r in direct),
                    "N_exact_match": sum(r["verdict"] == "CORRECT" for r in direct),
                    "N_pending_judge": len(pending), "N_unique_judge_inputs": len(unique),
                    "N_reusable_cached_responses": reused,
                    "new_requests_needed": sum(judge.cached(k) is None for k in unique),
                    "N_previous_attempts_requiring_review": sum(bool(judge.cached(k)) and bool(judge.cached(k).get("error_code")) for k in unique),
                    "real_api_requests": 0, "evaluation_config_sha256": config_sha256(config),
                    "judge": {k: config[k] for k in ("judge_provider", "judge_base_url", "judge_model", "max_tokens")},
                    "billing_note": "Character/UTF-8 counts only; provider tokens and prices unknown until actual usage is returned."}
        for name, value, lines in (("precheck.json", precheck, False), ("prepared.jsonl", prepared, True),
                                   ("pending_judge.jsonl", pending, True), ("deterministic.jsonl", direct, True),
                                   ("provenance.json", provenance, False)):
            path = output / name
            if path.exists():
                old = read_rows(path) if lines else load_json(path)
                # Cache availability may legitimately increase on resume; never rewrite the original snapshot.
                if name != "precheck.json" and old != value:
                    raise ContractError("Existing prepared artifact differs from this run")
            else:
                write_new(path, value, jsonl=lines)
        if args.dry_run:
            print(__import__("json").dumps(precheck, ensure_ascii=False))
            return 0
        started = datetime.now(timezone.utc).isoformat()
        meta_path = output / ("run_meta_eval_" + data.baseline.lower() + ".json")
        if meta_path.exists():
            meta = load_json(meta_path)
            for name, digest in meta["output_files_sha256"].items():
                if file_sha256((output / name).resolve()) != digest:
                    raise ContractError("Completed run output hash mismatch")
            return 0 if meta["N_failed"] == 0 else 2
        progress_path = output / "progress.jsonl"
        progress = read_rows(progress_path) if progress_path.exists() else []
        done = {r["interaction_id"]: r for r in progress}
        if len(done) != len(progress) or not set(done).issubset(data.ids):
            raise ContractError("Invalid progress journal IDs")
        pending_map = {r["interaction_id"]: r for r in pending}
        rows = []
        for item in prepared:
            i = item["interaction_id"]
            p, a = data.rows["predictions"][i], data.rows["answers"][i]
            if i in done:
                row = done[i]
                data.validate(row, "scores")
                if any(row[k] != v for k, v in (("run_id", args.run_id), ("source_generation_run_id", p["run_id"]),
                        ("agent_response_scored", item["agent_response_scored"]), ("baseline", data.baseline),
                        ("evaluation_config_sha256", config_sha256(config)), ("dataset_manifest_sha256", data.manifest_hash))):
                    raise ContractError("Progress journal source/method mismatch")
                if row["judge_status"] == "ok" or row["scoring_method"] == "unscored":
                    result = judge.cached(item["judge_key"]) if item["judge_key"] else None
                    expected_row = score_row(p, item["agent_response_scored"], a["ground_truth"], config, args.run_id, result)
                    if row != expected_row:
                        raise ContractError("Progress journal verdict differs from deterministic rules or saved judge response")
            else:
                result = judge.evaluate(item["judge_key"], pending_map[i]["messages"]) if item["judge_key"] else None
                row = score_row(p, item["agent_response_scored"], a["ground_truth"], config, args.run_id, result)
                data.validate(row, "scores")
                append_event(progress_path, row)
            rows.append(row)
        stats = summary(rows, list(data.rows["predictions"].values()), subset=data.subset,
                        baseline=data.baseline, manifest=data.manifest_hash, batch_hash=data.batch_hash)
        final = {"scores_" + data.baseline.lower() + ".jsonl": rows,
                 "official_check.json": official_check(rows, data.rows["answers"])}
        for name, value in final.items():
            path = output / name
            if path.exists():
                old = read_rows(path) if name.endswith("jsonl") else load_json(path)
                if old != value:
                    raise ContractError("Partial finalization artifact mismatch")
            else:
                write_new(path, value, jsonl=name.endswith("jsonl"))
        csv_path = output / "summary.csv"
        content = csv_text([stats])
        if csv_path.exists():
            if csv_path.read_text(encoding="utf-8") != content.replace("\r\n", "\n"):
                raise ContractError("Partial summary mismatch")
        else:
            with csv_path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
        outputs = [output / name for name in final] + [csv_path, progress_path]
        meta = {"run_id": args.run_id, "stage": "evaluation", "schema_version": "m3.v1", "subset": data.subset,
                "baseline": data.baseline, "source_generation_run_id": data.generation_run_id,
                "code_commit": "uncommitted E implementation; see source hashes", "code_files_sha256": identity["evaluation_source_sha256"],
                "config": config, "config_sha256": config_sha256(config),
                "input_files_sha256": {relative(p, output): file_sha256(p) for p in list(paths.values()) + [config_path]},
                "output_files_sha256": {relative(p, output): file_sha256(p) for p in outputs},
                "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                "hardware": {"platform": platform.system(), "python": platform.python_version(), "ram_mb": None, "gpu": None},
                "N_expected": len(rows), "N_success": stats["N_scored"], "N_failed": len(rows) - stats["N_scored"],
                "retries": 0, "peak_memory_mb": None, "batch_ids": data.ids if args.batch_ids else None,
                "api_requests_total_for_run": judge.used, "judge_journal": relative(cache, output),
                "is_simulated": False}
        from importlib.metadata import version
        meta["runtime_versions"] = {name: version(name) for name in ("tokenizers", "openai", "python-dotenv", "jsonschema", "pandas", "numpy")}
        completions = [e for e in judge.events if e.get("run_id") == args.run_id and e.get("event") in ("completed", "failed")]
        meta["usage"] = {"responses_with_known_usage": sum(e.get("usage") is not None for e in completions),
                         "responses_with_unknown_usage": sum(e.get("usage") is None for e in completions),
                         "provider_reported_total_tokens": sum(e["usage"].get("total_tokens", 0) for e in completions if e.get("usage") is not None) if completions and all(e.get("usage") is not None for e in completions) else None}
        write_new(meta_path, meta)
        print(__import__("json").dumps(stats, ensure_ascii=False))
        return 0 if stats["N_scored"] == len(rows) else 2


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return execute(args)
    except Exception as exc:
        from src.contracts.m3 import ContractError
        # Only our safe contract messages are exposed; SDK/filesystem bodies remain private.
        print("Evaluation stopped: " + (str(exc) if isinstance(exc, ContractError) else type(exc).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
