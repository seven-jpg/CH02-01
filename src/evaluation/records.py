"""Offline request audit and reproducible merges; never contact a provider."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.contracts.m3 import ContractError, config_sha256, file_sha256, load_json
from src.evaluation.inputs import Inputs, relative
from src.evaluation.score import (ROOT, cache_key, csv_text, load_tokenizer, local_settings,
    official_check, parse_result, read_rows, score_row, summary, truncate, validate_config, write_new)


def audit_requests(journals: list[Path], *, root: Path = ROOT) -> dict[str, Any]:
    """Count distinct logged attempts, including failures and cross-journal repeats.

    The attempt identity includes its original start time. Copying an identical
    event between journals does not prove another network request or another bill.
    """
    attempts, seen, duplicates = {}, {}, 0
    for path in journals:
        for event in read_rows(path):
            kind = event.get("event")
            fields = ("run_id", "key", "started_at", "evaluation_config_sha256")
            if kind not in ("started", "completed", "failed") or any(
                    not isinstance(event.get(k), str) or not event[k] for k in fields):
                raise ContractError("Invalid judge journal event")
            ident = tuple(event[k] for k in fields[:3])
            event_id = (ident, kind)
            if event_id in seen:
                if seen[event_id] != event:
                    raise ContractError("Conflicting duplicate judge journal event")
                duplicates += 1
                continue
            seen[event_id] = event
            entry = attempts.setdefault(ident, {})
            if kind != "started" and any(k in entry for k in ("completed", "failed")):
                raise ContractError("Multiple terminal events for one judge attempt")
            entry[kind] = event
    rows = []
    for ident, entry in attempts.items():
        if "started" not in entry:
            raise ContractError("Judge terminal event has no logged start")
        start = entry["started"]
        end = entry.get("completed") or entry.get("failed")
        if end and end["evaluation_config_sha256"] != start["evaluation_config_sha256"]:
            raise ContractError("Judge attempt method changed within its journal")
        if end and end["event"] == "completed":
            if parse_result(end.get("content"), end.get("finish_reason")) != end.get("verdict"):
                raise ContractError("Invalid completed judge result in journal")
        usage = end.get("usage") if end else None
        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        if tokens is not None and (type(tokens) is not int or tokens < 0):
            raise ContractError("Invalid provider token usage")
        rows.append({"run_id":ident[0], "key":ident[1], "started_at":ident[2],
            "evaluation_config_sha256":start["evaluation_config_sha256"],
            "outcome":end["event"] if end else "incomplete", "total_tokens":tokens,
            "error_code":end.get("error_code") if end else None,
            "finish_reason":end.get("finish_reason") if end else None})
    rows.sort(key=lambda r: (r["started_at"], r["run_id"], r["key"]))
    by_key = defaultdict(list)
    for row in rows:
        by_key[row["key"]].append(row)
    repeats = [{"key":key,"N_attempts":len(items),"attempts":items,
                "sent_again_after_failure_or_incomplete":any(
                    r["outcome"] in ("failed", "incomplete") for r in items[:-1])}
               for key, items in sorted(by_key.items()) if len(items) > 1]
    known = [r["total_tokens"] for r in rows if r["total_tokens"] is not None]
    return {"kind":"offline_judge_request_audit", "real_api_requests_by_this_tool":0,
        "authorization_verified":False,
        "scope":"All distinct logged attempts in supplied journals, including unsuccessful and unselected attempts",
        "N_started":len(rows), "N_unique_inputs":len(by_key),
        "by_run":dict(sorted(Counter(r["run_id"] for r in rows).items())),
        "by_outcome":dict(sorted(Counter(r["outcome"] for r in rows).items())),
        "N_usage_known":len(known), "N_usage_unknown":len(rows)-len(known),
        "known_total_tokens":sum(known),
        "provider_reported_total_tokens":sum(known) if len(known)==len(rows) else None,
        "currency_cost":None, "N_identical_copied_events":duplicates,
        "repeated_inputs":repeats, "attempts":rows,
        "journal_files_sha256":{relative(p,root):file_sha256(p) for p in journals},
        "note":"A journal records attempted requests, not independent proof of provider billing. No automatic retry does not mean no cross-run repeated requests."}


def _check_hashes(directory: Path, meta: dict[str, Any], root: Path) -> None:
    for field in ("input_files_sha256", "output_files_sha256"):
        mapping = meta.get(field)
        if not isinstance(mapping, dict) or not mapping:
            raise ContractError("Source run has no input/output hashes")
        for name, digest in mapping.items():
            path = (directory / name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or file_sha256(path) != digest:
                raise ContractError("Source hash mismatch or source dependency outside project")


def merge_evaluations(paths: dict[str, Path], config_path: Path, sources: list[Path],
                      journals: list[Path], output: Path, run_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Merge full-subset results, verifying inputs, tokenizer and saved judge responses.

    Corrections may overlap. Success beats failure; conflicting successful labels
    stop the merge. Equal successes use source order; all-failed IDs use the last
    supplied source. Existing artifacts are never rewritten.
    """
    root, output = root.resolve(), output.resolve()
    sources = [p.resolve() for p in sources]
    all_paths = [*paths.values(), config_path, *sources, *journals, output]
    if any(not p.resolve().is_relative_to(root) for p in all_paths):
        raise ContractError("Portable merge inputs and output must stay inside project")
    if not run_id.strip() or any(c in run_id for c in "/\\") or not sources or not journals:
        raise ContractError("Merge requires a valid run ID, source directories and journals")
    if len(set(sources)) != len(sources) or output in sources:
        raise ContractError("Repeated source directory or output/source collision")
    config = load_json(config_path)
    validate_config(config)
    config_hash = config_sha256(config)
    data = Inputs(dict(paths))
    data.provenance()
    tokenizer = load_tokenizer(local_settings(config))
    generated = [i for i in data.ids if data.rows["predictions"][i]["generation_status"] == "ok"]
    texts = dict(zip(generated, truncate(tokenizer, [data.rows["predictions"][i]["agent_response"] for i in generated])))
    audit = audit_requests(journals, root=root)
    completed = defaultdict(list)
    for journal in journals:
        for event in read_rows(journal):
            if event["event"] == "completed":
                completed[event["key"]].append(event)
    candidates, source_records, input_files, simulation = defaultdict(list), [], dict(data.paths), set()
    input_files["evaluation_config"] = config_path
    for n, directory in enumerate(sources):
        suffix = data.baseline.lower()
        meta_path = directory / ("run_meta_eval_" + suffix + ".json")
        score_path = directory / ("scores_" + suffix + ".jsonl")
        meta, rows = load_json(meta_path), read_rows(score_path)
        _check_hashes(directory, meta, root)
        if (meta.get("stage") != "evaluation" or meta.get("schema_version") != "m3.v1"
                or meta.get("subset") != data.subset or meta.get("baseline") != data.baseline
                or meta.get("source_generation_run_id") != data.generation_run_id
                or meta.get("config") != config or meta.get("config_sha256") != config_hash
                or meta.get("run_id") == run_id):
            raise ContractError("Source evaluation method or identity mismatch")
        if meta["output_files_sha256"].get(score_path.name) != file_sha256(score_path):
            raise ContractError("Source scores are not covered by run output hashes")
        ids = [r["interaction_id"] for r in rows]
        expected = meta.get("batch_ids")
        expected = data.ids if expected is None else expected
        if (not isinstance(expected, list) or len(set(expected)) != len(expected)
                or len(ids) != len(set(ids)) or set(ids) != set(expected) or not set(ids).issubset(data.ids)):
            raise ContractError("Source score/batch coverage mismatch")
        for field, value in (("N_expected",len(rows)), ("N_success",sum(r["judge_status"]=="ok" for r in rows)),
                             ("N_failed",sum(r["judge_status"]!="ok" for r in rows))):
            if type(meta.get(field)) is not int or meta[field] != value:
                raise ContractError("Source evaluation counts mismatch")
        simulation.add(bool(meta.get("is_simulated",False)))
        for row in rows:
            data.validate(row,"scores")
            i = row["interaction_id"]
            if (row["run_id"] != meta["run_id"] or row["source_generation_run_id"] != data.generation_run_id
                    or row["baseline"] != data.baseline or row["evaluation_config_sha256"] != config_hash
                    or row["dataset_manifest_sha256"] != data.manifest_hash or row["subset"] != data.subset
                    or row["agent_response_scored"] != texts.get(i)):
                raise ContractError("Source score identity or official truncation mismatch")
            result = {"error_code":row["error_code"]} if row["judge_status"]=="error" else None
            if row["judge_status"]=="ok" and row["scoring_method"]=="llm":
                key = cache_key(data.manifest_hash,i,data.rows["questions"][i]["query"],
                    data.rows["answers"][i]["ground_truth"],texts[i],config)
                result = next((e for e in completed[key] if e["evaluation_config_sha256"]==config_hash
                               and e["content"]==row["judge_reason"] and e["verdict"]==row["verdict"]),None)
                if result is None:
                    raise ContractError("Successful semantic score lacks matching saved judge response")
            expected_row = score_row(data.rows["predictions"][i],texts.get(i),
                data.rows["answers"][i]["ground_truth"],config,meta["run_id"],result)
            if expected_row != row:
                raise ContractError("Source score differs from saved response or deterministic rules")
            candidates[i].append((n,row))
        source_records.append({"directory":relative(directory,output),"run_id":meta["run_id"],
            "scores_sha256":file_sha256(score_path),"run_meta_sha256":file_sha256(meta_path),
            "code_files_sha256":meta.get("code_files_sha256",{})})
        input_files[f"source_meta_{n}"], input_files[f"source_scores_{n}"] = meta_path, score_path
    if len(simulation)!=1 or set(candidates)!=set(data.ids):
        raise ContractError("Merge mixes simulation/real data or does not cover the full subset")
    selected, rows = {}, []
    for i in data.ids:
        successful = [(n,r) for n,r in candidates[i] if r["judge_status"]=="ok"]
        if len({r["verdict"] for _,r in successful}) > 1:
            raise ContractError("Conflicting successful verdicts require review; merge stopped")
        n,row = successful[0] if successful else candidates[i][-1]
        selected[i] = {"source_index":n,"source_run_id":row["run_id"]}
        rows.append({**row,"run_id":run_id})
    stats = summary(rows,list(data.rows["predictions"].values()),subset=data.subset,
                    baseline=data.baseline,manifest=data.manifest_hash)
    record = {"run_id":run_id,"operation":"offline_merge", "real_api_requests":0,
        "selection_policy":"success over failure; conflicting successful verdicts stop; first successful or last unsuccessful source in supplied order",
        "sources":source_records,"selected_source_by_interaction_id":selected,
        "source_request_audit_scope":audit["scope"]}
    # Validate everything before creating output artifacts. Persistent lock files
    # are retained; no deletion or moving is needed for successful or failed runs.
    from scripts.evaluate import exclusive
    from datetime import datetime, timezone
    with exclusive(output / "merge.lock"):
        names = ["scores_"+data.baseline.lower()+".jsonl","summary.csv","official_check.json",
                 "merge_record.json","request_audit.json","run_meta_eval_"+data.baseline.lower()+".json"]
        if any((output/name).exists() for name in names):
            raise ContractError("Merge output already exists; choose a new directory")
        write_new(output/names[0],rows,jsonl=True)
        with (output/"summary.csv").open("x",encoding="utf-8",newline="") as stream:
            stream.write(csv_text([stats]))
        write_new(output/"official_check.json",official_check(rows,data.rows["answers"]))
        write_new(output/"merge_record.json",record)
        write_new(output/"request_audit.json",audit)
        input_files.update({f"journal_{n}":p for n,p in enumerate(journals)})
        now = datetime.now(timezone.utc).isoformat()
        meta = {"run_id":run_id,"stage":"evaluation","schema_version":"m3.v1", "subset":data.subset,
            "baseline":data.baseline,"source_generation_run_id":data.generation_run_id,
            "code_commit":"working tree; actual merger and source code hashes recorded",
            "code_files_sha256":{relative(ROOT/p,ROOT):file_sha256(ROOT/p) for p in (
                "scripts/evaluation_records.py","src/evaluation/records.py","src/evaluation/score.py",
                "src/evaluation/inputs.py","src/contracts/m3.py")},
            "config":config,"config_sha256":config_hash,"started_at":now,"finished_at":now,
            "hardware":{"platform":"offline merge","gpu":None,"ram_mb":None},"peak_memory_mb":None,
            "N_expected":len(rows),"N_success":stats["N_scored"],"N_failed":len(rows)-stats["N_scored"],
            "retries":0,"batch_ids":None,"is_simulated":simulation.pop(),
            "api_requests_total_for_run":0,"operation":"offline_merge",
            "usage":{"responses_with_known_usage":0,"responses_with_unknown_usage":0,"provider_reported_total_tokens":0},
            "input_files_sha256":{relative(p,output):file_sha256(p) for p in input_files.values()},
            "output_files_sha256":{name:file_sha256(output/name) for name in names[:-1]}}
        write_new(output/names[-1],meta)
    return stats
