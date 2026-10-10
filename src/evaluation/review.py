"""Reproducible offline workload, blinded review and completed-score comparisons."""
from __future__ import annotations

import csv
import io
from pathlib import Path
import random
from typing import Any

from src.contracts.m3 import ContractError, file_sha256, load_json
from src.evaluation.score import ROOT, csv_text, paired, read_rows, summary, write_new

INPUT_GROUPS = [
    {"name": "smoke_B0", "subset": "smoke", "baseline": "B0", "top_k": None, "predictions": "results/m3/smoke/predictions_b0.jsonl"},
    {"name": "smoke_B1_k5", "subset": "smoke", "baseline": "B1", "top_k": 5, "predictions": "results/m3/smoke/predictions_b1.jsonl"},
    {"name": "dev_B0", "subset": "dev", "baseline": "B0", "top_k": None, "predictions": "results/m3/dev/predictions_b0.jsonl"},
    {"name": "dev_B1_k1", "subset": "dev", "baseline": "B1", "top_k": 1, "predictions": "results/m3/dev_topk_sweep_run1/top_k_1/predictions_b1.jsonl"},
    {"name": "dev_B1_k3", "subset": "dev", "baseline": "B1", "top_k": 3, "predictions": "results/m3/dev_topk_sweep_run1/top_k_3/predictions_b1.jsonl"},
    {"name": "dev_B1_k5", "subset": "dev", "baseline": "B1", "top_k": 5, "predictions": "results/m3/dev/predictions_b1.jsonl"},
]
COMPARISONS = [("smoke_B0", "smoke_B1_k5"), ("dev_B0", "dev_B1_k5"),
               ("dev_B1_k1", "dev_B1_k3"), ("dev_B1_k1", "dev_B1_k5"), ("dev_B1_k3", "dev_B1_k5")]


def save_once(path: Path, value: Any, *, jsonl: bool = False) -> None:
    if path.exists():
        existing = read_rows(path) if jsonl else load_json(path)
        if existing != value:
            raise ContractError("Existing review artifact differs; use a new output directory")
    else:
        write_new(path, value, jsonl=jsonl)


def save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content.replace("\r\n", "\n"):
            raise ContractError("Existing text artifact differs; use a new output directory")
    else:
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)


