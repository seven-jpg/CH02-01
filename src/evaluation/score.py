"""Official text rules, guarded judge requests, durable response cache and metrics.

Only the two pure reference files are loaded, never the official package initializer.
The cache is an append-only journal: an interrupted request is never resent implicitly.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib.util
import io
import os
from pathlib import Path
import re
import time
from typing import Any

from src.contracts.m3 import (ContractError, RESPONSE_TOKENIZER, canonical_json,
                              config_sha256, file_sha256, load_json, parse_json,
                              query_sha256)

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL = ROOT / "external/CRAG-MM/evaluation"
TOKENIZER_SHA256 = "79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4"
USER_TEMPLATE = ("Your task is to judge if the prediction is correct or not based on the ground truth answer. Now your turn:\n\n"
                 "Question: {query}\nGround Truth: {ground_truth}\nPrediction: {agent_response}\nGive your output below:\n")
RULES_VERSION = "e-m3-1-idk-first-strict-result-no-retry"


def pure_reference(name: str) -> Any:
    spec = importlib.util.spec_from_file_location("_e_reference_" + name, OFFICIAL / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reference_hashes() -> dict[str, str]:
    return {str(path.relative_to(ROOT)).replace(os.sep, "/"): file_sha256(path)
            for path in (OFFICIAL / (name + ".py") for name in
                         ("evaluator", "llm_judge", "evaluation_prompt", "evaluation_utils", "config", "dataset_utils"))}


def make_config() -> dict[str, Any]:
    prompt = pure_reference("evaluation_prompt").CRAGMultiModalPrompts()
    return {"schema_version": "m3.v1", "judge_provider": "autodl",
            "judge_base_url": "https://www.autodl.art/api/v1", "judge_model": "DeepSeek-V4.1-Flash",
            "judge_revision": None, "temperature": 0, "max_tokens": 1024, "timeout_s": 120,
            "max_retries": 0, "response_tokenizer": RESPONSE_TOKENIZER, "response_max_tokens": 75,
            "tokenizer_sha256": TOKENIZER_SHA256, "rules_version": RULES_VERSION,
            "reference_sources_sha256": reference_hashes(),
            "prompt_templates": {"system": prompt.get_instructions() + "\n\n" + prompt.get_in_context_examples(),
                                 "user": USER_TEMPLATE},
            "adaptation": "Official prompts/tokenizer and binary rules; third-party DeepSeek judge; strict parsing and explicit technical failures."}


def validate_config(config: dict[str, Any]) -> None:
    # The complete effective method is committed and hashed, including literal prompts.
    if config != make_config():
        raise ContractError("Evaluation config differs from the reviewed method/reference files; create and review a new method version")


def local_settings(config: dict[str, Any], *, root: Path = ROOT) -> dict[str, str]:
    from dotenv import dotenv_values
    values = dotenv_values(root / ".env", interpolate=False)
    names = ("JUDGE_PROVIDER", "JUDGE_API_KEY", "JUDGE_BASE_URL", "JUDGE_MODEL",
             "RESPONSE_TOKENIZER_PATH", "RESPONSE_TOKENIZER_SHA256")
    result = {key: os.environ.get(key, values.get(key) or "") for key in names}
    for env, field in (("JUDGE_PROVIDER", "judge_provider"), ("JUDGE_BASE_URL", "judge_base_url"),
                       ("JUDGE_MODEL", "judge_model"), ("RESPONSE_TOKENIZER_SHA256", "tokenizer_sha256")):
        if result[env] and result[env] != config[field]:
            raise ContractError(f"Effective {env} conflicts with evaluation config")
        result[env] = config[field]
    result["RESPONSE_TOKENIZER_PATH"] = result["RESPONSE_TOKENIZER_PATH"] or ".cache/tokenizers/llama-3.2-1b-instruct/tokenizer.json"
    return result


def load_tokenizer(settings: dict[str, str], *, root: Path = ROOT) -> Any:
    from tokenizers import Tokenizer
    path = Path(settings["RESPONSE_TOKENIZER_PATH"])
    if not path.is_absolute():
        path = root / path
    if not path.is_file() or file_sha256(path) != TOKENIZER_SHA256:
        raise ContractError("Tokenizer missing or SHA256 mismatch; no download or fallback is permitted")
    try:
        tokenizer = Tokenizer.from_file(str(path))
        tokenizer.enable_truncation(max_length=75)
        return tokenizer
    except Exception:
        raise ContractError("Verified tokenizer could not be loaded") from None


def truncate(tokenizer: Any, responses: list[str]) -> list[str]:
    return [tokenizer.decode(enc.ids) for enc in tokenizer.encode_batch(responses)]


def is_missing(text: str) -> bool:
    cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower())
    return "i dont know" in cleaned or "i do not know" in cleaned


def deterministic(text: str, truth: str) -> tuple[str, str] | None:
    if is_missing(text):
        return "MISSING", "idk"
    if text.strip().lower() == truth.strip().lower():
        return "CORRECT", "exact_match"
    return None


def messages(config: dict[str, Any], query: str, truth: str, text: str) -> list[dict[str, str]]:
    templates = config["prompt_templates"]
    return [{"role": "system", "content": templates["system"]},
            {"role": "user", "content": templates["user"].format(query=query, ground_truth=truth, agent_response=text)}]


def cache_key(manifest: str, ident: str, query: str, truth: str, text: str, config: dict[str, Any]) -> str:
    # Groups are deliberately absent; identical actual judge inputs may share a response.
    return query_sha256(canonical_json({"manifest": manifest, "interaction_id": ident,
        "query": query, "ground_truth": truth, "agent_response_scored": text,
        "evaluation_config_sha256": config_sha256(config)}))


def parse_result(content: str, finish_reason: str = "stop") -> str:
    if finish_reason != "stop" or not isinstance(content, str) or not content.strip():
        raise ContractError("judge_incomplete_response")
    lines = content.strip().splitlines()
    matches = re.findall(r"(?m)^\s*Result:\s*(CORRECT|WRONG)\s*$", content)
    final = re.fullmatch(r"\s*Result:\s*(CORRECT|WRONG)\s*", lines[-1])
    if not final or not matches or len(set(matches)) != 1:
        raise ContractError("judge_invalid_result")
    # Reject conflicting inline/malformed result claims as well as conflicting full lines.
    claims = re.findall(r"Result:\s*(CORRECT|WRONG)", content)
    if set(claims) != {final.group(1)}:
        raise ContractError("judge_conflicting_result")
    return final.group(1)


def read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise ContractError("JSONL file cannot be read as UTF-8") from None
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            raise ContractError(f"Blank JSONL line {number}")
        row = parse_json(line)
        if not isinstance(row, dict):
            raise ContractError(f"JSONL line {number} must be an object")
        rows.append(row)
    return rows


def write_new(path: Path, value: Any, *, jsonl: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ("".join(canonical_json(row) + "\n" for row in value) if jsonl
            else canonical_json(value) + "\n")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(event) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    return value


class Judge:
    """Sequential requests with SDK retries disabled and durable start-before-send logging.

    The CLI holds an operating-system lock on the journal during evaluation.
    A crash releases that lock; unfinished request entries still block resending.
    """
    def __init__(self, config: dict[str, Any], settings: dict[str, str], journal: Path,
                 run_id: str, *, allow_paid: bool = False, max_requests: int | None = None,
                 client: Any = None):
        self.config, self.settings, self.journal, self.run_id = config, settings, journal, run_id
        self.allow_paid, self.max_requests, self.client = allow_paid, max_requests, client
        self.events = read_rows(journal) if journal.exists() else []
        self.used = sum(e.get("event") == "started" and e.get("run_id") == run_id for e in self.events)
        self.stopped = False

    def cached(self, key: str) -> dict[str, Any] | None:
        matching = [event for event in self.events if event.get("key") == key]
        for event in reversed(matching):
            if event.get("event") == "completed":
                if event.get("evaluation_config_sha256") != config_sha256(self.config):
                    raise ContractError("Cache method mismatch")
                if parse_result(event.get("content"), event.get("finish_reason")) != event.get("verdict"):
                    raise ContractError("Corrupt cached judge result")
                return event
        if matching:
            return {"error_code": "judge_previous_attempt_requires_review"}
        return None

    def evaluate(self, key: str, request_messages: list[dict[str, str]]) -> dict[str, Any]:
        existing = self.cached(key)
        if existing:
            return {**existing, "cache_hit": True}
        if self.stopped:
            return {"error_code": "judge_run_stopped"}
        if not self.allow_paid or type(self.max_requests) is not int or self.max_requests < 1:
            return {"error_code": "paid_api_disabled"}
        if self.used >= self.max_requests:
            return {"error_code": "judge_request_limit"}
        if self.client is None:
            if not self.settings["JUDGE_API_KEY"]:
                raise ContractError("JUDGE_API_KEY is required only for an authorized paid run")
            from openai import OpenAI
            self.client = OpenAI(api_key=self.settings["JUDGE_API_KEY"], base_url=self.config["judge_base_url"],
                                 max_retries=0, timeout=self.config["timeout_s"])
        start = {"event": "started", "key": key, "run_id": self.run_id,
                 "evaluation_config_sha256": config_sha256(self.config),
                 "started_at": datetime.now(timezone.utc).isoformat(), "attempt_for_run": self.used + 1}
        append_event(self.journal, start)
        self.events.append(start)
        self.used += 1
        began = time.monotonic()
        content, finish, usage = None, None, None
        try:
            response = self.client.chat.completions.create(model=self.config["judge_model"], messages=request_messages,
                      temperature=self.config["temperature"], max_tokens=self.config["max_tokens"])
            choice = response.choices[0]
            content, finish = choice.message.content, choice.finish_reason
            usage = response.usage.model_dump() if response.usage is not None else None
            verdict = parse_result(content, finish)
            event = redact({**start, "event": "completed", "content": content,
                            "finish_reason": finish, "verdict": verdict, "usage": usage,
                            "response_id": getattr(response, "id", None)}, (self.settings["JUDGE_API_KEY"],))
        except Exception as exc:
            # Exception strings and provider bodies can include credentials. Never persist them.
            code = str(exc) if isinstance(exc, ContractError) else "judge_request_or_structure_error"
            event = redact({**start, "event": "failed", "error_code": code,
                            "content": content, "finish_reason": finish, "usage": usage},
                           (self.settings["JUDGE_API_KEY"],))
            self.stopped = True
        event.update(finished_at=datetime.now(timezone.utc).isoformat(), latency_ms=(time.monotonic() - began) * 1000)
        append_event(self.journal, event)
        self.events.append(event)
        return {**event, "cache_hit": False}


def score_row(prediction: dict[str, Any], text: str | None, truth: str,
              config: dict[str, Any], run_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {key: prediction[key] for key in ("schema_version", "subset", "interaction_id", "dataset_manifest_sha256", "baseline")}
    row.update(run_id=run_id, source_generation_run_id=prediction["run_id"], judge_status="ok",
               verdict=None, score=None, agent_response_scored=text, scoring_method="unscored",
               judge_model=None, evaluation_config_sha256=config_sha256(config),
               response_tokenizer=RESPONSE_TOKENIZER, response_max_tokens=75, judge_reason=None, error_code=None)
    if prediction["generation_status"] != "ok":
        row.update(judge_status="unscored", error_code="generation_" + prediction["generation_status"])
        return row
    direct = deterministic(text, truth)
    if direct:
        row.update(verdict=direct[0], scoring_method=direct[1])
    else:
        row.update(scoring_method="llm", judge_model=config["judge_model"])
        if result is None or result.get("error_code"):
            row.update(judge_status="error", error_code=(result or {}).get("error_code", "judge_result_missing"))
            return row
        row.update(verdict=result["verdict"], judge_reason=result["content"])
    row["score"] = {"CORRECT": 1, "WRONG": -1, "MISSING": 0}[row["verdict"]]
    return row


def summary(rows: list[dict[str, Any]], predictions: list[dict[str, Any]], *, subset: str,
            baseline: str, manifest: str, batch_hash: str | None = None) -> dict[str, Any]:
    ids = [row["interaction_id"] for row in rows]
    if len({p["interaction_id"] for p in predictions}) != len(predictions) or len(set(ids)) != len(ids) or set(ids) != {p["interaction_id"] for p in predictions}:
        raise ContractError("Summary requires one score per expected prediction; merge batches by ID first")
    if any(r["subset"] != subset or r["baseline"] != baseline or r["dataset_manifest_sha256"] != manifest for r in rows):
        raise ContractError("Summary rows have mixed data/baseline identities")
    fixed = len(predictions)
    generated = sum(p["generation_status"] == "ok" for p in predictions)
    counts = {label: sum(r["judge_status"] == "ok" and r["verdict"] == label for r in rows)
              for label in ("CORRECT", "WRONG", "MISSING")}
    c, w, m = (counts[label] for label in ("CORRECT", "WRONG", "MISSING"))
    n = c + w + m
    return {"scope": "batch" if batch_hash else "full", "batch_ids_sha256": batch_hash,
            "subset": subset, "baseline": baseline, "manifest_sha256": manifest,
            "N_fixed": fixed, "N_generated": generated, "N_scored": n,
            "C_correct": c, "W_wrong": w, "M_missing": m,
            "generation_coverage": generated / fixed if fixed else None,
            "scoring_coverage": n / fixed if fixed else None,
            "accuracy": c / n if n else None, "hallucination_rate": w / n if n else None,
            "missing_rate": m / n if n else None, "truthfulness": (c - w) / n if n else None}


def csv_text(rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def paired(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> dict[str, Any]:
    a = {r["interaction_id"]: r for r in first}
    b = {r["interaction_id"]: r for r in second}
    if len(a) != len(first) or len(b) != len(second) or set(a) != set(b):
        raise ContractError("Paired comparison needs identical unique expected IDs")
    methods = {(r["subset"], r["dataset_manifest_sha256"], r["evaluation_config_sha256"]) for r in first + second}
    if len(methods) > 1:
        raise ContractError("Paired comparison data/method mismatch")
    ids = sorted(i for i in a if a[i]["judge_status"] == b[i]["judge_status"] == "ok")
    def metrics(mapping):
        c = sum(mapping[i]["verdict"] == "CORRECT" for i in ids)
        w = sum(mapping[i]["verdict"] == "WRONG" for i in ids)
        return {"accuracy": c / len(ids) if ids else None,
                "truthfulness": (c - w) / len(ids) if ids else None}
    left, right = metrics(a), metrics(b)
    return {"N_fixed": len(a), "n_common_scored": len(ids), "common_ids": ids,
            "first": left, "second": right,
            "accuracy_delta": right["accuracy"] - left["accuracy"] if ids else None,
            "truthfulness_delta": right["truthfulness"] - left["truthfulness"] if ids else None,
            "first_failed_ids": sorted(i for i in a if a[i]["judge_status"] != "ok"),
            "second_failed_ids": sorted(i for i in b if b[i]["judge_status"] != "ok")}


def official_check(rows: list[dict[str, Any]], answers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    import pandas as pd
    records = []
    overlaps = []
    for row in rows:
        if row["judge_status"] != "ok":
            continue
        text = row["agent_response_scored"]
        exact = text.strip().lower() == answers[row["interaction_id"]]["ground_truth"].strip().lower()
        missing = is_missing(text)
        correct = exact or row["verdict"] == "CORRECT"
        if exact and missing:
            overlaps.append(row["interaction_id"])
        records.append({"session_id": row["interaction_id"], "is_correct": correct,
                        "is_exact_match": exact, "is_miss": missing,
                        "is_semantically_correct": correct})
    return {"N_scored": len(records), "official_output": pure_reference("evaluation_utils").calculate_scores(pd.DataFrame(records)) if records else None,
            "idk_exact_overlap_ids": overlaps,
            "differences": ["N=0: official function not called; ratios null.",
                            "N=1: official truthfulness is 0; project uses (C-W)/N.",
                            "Exact-match refusal: official dual flags retained here; project gives MISSING priority.",
                            "Only completed scores included; never treat pending/failure as wrong."]}
