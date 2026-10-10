"""E evaluation controls. Tests use a caller-selected artifact directory and mock every API.

Set E_TEST_WORKDIR to a process-artifact directory before running. Test files are
retained for inspection; this module never deletes or moves a file.
"""
from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fixtures.synthetic.integration.build_fixture import build
from scripts import evaluate
from src.contracts.m3 import ContractError, canonical_json, config_sha256, file_sha256, load_json
from src.evaluation.inputs import Inputs
from src.evaluation.score import (Judge, TOKENIZER_SHA256, append_event, cache_key, deterministic,
    load_tokenizer, local_settings, make_config, messages, official_check, paired, parse_result,
    read_rows, score_row, summary, truncate)


def dump(path, value):
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def rows_write(path, rows):
    path.write_text("".join(canonical_json(r) + "\n" for r in rows), encoding="utf-8")


def completion(content="Brief rationale.\nResult: CORRECT", finish="stop", usage=True):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
                           usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}) if usage else None,
                           id="synthetic-judge-response")


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = os.environ.get("E_TEST_WORKDIR")
        if not target:
            raise unittest.SkipTest("Set E_TEST_WORKDIR to retain test process artifacts")
        cls.base = Path(target) / ("evaluation-" + uuid.uuid4().hex)
        cls.base.mkdir(parents=True)
        cls.config = make_config()
        cls.settings = local_settings(cls.config)
        cls.tokenizer = load_tokenizer(cls.settings)

    def setUp(self):
        self.directory = self.base / self._testMethodName
        self.directory.mkdir()
        build(self.directory)
        self.paths = {name: self.directory / (name + (".json" if name == "manifest" else ".jsonl"))
                      for name in ("questions", "answers", "metadata")}
        self.paths["manifest"] = self.directory / "manifest.json"
        self.paths["predictions"] = self.directory / "predictions_b0.jsonl"
        dump(self.directory / "e_config.json", self.config)
        self.attach_meta()
        self.fake_client = Mock()
        self.fake_client.chat.completions.create.return_value = completion()

    def attach_meta(self):
        pred = read_rows(self.paths["predictions"])[0]
        config = load_json(self.directory / "generation.json")
        dump(self.directory / "run_meta_b0.json", {
            "run_id": pred["run_id"], "stage": "generation", "schema_version": "m3.v1", "subset": "smoke", "baseline": "B0",
            "config": config, "config_sha256": config_sha256(config),
            "input_files_sha256": {name + ".json" if name == "manifest" else name + ".jsonl": file_sha256(self.paths[name]) for name in ("manifest", "questions")},
            "output_files_sha256": {name: file_sha256(self.directory / name) for name in ("predictions_b0.jsonl", "requests_b0.jsonl")}})

    def cli(self, *extra, expected=0, output="output", run="synthetic-evaluation"):
        args = []
        for name, path in self.paths.items():
            args += ["--" + name, str(path)]
        args += ["--config", str(self.directory / "e_config.json"), "--output-dir", str(self.directory / output), "--run-id", run]
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream), patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in tests")), \
             patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden in tests")), \
             patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden in tests")), \
             patch("openai.OpenAI", return_value=self.fake_client) as factory:
            result = evaluate.main(args + list(extra))
        self.assertEqual(expected, result, stream.getvalue())
        self.last_output = stream.getvalue()
        self.factory_calls = factory.call_count
        self.factory_args = factory.call_args
        return self.directory / output

    def judge(self, **kwargs):
        return Judge(self.config, {**self.settings, "JUDGE_API_KEY": "synthetic-secret-marker"},
                     self.directory / "cache.jsonl", "synthetic-run", client=self.fake_client, **kwargs)

    def prediction(self):
        return read_rows(self.paths["predictions"])[0]

    def test_rules_do_not_extend_refusal(self):
        for text in ("I don't know.", "I do not know", "Well, I DON'T KNOW!", "I don’t know."):
            self.assertEqual(("MISSING", "idk"), deterministic(text, "other"))
        for text in ("I'm uncertain.", "Cannot help.", "i  dont know", "The answer may be London."):
            self.assertIsNone(deterministic(text, "other"))
        self.assertEqual(("CORRECT", "exact_match"), deterministic(" London ", "london"))
        self.assertEqual(("MISSING", "idk"), deterministic("I don't know.", "I don't know."))

    def test_official_truncation_real_and_boundaries(self):
        source = ast.parse((ROOT / "external/CRAG-MM/evaluation/evaluator.py").read_text(encoding="utf-8"))
        cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "CRAGEvaluator")
        function = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "truncate_agent_responses")
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "official-extracted", "exec"), scope)
        boundary = ["", "hello " * 200, "中文测试。" * 100, "<|begin_of_text|>hi<|eot_id|>", " ", " x" * 74, " x" * 75, " x" * 76]
        real = []
        from src.evaluation.review import INPUT_GROUPS
        for group in INPUT_GROUPS:
            real += [r["agent_response"] for r in read_rows(ROOT / group["predictions"]) if r["generation_status"] == "ok"]
        self.assertEqual(240, len(real))
        sample = real + boundary
        self.assertEqual(scope["truncate_agent_responses"](SimpleNamespace(tokenizer=self.tokenizer), sample), truncate(self.tokenizer, sample))
        self.assertTrue(all(len(enc.ids) <= 75 for enc in self.tokenizer.encode_batch(sample)))

    def test_tokenizer_mismatch_never_downloads(self):
        fake = self.directory / "bad_tokenizer.json"
        fake.write_text("{}", encoding="utf-8")
        with self.assertRaises(ContractError):
            load_tokenizer({**self.settings, "RESPONSE_TOKENIZER_PATH": str(fake)})

    def test_row_shuffle_keeps_id_associations(self):
        original = Inputs(dict(self.paths)).rows
        for name in ("questions", "answers", "metadata", "predictions"):
            rows = read_rows(self.paths[name])
            random.Random(10).shuffle(rows)
            rows_write(self.paths[name], rows)
        self.assertEqual(original, Inputs(dict(self.paths)).rows)

    def test_missing_duplicate_unknown_hash_and_bad_json_rejected(self):
        path = self.paths["answers"]
        original = read_rows(path)
        variants = [original[:-1], original + [original[0]],
                    [{**r, "interaction_id": "unknown-id"} if j == 0 else r for j, r in enumerate(original)],
                    [{**r, "dataset_manifest_sha256": "0" * 64} if j == 0 else r for j, r in enumerate(original)]]
        for variant in variants:
            rows_write(path, variant)
            with self.assertRaises(ContractError):
                Inputs(dict(self.paths))
        for text in ("{bad}\n", "{\"x\":1,\"x\":2}\n", "\ufeff{}\n", "{\"x\":NaN}\n", "\n"):
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ContractError):
                Inputs(dict(self.paths))

    def test_query_and_mixed_source_rejected(self):
        original = read_rows(self.paths["predictions"])
        for field, value in (("query_sha256", "0" * 64), ("run_id", "other-run"), ("generation_config_sha256", "0" * 64)):
            variant = [{**r, field: value} if j == 0 else r for j, r in enumerate(original)]
            rows_write(self.paths["predictions"], variant)
            with self.assertRaises(ContractError):
                Inputs(dict(self.paths))

    def test_batch_filters_full_answers_before_coverage(self):
        selected = load_json(self.directory / "batch_ids.json")
        rows_write(self.paths["predictions"], [p for p in read_rows(self.paths["predictions"]) if p["interaction_id"] in selected])
        data = Inputs(dict(self.paths), self.directory / "batch_ids.json")
        self.assertEqual(set(selected), set(data.rows["answers"]))
        self.assertEqual(2, len(data.ids))
        with self.assertRaises(ContractError):
            Inputs(dict(self.paths))

    def test_result_parser_rejects_conflict_empty_and_truncated(self):
        self.assertEqual("CORRECT", parse_result("Because grounded.\nResult: CORRECT"))
        self.assertEqual("WRONG", parse_result("Wrong object.\nResult: WRONG\n"))
        for content, finish in (("", "stop"), (None, "stop"), ("CORRECT", "stop"),
                ("Result: CORRECT\nResult: WRONG", "stop"), ("Result: CORRECT", "length"),
                ("Result: CORRECT\nextra", "stop"), ("Earlier Result: WRONG\nResult: CORRECT", "stop")):
            with self.assertRaises(ContractError):
                parse_result(content, finish)

    def test_generation_failure_and_judge_failure_have_no_score(self):
        p = self.prediction()
        for status in ("error", "blocked"):
            row = score_row({**p, "generation_status": status}, None, "truth", self.config, "e")
            self.assertEqual(("unscored", None, None), (row["judge_status"], row["verdict"], row["score"]))
        row = score_row(p, "unrelated", "truth", self.config, "e", {"error_code": "timeout"})
        self.assertEqual(("error", None, None), (row["judge_status"], row["verdict"], row["score"]))

    def test_paid_gates_limit_and_zero_hidden_retries(self):
        for kwargs in ({}, {"allow_paid": True}, {"allow_paid": True, "max_requests": 0}):
            j = self.judge(**kwargs)
            self.assertEqual("paid_api_disabled", j.evaluate("a", []) ["error_code"])
        self.fake_client.chat.completions.create.assert_not_called()
        j = self.judge(allow_paid=True, max_requests=1)
        self.assertEqual("CORRECT", j.evaluate("a", []) ["verdict"])
        self.assertEqual("judge_request_limit", j.evaluate("b", []) ["error_code"])
        self.assertEqual(1, self.fake_client.chat.completions.create.call_count)
        resumed = self.judge(allow_paid=True, max_requests=1)
        self.assertEqual("judge_request_limit", resumed.evaluate("b", []) ["error_code"])

    def test_cache_reuses_input_but_invalidates_changed_method_or_data(self):
        key = cache_key("m", "i", "q", "a", "p", self.config)
        j = self.judge(allow_paid=True, max_requests=1)
        j.evaluate(key, [])
        self.assertTrue(j.evaluate(key, []) ["cache_hit"])
        for args in (("x", "i", "q", "a", "p"), ("m", "j", "q", "a", "p"), ("m", "i", "qq", "a", "p"),
                     ("m", "i", "q", "aa", "p"), ("m", "i", "q", "a", "pp")):
            self.assertNotEqual(key, cache_key(*args, self.config))
        self.assertNotEqual(key, cache_key("m", "i", "q", "a", "p", {**self.config, "judge_model": "different"}))
        p = self.prediction()
        a = score_row(p, "p", "a", self.config, "e-one", j.cached(key))
        b = score_row({**p, "baseline": "B1", "run_id": "generation-two"}, "p", "a", self.config, "e-two", j.cached(key))
        self.assertEqual("generation-two", b["source_generation_run_id"])
        self.assertEqual("B0", a["baseline"])
        self.fake_client.chat.completions.create.assert_called_once()

    def test_interrupted_and_failed_requests_are_not_resent(self):
        append_event(self.directory / "cache.jsonl", {"event": "started", "run_id": "synthetic-run", "key": "unknown"})
        j = self.judge(allow_paid=True, max_requests=10)
        self.assertEqual("judge_previous_attempt_requires_review", j.evaluate("unknown", []) ["error_code"])
        self.fake_client.chat.completions.create.assert_not_called()
        self.fake_client.chat.completions.create.side_effect = RuntimeError("synthetic-secret-marker from provider")
        self.assertIn("error_code", j.evaluate("new", []))
        self.assertEqual("judge_run_stopped", j.evaluate("later", []) ["error_code"])
        text = (self.directory / "cache.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("synthetic-secret-marker", text)
        self.assertEqual(1, self.fake_client.chat.completions.create.call_count)

    def test_api_empty_invalid_structure_and_usage_unknown(self):
        for n, response in enumerate((completion(""), SimpleNamespace(choices=[]), completion("Result: WRONG", "length"))):
            self.fake_client.chat.completions.create.return_value = response
            j = Judge(self.config, self.settings, self.directory / f"cache-{n}.jsonl", "r", allow_paid=True, max_requests=1, client=self.fake_client)
            self.assertIn("error_code", j.evaluate("k", []))
        self.fake_client.chat.completions.create.return_value = completion(usage=False)
        j = self.judge(allow_paid=True, max_requests=1)
        self.assertIsNone(j.evaluate("valid", []) ["usage"])

    def test_raw_judge_content_is_redacted(self):
        self.fake_client.chat.completions.create.return_value = completion("synthetic-secret-marker\nResult: CORRECT")
        j = self.judge(allow_paid=True, max_requests=1)
        result = j.evaluate("k", [])
        self.assertNotIn("synthetic-secret-marker", canonical_json(result))
        self.assertNotIn("synthetic-secret-marker", (self.directory / "cache.jsonl").read_text(encoding="utf-8"))

    def test_summary_zero_single_and_unequal_batches(self):
        empty = summary([], [], subset="smoke", baseline="B0", manifest="m")
        self.assertIsNone(empty["accuracy"])
        p = self.prediction()
        correct = score_row(p, "London", "London", self.config, "e")
        one = summary([correct], [p], subset="smoke", baseline="B0", manifest=p["dataset_manifest_sha256"])
        self.assertEqual(1, one["truthfulness"])
        official = official_check([correct], {p["interaction_id"]: {"ground_truth": "London"}})
        self.assertEqual(0, official["official_output"]["truthfulness_score"])
        self.assertIsNone(official_check([], {})["official_output"])
        predictions = [p] + [{**p, "interaction_id": str(i)} for i in range(4)]
        scores = [correct] + [score_row(x, "I don't know.", "truth", self.config, "e") for x in predictions[1:]]
        combined = summary(scores, predictions, subset="smoke", baseline="B0", manifest=p["dataset_manifest_sha256"])
        self.assertEqual(.2, combined["accuracy"])
        self.assertNotEqual(.5, combined["accuracy"])
        with self.assertRaises(ContractError):
            summary(scores + [correct], predictions, subset="smoke", baseline="B0", manifest="m")

    def test_paired_comparison_uses_common_success(self):
        p = self.prediction()
        c = score_row(p, "a", "a", self.config, "e")
        fail = {**c, "judge_status": "error", "verdict": None, "score": None, "error_code": "failure"}
        missing = {**score_row(p, "I don't know.", "a", self.config, "e"), "interaction_id": "second"}
        result = paired([c, missing], [fail, missing])
        self.assertEqual(["second"], result["common_ids"])
        self.assertEqual(1, result["n_common_scored"])
        self.assertEqual([p["interaction_id"]], result["second_failed_ids"])

    def test_dry_run_network_blocked_and_no_client_initialized(self):
        output = self.cli("--dry-run")
        self.assertEqual(0, self.factory_calls)
        self.fake_client.chat.completions.create.assert_not_called()
        self.assertFalse((output / "scores_b0.jsonl").exists())
        precheck = load_json(output / "precheck.json")
        self.assertEqual(3, precheck["N_pending_judge"])
        self.assertEqual(0, precheck["real_api_requests"])

    def test_cli_refuses_paid_without_budget_or_disabled(self):
        self.cli(expected=1)
        self.cli("--allow-paid-api", expected=1)
        self.cli("--max-api-requests", "3", expected=1)
        self.assertEqual(0, self.factory_calls)

    def test_effective_env_conflicts_and_env_priority(self):
        with patch.dict(os.environ, {"JUDGE_MODEL": "other"}):
            with self.assertRaises(ContractError):
                local_settings(self.config)
        with patch.dict(os.environ, {"JUDGE_API_KEY": "synthetic-env-override"}):
            self.assertEqual("synthetic-env-override", local_settings(self.config)["JUDGE_API_KEY"])
        self.assertNotIn("synthetic-env-override", canonical_json(self.config))

    def test_exact_and_idk_do_not_call_api(self):
        preds = read_rows(self.paths["predictions"])
        answers = {r["interaction_id"]: r for r in read_rows(self.paths["answers"])}
        for index, p in enumerate(preds):
            p["agent_response"] = answers[p["interaction_id"]]["ground_truth"] if index == 0 else "I don't know."
        rows_write(self.paths["predictions"], preds)
        self.attach_meta()
        output = self.cli("--allow-paid-api", "--max-api-requests", "1")
        self.assertEqual(0, self.factory_calls)
        self.assertEqual(["CORRECT", "MISSING", "MISSING"], [r["verdict"] for r in read_rows(output / "scores_b0.jsonl")])

    def test_simulated_cli_scores_pass_A_and_resume_integrity(self):
        output = self.cli("--allow-paid-api", "--max-api-requests", "3")
        self.assertEqual(3, self.fake_client.chat.completions.create.call_count)
        self.assertEqual(0, self.factory_args.kwargs["max_retries"])
        actual = self.fake_client.chat.completions.create.call_args.kwargs
        self.assertEqual(self.config["judge_model"], actual["model"])
        self.assertEqual(0, actual["temperature"])
        self.assertEqual(1024, actual["max_tokens"])
        self.fake_client.chat.completions.create.reset_mock()
        self.cli("--allow-paid-api", "--max-api-requests", "3", "--resume")
        self.fake_client.chat.completions.create.assert_not_called()
        command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/check_artifacts.py")]
        for name, path in self.paths.items():
            command += ["--" + name, str(path)]
        command += ["--scores", str(output / "scores_b0.jsonl"), "--config", "evaluation=" + str(self.directory / "e_config.json"),
                    "--run-meta", "evaluation=" + str(output / "run_meta_eval_b0.json")]
        result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        dump(output / "A_acceptance.json", json.loads(result.stdout))
        dump(output / "SIMULATED_NOTICE.json", {"is_simulated": True, "real_api_requests": 0,
              "notice": "Every judge completion in this development fixture was injected using unittest.mock; not real model scores."})
        # The exported sidecar must disclose simulation even when the tested CLI uses a mocked SDK.
        meta = load_json(output / "run_meta_eval_b0.json")
        meta["is_simulated"] = True
        dump(output / "run_meta_eval_b0.json", meta)
        scores = read_rows(output / "scores_b0.jsonl")
        rows_write(output / "scores_b0.jsonl", list(reversed(scores)))
        self.cli("--allow-paid-api", "--max-api-requests", "3", "--resume", expected=1)

    def test_budget_errors_preserve_all_expected_ids(self):
        output = self.cli("--allow-paid-api", "--max-api-requests", "1", expected=2)
        rows = read_rows(output / "scores_b0.jsonl")
        self.assertEqual(3, len(rows))
        self.assertEqual(["ok", "error", "error"], [r["judge_status"] for r in rows])
        self.assertTrue(all(r["score"] is None for r in rows[1:]))

    def test_actual_judge_failure_stops_later_calls_and_keeps_all_rows(self):
        self.fake_client.chat.completions.create.side_effect = RuntimeError("do not log provider body")
        output = self.cli("--allow-paid-api", "--max-api-requests", "3", expected=2)
        self.assertEqual(1, self.fake_client.chat.completions.create.call_count)
        rows = read_rows(output / "scores_b0.jsonl")
        self.assertEqual(3, len(rows))
        self.assertEqual([None] * 3, [r["verdict"] for r in rows])
        self.assertNotIn("do not log provider body", self.last_output)

    def test_output_input_collision_and_stale_identity_rejected(self):
        output = self.cli("--dry-run")
        self.cli("--dry-run", expected=1)
        self.cli("--dry-run", "--resume", run="different-run", expected=1)
        self.cli("--dry-run", "--cache", str(self.paths["predictions"]), output="new", expected=1)

    def test_run_lock_prevents_concurrent_writer(self):
        lock = self.directory / "exclusive.lock"
        with evaluate.exclusive(lock):
            with self.assertRaises(ContractError):
                with evaluate.exclusive(lock):
                    self.fail("Second writer acquired exclusive lock")
        with evaluate.exclusive(lock):
            pass

    def test_human_summary_leaves_blank_reviews_pending(self):
        from src.evaluation.review import human_summary, blind_review
        pool = [{"group": "g", "interaction_id": str(i), "query": "q", "ground_truth": "a", "agent_response": "p",
                 "agent_response_scored": "p", "judge_key": "key" if i < 20 else None, "rule": None if i < 20 else "idk",
                 "source_generation_run_id": "r"} for i in range(30)]
        blind_review(self.directory / "review", pool)
        report = human_summary(self.directory / "review/human_review.csv", self.directory / "review/blind_mapping_private.jsonl", [])
        self.assertEqual(30, report["N_pending_human"])
        self.assertEqual(0, report["N_human_completed"])
        self.assertIsNone(report["agreement"])

    def test_submission_source_has_no_machine_paths(self):
        import re
        files = [ROOT / "scripts/evaluate.py", ROOT / "scripts/review_evaluation.py"] + list((ROOT / "src/evaluation").glob("*.py"))
        prohibited_directory = "codex" + "_proc"
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(prohibited_directory, text)
            self.assertIsNone(re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", text), path.name)
            self.assertNotIn("/" + "home/", text)

    def test_other_cwd_and_help_never_need_credentials(self):
        other = self.directory / "other-cwd"
        other.mkdir()
        result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/evaluate.py"), "--help"],
                                cwd=other, capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(0, result.returncode)
        self.assertIn("--dry-run", result.stdout)
        from src.evaluation.inputs import resolve
        original = Path.cwd()
        try:
            os.chdir(other)
            self.assertEqual(ROOT / "experiments/m3/evaluation.json", resolve("experiments/m3/evaluation.json"))
        finally:
            os.chdir(original)


if __name__ == "__main__":
    unittest.main()