def prepare_suite(output: Path, run_prefix: str, *, resume: bool = False) -> dict[str, Any]:
    from scripts.evaluate import main as evaluate_main
    all_prepared, pending, group_counts, outputs = [], [], [], []
    for group in INPUT_GROUPS:
        subset = group["subset"]
        directory = (ROOT / group["predictions"]).parent / run_prefix / group["baseline"].lower()
        args = ["--manifest", "data/processed/m3/manifest.json", "--predictions", group["predictions"],
                "--config", "experiments/m3/evaluation.json", "--output-dir", str(directory),
                "--run-id", run_prefix + "-" + group["name"], "--dry-run"]
        for name in ("questions", "answers", "metadata"):
            args += ["--" + name, f"data/processed/m3/{subset}/{name}.jsonl"]
        if resume:
            args += ["--resume"]
        if evaluate_main(args) != 0:
            raise ContractError("Offline suite stopped: " + group["name"])
        precheck = load_json(directory / "precheck.json")
        group_counts.append({"group": group["name"], "subset": subset, "baseline": group["baseline"], "top_k": group["top_k"],
            **{key: precheck[key] for key in ("N_fixed", "N_generated", "N_missing", "N_exact_match", "N_pending_judge", "N_unique_judge_inputs")},
            "generation_coverage": precheck["N_generated"] / precheck["N_fixed"],
            "rule_refusal_fraction_of_fixed": precheck["N_missing"] / precheck["N_fixed"],
            "accuracy": None, "hallucination_rate": None, "truthfulness": None, "status": "awaiting_semantic_judge"})
        for item in read_rows(directory / "prepared.jsonl"):
            all_prepared.append({**item, "group": group["name"], "prediction_path": group["predictions"]})
        for item in read_rows(directory / "pending_judge.jsonl"):
            pending.append({**item, "group": group["name"], "prediction_path": group["predictions"]})
        outputs.append({"group": group["name"], "directory": directory.relative_to(ROOT).as_posix(),
                        "precheck_sha256": file_sha256(directory / "precheck.json")})
    deduplicated = {}
    for item in pending:
        key = item["judge_key"]
        if key not in deduplicated:
            deduplicated[key] = {"judge_key": key, "messages": item["messages"],
                                "prompt_characters": item["prompt_characters"], "prompt_utf8_bytes": item["prompt_utf8_bytes"],
                                "billing_tokens": None, "max_output_tokens": item["max_output_tokens"], "consumers": []}
        deduplicated[key]["consumers"].append({"group": item["group"], "interaction_id": item["interaction_id"],
                                             "source_generation_run_id": item["source_generation_run_id"]})
    lengths = [item["prompt_characters"] for item in deduplicated.values()]
    suite = {"kind": "offline_workload", "is_formal_result": False, "real_api_requests": 0,
             "N_predictions": len(all_prepared), "N_pending_judge": len(pending), "N_unique_judge_inputs": len(deduplicated),
             "N_within_suite_reusable_responses": len(pending) - len(deduplicated),
             "reuse_reason": "Same manifest/ID/question/reference/scored text and evaluation method; scores keep individual generation provenance.",
             "prompt_characters": {"min": min(lengths) if lengths else None, "max": max(lengths) if lengths else None,
                                   "total_unique": sum(lengths)}, "max_output_tokens_per_request": 1024,
             "provider_billing_tokens": None, "estimated_currency_cost": None,
             "cache_policy": "Share one journal explicitly to realize cross-group savings; starts persisted before send; no retries; unknown/failed requests require review.",
             "groups": group_counts, "outputs": outputs,
             "pending_comparisons": [{"first": a, "second": b, "status": "awaiting_real_judge_results"} for a, b in COMPARISONS]}
    save_once(output / "suite_summary.json", suite)
    save_text(output / "suite_summary.csv", csv_text(group_counts))
    save_once(output / "unique_judge_requests.jsonl", list(deduplicated.values()), jsonl=True)
    blind_review(output, all_prepared)
    return suite


def blind_review(output: Path, all_prepared: list[dict[str, Any]], seed: int = 42) -> None:
    # Sample prediction records, not just question IDs; top-k variants are independent observations.
    rng = random.Random(seed)
    ordered = sorted(all_prepared, key=lambda r: (r["group"], r["interaction_id"]))
    semantic = [r for r in ordered if r["judge_key"]]
    refusals = [r for r in ordered if r["rule"] == "idk"]
    chosen = rng.sample(semantic, min(20, len(semantic))) + rng.sample(refusals, min(10, len(refusals)))
    rng.shuffle(chosen)
    blind, mapping, editable = [], [], []
    for index, item in enumerate(chosen, 1):
        blind_id = f"R{index:03d}"
        visible = {key: item[key] for key in ("query", "ground_truth", "agent_response", "agent_response_scored")}
        blind.append({"blind_id": blind_id, **visible})
        editable.append({"blind_id": blind_id, **visible, "human_verdict": "", "human_reason": "", "reviewer": ""})
        mapping.append({"blind_id": blind_id, **item})
    save_once(output / "blind_review.jsonl", blind, jsonl=True)
    save_once(output / "blind_mapping_private.jsonl", mapping, jsonl=True)
    save_text(output / "human_review.csv", csv_text(editable))
    save_once(output / "review_sampling.json", {"seed": seed, "sampling_unit": "prediction record (group, interaction_id)",
              "procedure": "Sort by group then ID; sample semantic 20, refusals 10 using Random(42), concatenate, shuffle using same RNG.",
              "population": len(all_prepared), "semantic_population": len(semantic), "refusal_population": len(refusals),
              "selected": len(chosen), "selected_semantic": min(20, len(semantic)), "selected_refusals": min(10, len(refusals)),
              "unique_question_ids": len({r["interaction_id"] for r in chosen}),
              "human_completed": 0, "ai_review_is_human": False})
    paragraphs = ["# 人工盲审包\n\n请先独立判断，再查看 AI 建议或身份映射。此文件不包含基线/top-k/机器标签。\n\n"
                  "在 human_review.csv 填写 human_verdict（CORRECT/WRONG/MISSING）、human_reason、reviewer。"
                  "以参考答案为准，判断实际评分文本；原回答用于检查截断影响。不能将未填行计为人工核查。\n"]
    for r in blind:
        paragraphs.append(f"\n## {r['blind_id']}\n\n问题：{r['query']}\n\n参考答案：{r['ground_truth']}\n\n"
                          f"原回答：{r['agent_response']}\n\n评分文本：{r['agent_response_scored']}\n\n人工判断：________  理由：________\n")
    save_text(output / "human_blind_review.md", "".join(paragraphs))


