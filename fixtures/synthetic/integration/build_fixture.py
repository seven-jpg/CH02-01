"""Rebuild small synthetic contract fixtures. No network or model is used."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
NOTICE = "SYNTHETIC CONTRACT TEST ONLY: not official data or measured model output"
REVISION = "0123456789abcdef0123456789abcdef01234567"
DATASET = "synthetic/test-only-crag-contract"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def write_json(directory, name, value):
    path = directory / name
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_rows(directory, name, rows):
    (directory / name).write_bytes(
        "".join(canonical(row) + "\n" for row in rows).encode("utf-8")
    )


def build(directory=HERE, *, count=3, subset="smoke", batch_count=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if count < 3 or subset not in {"smoke", "dev", "eval"}:
        raise ValueError("Synthetic fixture needs at least three IDs and a known subset")
    ids = [f"synthetic-{i:03d}" for i in range(1, count + 1)]
    subsets = {name: {"ids": [], "count": 0} for name in ("smoke", "dev", "eval")}
    subsets[subset] = {"ids": ids, "count": len(ids)}
    manifest = {
        "schema_version": "m3.v1", "data_origin": "official",
        "dataset_id": DATASET, "revision": REVISION, "split": "validation",
        "seed": 42, "grouping": "session and image group and duplicate query",
        "id_rule": "synthetic identifiers for unit tests only",
        "subsets": subsets,
        "fixture_notice": NOTICE,
    }
    manifest_hash = write_json(directory, "manifest.json", manifest)
    config = {"provider": "synthetic-provider", "model": "synthetic-model",
              "temperature": 0, "max_tokens": 100,
              "answer_instruction": "Synthetic test: answer briefly or abstain."}
    retrieval_config = {"top_k": 5, "source": "synthetic-contract-test",
                        "index_revision": "synthetic-index-v1",
                        "encoder_revision": "synthetic-encoder-v1"}
    evaluation_config = {"judge_model": "synthetic-judge",
                         "response_tokenizer": "meta-llama/Llama-3.2-1B-Instruct",
                         "response_max_tokens": 75}
    write_json(directory, "generation.json", config)
    write_json(directory, "retrieval.json", retrieval_config)
    write_json(directory, "evaluation.json", evaluation_config)
    batch = [ids[2], ids[0]] if batch_count is None else list(reversed(ids[:batch_count]))
    write_json(directory, "batch_ids.json", batch)
    questions, answers, metadata, evidence = [], [], [], []
    predictions = {"B0": [], "B1": []}
    scores = {"B0": [], "B1": []}
    requests = {"B0": [], "B1": []}
    for i, interaction_id in enumerate(ids, 1):
        common = {"schema_version": "m3.v1", "subset": subset,
                  "interaction_id": interaction_id,
                  "dataset_manifest_sha256": manifest_hash}
        query = f"What label belongs to synthetic fixture number {i}?"
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
        session = f"synthetic-session-{i}"
        questions.append({**common, "session_id": session, "query": query})
        answers.append({**common, "ground_truth": f"reference-answer-marker-{i:03d}"})
        metadata.append({**common, "session_id": session,
                         "source_interaction_id": interaction_id,
                         "source_dataset": DATASET, "source_split": "validation",
                         "source_revision": REVISION, "turn_index": 0,
                         "domain": None, "query_category": None,
                         "image_group_id": f"synthetic-image-{i}",
                         "is_egocentric": None})
        hit = {"rank": 1, "doc_id": f"synthetic-document-{i}",
               "url": "https://example.invalid/synthetic-contract-test",
               "title": "Synthetic evidence, not a real search result",
               "text": f"Synthetic fixture evidence number {i}.",
               "score": 0.5, "score_kind": "similarity"}
        evidence.append({**common, "query_sha256": query_hash,
                         "run_id": "synthetic-retrieval-run",
                         "retrieval_status": "ok", "hits": [hit],
                         "retrieval_config_sha256": digest(retrieval_config),
                         "index_revision": "synthetic-index-v1",
                         "encoder_revision": "synthetic-encoder-v1",
                         "latency_ms": None, "error_code": None})
        for baseline in predictions:
            run_id = f"synthetic-generation-{baseline.lower()}"
            content = query
            if baseline == "B1":
                content += "\nRetrieved evidence:\n" + hit["text"]
            messages = [
                {"role": "system", "content": config["answer_instruction"]},
                {"role": "user", "content": content},
            ]
            prompt_hash = digest(messages)
            response = f"Synthetic model-output marker {i}; no model was called."
            predictions[baseline].append({
                **common, "query_sha256": query_hash, "baseline": baseline,
                "run_id": run_id, "generation_status": "ok",
                "agent_response": response, "provider": config["provider"],
                "model": config["model"], "generation_config_sha256": digest(config),
                "retrieval_config_sha256": digest(retrieval_config) if baseline == "B1" else None,
                "evidence_status": "ok" if baseline == "B1" else "not_used",
                "prompt_sha256": prompt_hash,
                "usage": {"input_tokens": None, "output_tokens": None},
                "latency_ms": None, "error_code": None,
            })
            requests[baseline].append({
                **common, "baseline": baseline, "run_id": run_id,
                "query_sha256": query_hash, "prompt_sha256": prompt_hash,
                "messages": messages,
                "evidence_used": [{"doc_id": hit["doc_id"], "text": hit["text"]}]
                if baseline == "B1" else [],
            })
            scores[baseline].append({
                **common, "baseline": baseline,
                "run_id": f"synthetic-evaluation-{baseline.lower()}",
                "source_generation_run_id": run_id, "judge_status": "ok",
                "verdict": "CORRECT", "score": 1,
                "agent_response_scored": response, "scoring_method": "manual",
                "judge_model": None, "evaluation_config_sha256": digest(evaluation_config),
                "response_tokenizer": evaluation_config["response_tokenizer"],
                "response_max_tokens": 75,
                "judge_reason": NOTICE, "error_code": None,
            })
    for name, rows in {"questions": questions, "answers": answers,
                       "metadata": metadata, "evidence": evidence}.items():
        write_rows(directory, name + ".jsonl", rows)
    for baseline in predictions:
        suffix = baseline.lower() + ".jsonl"
        write_rows(directory, "predictions_" + suffix, predictions[baseline])
        write_rows(directory, "scores_" + suffix, scores[baseline])
        write_rows(directory, "requests_" + suffix, requests[baseline])


if __name__ == "__main__":
    build()
