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
from src.evaluation.records import audit_requests, merge_evaluations
from src.evaluation.score import (Judge, TOKENIZER_SHA256, append_event, cache_key, deterministic,
    load_tokenizer, local_settings, make_config, messages, official_check, paired, parse_result,
    read_rows, score_row, summary, truncate, validate_config)


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

    def test_full_generation_file_can_supply_evaluation_batch(self):
        predictions = read_rows(self.paths["predictions"])
        meta_path = self.directory / "run_meta_b0.json"
        meta = load_json(meta_path)
        meta.update(N_expected=3, N_success=3, N_failed=0,
                    batch_ids=[p["interaction_id"] for p in predictions])
        dump(meta_path, meta)
        data = Inputs(dict(self.paths), self.directory / "batch_ids.json")
        provenance = data.provenance()
        self.assertEqual(2, len(data.ids))
        self.assertEqual(3, provenance["N_generation_input_records"])
        self.assertEqual(2, provenance["N_evaluation_selected"])

    def test_physical_batch_generation_counts_and_requests(self):
        selected = load_json(self.directory / "batch_ids.json")
        for name in ("predictions_b0.jsonl", "requests_b0.jsonl"):
            path = self.directory / name
            rows_write(path, [r for r in read_rows(path) if r["interaction_id"] in selected])
        self.attach_meta()
        meta_path = self.directory / "run_meta_b0.json"
        meta = load_json(meta_path)
        meta.update(N_expected=2, N_success=2, N_failed=0, batch_ids=selected)
        dump(meta_path, meta)
        data = Inputs(dict(self.paths), self.directory / "batch_ids.json")
        self.assertEqual(2, data.provenance()["N_generation_input_records"])

    def test_generation_metadata_cannot_mix_full_and_evaluation_batch_counts(self):
        meta_path = self.directory / "run_meta_b0.json"
        original = load_json(meta_path)
        for counts in ({"N_expected":2,"N_success":3,"N_failed":0},
                       {"N_expected":3,"N_success":2,"N_failed":0},
                       {"N_expected":2,"N_success":2,"N_failed":0},
                       {"N_expected":True}, {"N_expected":2}):
            with self.subTest(counts=counts):
                dump(meta_path, {**original, **counts})
                with self.assertRaisesRegex(ContractError, "count mismatch"):
                    Inputs(dict(self.paths), self.directory / "batch_ids.json").provenance()

    def test_full_generation_requests_outside_evaluation_batch_are_checked(self):
        selected = load_json(self.directory / "batch_ids.json")
        request_path = self.directory / "requests_b0.jsonl"
        original = read_rows(request_path)
        missing = [r for r in original if r["interaction_id"] in selected]
        changed = [{**r, "run_id":"unrelated-generation"} if r["interaction_id"] not in selected else r for r in original]
        for variant in (missing, changed, original + [original[0]]):
            with self.subTest(size=len(variant)):
                rows_write(request_path, variant)
                self.attach_meta()
                with self.assertRaises(ContractError):
                    Inputs(dict(self.paths), self.directory / "batch_ids.json").provenance()

    def test_generation_source_batch_ids_are_not_evaluation_batch_ids(self):
        meta_path = self.directory / "run_meta_b0.json"
        original = load_json(meta_path)
        selected = load_json(self.directory / "batch_ids.json")
        for batch_ids in (selected, selected + selected, "invalid"):
            dump(meta_path, {**original,"batch_ids":batch_ids})
            with self.assertRaisesRegex(ContractError, "batch mismatch"):
                Inputs(dict(self.paths), self.directory / "batch_ids.json").provenance()

    def test_reviewed_4096_config_keeps_historical_method_intact(self):
        original = load_json(ROOT / "experiments/m3/evaluation.json")
        self.assertEqual(original, make_config())
        extended = make_config(max_tokens=4096)
        self.assertEqual({**original, "max_tokens":4096}, extended)
        self.assertNotEqual(config_sha256(original), config_sha256(extended))
        validate_config(original)
        validate_config(extended)
        for config in ({**extended,"max_tokens":2048}, {**extended,"max_tokens":True},
                       {**extended,"temperature":1}, {**extended,"judge_model":"other"}):
            with self.assertRaises(ContractError):
                validate_config(config)

    def test_cli_4096_reaches_sdk_without_changing_other_parameters(self):
        config = make_config(max_tokens=4096)
        dump(self.directory / "e_config.json", config)
        output = self.cli("--allow-paid-api", "--max-api-requests", "3")
        actual = self.fake_client.chat.completions.create.call_args.kwargs
        self.assertEqual(4096, actual["max_tokens"])
        self.assertEqual(0, actual["temperature"])
        self.assertEqual(config["judge_model"], actual["model"])
        self.assertEqual(0, self.factory_args.kwargs["max_retries"])
        self.assertEqual(config_sha256(config), load_json(output / "run_identity.json")["config_sha256"])

    def test_4096_has_distinct_cache_key_and_preserves_failed_1024_attempt(self):
        old_key = cache_key("m", "i", "q", "a", "p", self.config)
        config = make_config(max_tokens=4096)
        new_key = cache_key("m", "i", "q", "a", "p", config)
        self.assertNotEqual(old_key, new_key)
        journal = self.directory / "cache.jsonl"
        append_event(journal, {"event":"failed", "key":old_key,"run_id":"old-run"})
        judge = Judge(config, self.settings, journal, "new-run", allow_paid=True,
                      max_requests=1, client=self.fake_client)
        self.assertEqual("judge_previous_attempt_requires_review", judge.cached(old_key)["error_code"])
        self.assertEqual("completed", judge.evaluate(new_key, []) ["event"])
        self.assertEqual(4096, self.fake_client.chat.completions.create.call_args.kwargs["max_tokens"])
        self.assertEqual("failed", read_rows(journal)[0]["event"])

    def test_request_audit_counts_failures_repeats_and_unknown_usage(self):
        first = self.directory / "first_journal.jsonl"
        second = self.directory / "second_journal.jsonl"
        start = {"event":"started","run_id":"first","key":"same-input",
                 "started_at":"2026-10-11T00:00:00+00:00","evaluation_config_sha256":config_sha256(self.config)}
        failed = {**start,"event":"failed","error_code":"judge_incomplete_response",
                  "finish_reason":"length","usage":{"total_tokens":123}}
        later = {**start,"run_id":"second","started_at":"2026-10-11T00:01:00+00:00"}
        rows_write(first,[start,failed])
        rows_write(second,[later])
        report = audit_requests([first,second],root=self.directory)
        self.assertEqual(2,report["N_started"])
        self.assertEqual({"failed":1,"incomplete":1},report["by_outcome"])
        self.assertEqual(123,report["known_total_tokens"])
        self.assertIsNone(report["provider_reported_total_tokens"])
        self.assertTrue(report["repeated_inputs"][0]["sent_again_after_failure_or_incomplete"])
        self.assertFalse(report["authorization_verified"])

    def test_request_audit_does_not_double_count_copied_events(self):
        self.judge(allow_paid=True,max_requests=1).evaluate("input",[])
        first = self.directory / "cache.jsonl"
        second = self.directory / "copied_journal.jsonl"
        rows_write(second,read_rows(first))
        report = audit_requests([first,second],root=self.directory)
        self.assertEqual(1,report["N_started"])
        self.assertEqual(2,report["N_identical_copied_events"])
        bad = read_rows(second)
        bad[-1]["verdict"] = "WRONG"
        rows_write(second,bad)
        with self.assertRaises(ContractError):
            audit_requests([first,second],root=self.directory)

    def test_merge_preserves_success_over_failure_and_counts_only_own_calls(self):
        first = self.cli("--allow-paid-api","--max-api-requests","1",expected=2,output="first",run="first")
        second = self.cli("--allow-paid-api","--max-api-requests","3",output="second",run="second")
        output = self.directory / "merged"
        journals = [first/"judge_journal.jsonl",second/"judge_journal.jsonl"]
        before = {p:file_sha256(p) for d in (first,second) for p in d.iterdir() if p.is_file()}
        stats = merge_evaluations(dict(self.paths),self.directory/"e_config.json",[first,second],
                                 journals,output,"merged",root=self.directory)
        self.assertEqual(3,stats["N_scored"])
        self.assertEqual(0,load_json(output/"run_meta_eval_b0.json")["api_requests_total_for_run"])
        self.assertEqual(4,load_json(output/"request_audit.json")["N_started"])
        selection = load_json(output/"merge_record.json")["selected_source_by_interaction_id"]
        source_ids = [r["source_run_id"] for r in selection.values()]
        self.assertEqual(1,source_ids.count("first"))
        self.assertEqual(2,source_ids.count("second"))
        self.assertTrue(all(file_sha256(p)==h for p,h in before.items()))
        command = [sys.executable,"-X","utf8",str(ROOT/"scripts/check_artifacts.py")]
        for name,path in self.paths.items():
            command += ["--"+name,str(path)]
        command += ["--scores",str(output/"scores_b0.jsonl"),"--config","evaluation="+str(self.directory/"e_config.json"),
                    "--run-meta","evaluation="+str(output/"run_meta_eval_b0.json")]
        checked = subprocess.run(command,capture_output=True,encoding="utf-8",timeout=30)
        self.assertEqual(0,checked.returncode,checked.stdout+checked.stderr)
        with self.assertRaisesRegex(ContractError,"already exists"):
            merge_evaluations(dict(self.paths),self.directory/"e_config.json",[first,second],
                              journals,output,"merged",root=self.directory)

    def test_merge_rejects_mixed_config_conflicting_verdict_and_missing_ids(self):
        first = self.cli("--allow-paid-api","--max-api-requests","3",output="first",run="first")
        self.fake_client.chat.completions.create.return_value = completion("Different judgment.\nResult: WRONG")
        second = self.cli("--allow-paid-api","--max-api-requests","3",output="second",run="second")
        journals = [first/"judge_journal.jsonl",second/"judge_journal.jsonl"]
        with self.assertRaisesRegex(ContractError,"Conflicting successful"):
            merge_evaluations(dict(self.paths),self.directory/"e_config.json",[first,second],journals,
                              self.directory/"conflict","conflict",root=self.directory)
        dump(self.directory/"new_config.json",make_config(max_tokens=4096))
        with self.assertRaisesRegex(ContractError,"method or identity"):
            merge_evaluations(dict(self.paths),self.directory/"new_config.json",[first],journals,
                              self.directory/"mixed","mixed",root=self.directory)
        batch = self.cli("--allow-paid-api","--max-api-requests","3","--batch-ids",str(self.directory/"batch_ids.json"),
                         output="batch",run="batch")
        with self.assertRaisesRegex(ContractError,"full subset"):
            merge_evaluations(dict(self.paths),self.directory/"e_config.json",[batch],
                              [batch/"judge_journal.jsonl"],self.directory/"missing","missing",root=self.directory)

    def test_merge_rejects_tampered_output_and_missing_saved_response(self):
        source = self.cli("--allow-paid-api","--max-api-requests","3")
        journal = source/"judge_journal.jsonl"
        empty = self.directory/"empty_journal.jsonl"
        rows_write(empty,[])
        with self.assertRaisesRegex(ContractError,"matching saved judge response"):
            merge_evaluations(dict(self.paths),self.directory/"e_config.json",[source],[empty],
                              self.directory/"no_response","no-response",root=self.directory)
        scores = source/"scores_b0.jsonl"
        rows = read_rows(scores)
        rows[0]["verdict"], rows[0]["score"] = "WRONG",-1
        rows_write(scores,rows)
        with self.assertRaisesRegex(ContractError,"hash mismatch"):
            merge_evaluations(dict(self.paths),self.directory/"e_config.json",[source],[journal],
                              self.directory/"tampered","tampered",root=self.directory)

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

    def comparison_fixture(self):
        root = self.directory / 'comparison-project'
        data = root / 'data/processed/m3/smoke'
        data.mkdir(parents=True)
        for name in ('questions.jsonl', 'answers.jsonl', 'metadata.jsonl'):
            (data / name).write_bytes((self.directory / name).read_bytes())
        (data.parent / 'manifest.json').write_bytes(self.paths['manifest'].read_bytes())
        results = root / 'results/m3/smoke'
        results.mkdir(parents=True)
        scores = {}
        truth = {r['interaction_id']: r['ground_truth'] for r in read_rows(self.paths['answers'])}
        for baseline, group in (('b0', 'smoke_B0'), ('b1', 'smoke_B1_k5')):
            target = results / ('predictions_' + baseline + '.jsonl')
            predictions = read_rows(self.directory / target.name)
            if baseline == 'b0':
                predictions[0]['agent_response'] = "I don't know."
            rows_write(target, predictions)
            rows = [score_row(p, p['agent_response'], truth[p['interaction_id']], self.config, 'comparison-' + baseline,
                              {'verdict': 'CORRECT', 'content': 'Result: CORRECT'}) for p in predictions]
            scores[group] = results / ('scores_' + baseline + '.jsonl')
            rows_write(scores[group], rows)
            inputs = [data.parent / 'manifest.json', target] + [data / (name + '.jsonl')
                      for name in ('questions', 'answers', 'metadata')]
            dump(results / ('run_meta_eval_' + baseline + '.json'), {
                'run_id': 'comparison-' + baseline, 'stage': 'evaluation', 'schema_version': 'm3.v1',
                'subset': 'smoke', 'baseline': baseline.upper(), 'source_generation_run_id': predictions[0]['run_id'],
                'config': self.config, 'config_sha256': config_sha256(self.config),
                'N_expected': len(rows), 'N_success': len(rows), 'N_failed': 0, 'batch_ids': None,
                'input_files_sha256': {os.path.relpath(p, results).replace(os.sep, '/'): file_sha256(p) for p in inputs},
                'output_files_sha256': {scores[group].name: file_sha256(scores[group])}})
        return root, scores

    def test_comparison_retains_group_names_alongside_metrics(self):
        from src.evaluation import review
        root, scores = self.comparison_fixture()
        with patch.object(review, 'ROOT', root):
            result = review.compare_groups(scores, root / 'comparison')
        comparison = result['paired'][0]
        self.assertEqual('smoke_B0', comparison['first_group'])
        self.assertEqual('smoke_B1_k5', comparison['second_group'])
        self.assertIsInstance(comparison['first']['accuracy'], float)
        self.assertIsInstance(comparison['second']['truthfulness'], float)

    def test_comparison_rejects_modified_scores_before_writing_output(self):
        from src.evaluation import review
        from scripts.review_evaluation import main as review_main
        root, scores = self.comparison_fixture()
        path = scores['smoke_B0']
        rows = read_rows(path)
        rows[0].update(verdict='CORRECT', score=1, scoring_method='exact_match')
        rows_write(path, rows)
        output = root / 'rejected-comparison'
        with patch.object(review, 'ROOT', root), \
             patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden')), \
             patch('src.evaluation.score.load_tokenizer', side_effect=AssertionError('Tokenizer forbidden')):
            with self.assertRaisesRegex(ContractError, 'artifact hash mismatch'):
                review.compare_groups(scores, output)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(1, review_main(['compare', '--scores', 'smoke_B0=' + str(path),
                                               '--output-dir', str(output)]))
        self.assertFalse(output.exists())

    def test_comparison_requires_sidecar_and_hash_coverage(self):
        from src.evaluation import review
        root, scores = self.comparison_fixture()
        path = scores['smoke_B0']
        copy = root / 'copy'
        copy.mkdir()
        copied_scores = copy / path.name
        copied_scores.write_bytes(path.read_bytes())
        with patch.object(review, 'ROOT', root):
            with self.assertRaisesRegex(ContractError, 'adjacent evaluation run metadata'):
                review.compare_groups({'smoke_B0': copied_scores}, root / 'missing-meta')
        meta_path = path.parent / 'run_meta_eval_b0.json'
        original = load_json(meta_path)
        variants = [
            {**original, 'output_files_sha256': {'run_meta_eval_b1.json': file_sha256(path.parent / 'run_meta_eval_b1.json')}},
            {**original, 'input_files_sha256': {k: v for k, v in original['input_files_sha256'].items()
                                               if not k.endswith('answers.jsonl')}}]
        for meta in variants:
            with self.subTest(mapping=meta):
                dump(meta_path, meta)
                with patch.object(review, 'ROOT', root), self.assertRaisesRegex(ContractError, 'not covered'):
                    review.compare_groups(scores, root / 'uncovered')
        self.assertFalse((root / 'uncovered').exists())

    def test_comparison_rejects_wrong_run_config_scope_counts_and_input_hash(self):
        from src.evaluation import review
        root, scores = self.comparison_fixture()
        path = scores['smoke_B0']
        meta_path = path.parent / 'run_meta_eval_b0.json'
        original = load_json(meta_path)
        variants = [{'stage': 'generation'}, {'run_id': 'another-evaluation'},
                    {'source_generation_run_id': 'another-generation'}, {'baseline': 'B1'},
                    {'subset': 'dev'}, {'config_sha256': '0' * 64},
                    {'config': {**self.config, 'temperature': 1}},
                    {'N_expected': 99}, {'N_success': True}, {'N_failed': 1},
                    {'batch_ids': ['synthetic-001']}]
        for changes in variants:
            with self.subTest(changes=changes):
                dump(meta_path, {**original, **changes})
                with patch.object(review, 'ROOT', root), self.assertRaises(ContractError):
                    review.compare_groups(scores, root / 'invalid-meta')
        dump(meta_path, original)
        answers = root / 'data/processed/m3/smoke/answers.jsonl'
        answers.write_bytes(b' ' + answers.read_bytes())
        with patch.object(review, 'ROOT', root), self.assertRaisesRegex(ContractError, 'artifact hash mismatch'):
            review.compare_groups(scores, root / 'changed-input')
        self.assertFalse((root / 'invalid-meta').exists())
        self.assertFalse((root / 'changed-input').exists())

    def test_comparison_rejects_rule_conflict_even_with_updated_output_hash(self):
        from src.evaluation import review
        root, scores = self.comparison_fixture()
        path = scores['smoke_B0']
        rows = read_rows(path)
        rows[0].update(verdict='CORRECT', score=1, scoring_method='exact_match')
        rows_write(path, rows)
        meta_path = path.parent / 'run_meta_eval_b0.json'
        meta = load_json(meta_path)
        meta['output_files_sha256'][path.name] = file_sha256(path)
        dump(meta_path, meta)
        with patch.object(review, 'ROOT', root), self.assertRaisesRegex(ContractError, 'deterministic scoring rules'):
            review.compare_groups(scores, root / 'rule-conflict')
        self.assertFalse((root / 'rule-conflict').exists())

    def test_comparison_preserves_valid_generation_and_judge_failures(self):
        from src.evaluation import review
        root, scores = self.comparison_fixture()
        path = scores['smoke_B0']
        prediction_path = path.parent / 'predictions_b0.jsonl'
        meta_path = path.parent / 'run_meta_eval_b0.json'
        original_predictions, original_rows = read_rows(prediction_path), read_rows(path)
        original_meta = load_json(meta_path)
        truth = read_rows(root / 'data/processed/m3/smoke/answers.jsonl')[1]['ground_truth']
        for failure in ('generation', 'judge'):
            with self.subTest(failure=failure):
                predictions, rows = [dict(p) for p in original_predictions], [dict(r) for r in original_rows]
                if failure == 'generation':
                    predictions[1].update(generation_status='error', agent_response=None, error_code='synthetic-failure')
                    rows[1] = score_row(predictions[1], None, truth, self.config, original_meta['run_id'])
                else:
                    rows[1] = score_row(predictions[1], predictions[1]['agent_response'], truth, self.config,
                                        original_meta['run_id'], {'error_code': 'synthetic-judge-failure'})
                rows_write(prediction_path, predictions)
                rows_write(path, rows)
                meta = json.loads(canonical_json(original_meta))
                meta.update(N_success=2, N_failed=1)
                meta['input_files_sha256'][prediction_path.name] = file_sha256(prediction_path)
                meta['output_files_sha256'][path.name] = file_sha256(path)
                dump(meta_path, meta)
                with patch.object(review, 'ROOT', root), \
                     patch('src.evaluation.score.load_tokenizer', side_effect=AssertionError('Tokenizer forbidden')), \
                     patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden')):
                    result = review.compare_groups(scores, root / ('valid-' + failure))
                self.assertEqual(2, result['groups'][0]['N_scored'])
                self.assertEqual(2, result['paired'][0]['n_common_scored'])
                self.assertEqual(['synthetic-002'], result['paired'][0]['first_failed_ids'])

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

    def test_eval_paired_transitions_and_failures(self):
        from src.evaluation.review import paired_details
        first = []
        second = []
        for index, (left, right) in enumerate((("MISSING", "CORRECT"), ("CORRECT", "WRONG"),
                                               ("WRONG", "WRONG"), ("MISSING", None))):
            common = {"interaction_id": str(index), "subset": "eval", "dataset_manifest_sha256": "same",
                      "evaluation_config_sha256": "same"}
            for target, verdict in ((first, left), (second, right)):
                target.append({**common, "judge_status": "ok" if verdict else "error", "verdict": verdict,
                               "score": {"CORRECT": 1, "WRONG": -1, "MISSING": 0, None: None}[verdict]})
        report = paired_details(first, list(reversed(second)))
        self.assertEqual((1, 1, 1), (report["second_wins"], report["ties"], report["second_losses"]))
        self.assertEqual(3, report["n_common_scored"])
        self.assertEqual(1, report["transition_matrix"]["MISSING"]["CORRECT"])
        self.assertEqual(["3"], report["second_failed_ids"])
        self.assertIsNone(report["per_question"][-1]["score_delta"])

    def test_eval_comparison_registration_and_method_guard(self):
        from src.evaluation.review import EVAL_GROUPS, EVAL_COMPARISONS, INPUT_GROUPS, paired_details
        self.assertEqual(6, len(INPUT_GROUPS))
        self.assertEqual([("eval_B0", "eval_B1_k1")], EVAL_COMPARISONS)
        self.assertEqual({"eval"}, {g["subset"] for g in EVAL_GROUPS})
        row = {"interaction_id": "a", "subset": "eval", "dataset_manifest_sha256": "same",
               "evaluation_config_sha256": "one", "judge_status": "ok", "verdict": "MISSING", "score": 0}
        with self.assertRaises(ContractError):
            paired_details([row], [{**row, "evaluation_config_sha256": "two"}])

    def test_submission_source_has_no_machine_paths(self):
        import re
        files = [ROOT / "scripts/evaluate.py", ROOT / "scripts/review_evaluation.py", ROOT / "scripts/evaluation_records.py"] + list((ROOT / "src/evaluation").glob("*.py"))
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