def human_summary(csv_path: Path, mapping_path: Path, judge_paths: list[Path]) -> dict[str, Any]:
    mapping_rows = read_rows(mapping_path)
    mapping = {r["blind_id"]: r for r in mapping_rows}
    if len(mapping) != len(mapping_rows):
        raise ContractError("Duplicate blind mapping ID")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len({r["blind_id"] for r in rows}) != len(rows) or {r["blind_id"] for r in rows} != set(mapping):
        raise ContractError("Human review must retain every blind ID exactly once")
    completed = []
    for row in rows:
        verdict = row["human_verdict"].strip()
        if verdict and verdict not in ("CORRECT", "WRONG", "MISSING"):
            raise ContractError("Invalid human verdict")
        if verdict:
            if not row["reviewer"].strip() or not row["human_reason"].strip():
                raise ContractError("Completed human reviews require reviewer and reason")
            completed.append({**row, "human_verdict": verdict})
    judged = {}
    for path in judge_paths:
        for r in read_rows(path):
            key = (r["source_generation_run_id"], r["interaction_id"])
            if key in judged:
                raise ContractError("Duplicate source in supplied judge scores")
            judged[key] = r
    matched, agree, disagreements = 0, 0, []
    for r in completed:
        source = mapping[r["blind_id"]]
        judge = judged.get((source["source_generation_run_id"], source["interaction_id"]))
        if judge and judge["judge_status"] == "ok":
            if judge["agent_response_scored"] != source["agent_response_scored"]:
                raise ContractError("Manual/judge scored text differs")
            matched += 1
            if judge["verdict"] == r["human_verdict"]:
                agree += 1
            else:
                disagreements.append({"blind_id": r["blind_id"], "human": r["human_verdict"], "judge": judge["verdict"]})
    return {"N_selected": len(rows), "N_human_completed": len(completed), "N_pending_human": len(rows) - len(completed),
            "N_human_judge_paired": matched, "agreement": agree / matched if matched else None,
            "disagreements": disagreements, "ai_suggestions_counted_as_human": False}


def compare_groups(score_paths: dict[str, Path], output: Path) -> dict[str, Any]:
    groups = {g["name"]: g for g in INPUT_GROUPS}
    scores, summaries = {}, []
    for name, path in score_paths.items():
        if name not in groups:
            raise ContractError("Unknown comparison group")
        g = groups[name]
        from src.evaluation.inputs import Inputs
        data = Inputs({"manifest": ROOT / "data/processed/m3/manifest.json",
                       **{k: ROOT / f"data/processed/m3/{g['subset']}/{k}.jsonl" for k in ("questions", "answers", "metadata")},
                       "predictions": ROOT / g["predictions"]})
        pred = read_rows(ROOT / g["predictions"])
        rows = read_rows(path)
        for row in rows:
            data.validate(row, "scores")
        if len({r["evaluation_config_sha256"] for r in rows}) != 1:
            raise ContractError("Comparison contains mixed evaluation configs")
        if any(r["baseline"] != g["baseline"] or r["source_generation_run_id"] != pred[0]["run_id"] for r in rows):
            raise ContractError("Comparison score provenance mismatch")
        scores[name] = rows
        summaries.append({"group": name, **summary(rows, pred, subset=g["subset"], baseline=g["baseline"],
                                                    manifest=pred[0]["dataset_manifest_sha256"])})
    comparisons = [{"first": a, "second": b, **paired(scores[a], scores[b])} for a, b in COMPARISONS if a in scores and b in scores]
    result = {"groups": summaries, "paired": comparisons}
    save_once(output / "completed_comparisons.json", result)
    save_text(output / "completed_summary.csv", csv_text(summaries))
    return result
