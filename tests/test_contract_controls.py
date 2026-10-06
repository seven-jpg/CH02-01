"""Focused contract controls; synthetic inputs only, no network/model/index.

These tests do not inherit the existing artifact test suite. Helpers are tested
at their public boundary; grouping and frozen prompts use the CLI and an
isolated copy rebuilt by the published synthetic fixture builder.
"""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.contracts.m3 import (  # noqa: E402
    ContractError, canonical_json, config_sha256, load_json, parse_json,
    prompt_sha256, query_sha256, render_messages,
)

SCRIPT = ROOT / "scripts" / "check_artifacts.py"
FIXTURE_BUILDER = ROOT / "fixtures" / "synthetic" / "integration" / "build_fixture.py"
TEMPLATES = {
    "system": "Synthetic contract test: answer briefly from permitted input.",
    "b0_user": "Question: {query}",
    "b1_user": "Evidence:\n{evidence}\nQuestion: {query}",
}


class ContractHelperControlsTests(unittest.TestCase):
    def test_duplicate_json_keys_are_rejected_at_any_depth(self):
        for payload in ('{"id":1,"id":2}', '{"outer":{"id":1,"id":2}}'):
            with self.subTest(payload=payload), self.assertRaises(ContractError):
                parse_json(payload)

    def test_nonfinite_numbers_and_overflow_are_not_json_data(self):
        for payload in ('{"value":NaN}', '[Infinity]', '[-Infinity]', '{"value":1e999}'):
            with self.subTest(payload=payload), self.assertRaises(ContractError):
                parse_json(payload)

    def test_utf8_loading_accepts_chinese_and_rejects_bom_bad_bytes_and_surrogates(self):
        with tempfile.TemporaryDirectory(prefix="m3-helper-encoding-") as directory:
            path = Path(directory) / "input.json"
            path.write_bytes('{"问题":"答案"}'.encode("utf-8"))
            self.assertEqual({"问题": "答案"}, load_json(path))
            for payload in (b'\xef\xbb\xbf{"x":1}', b'{"x":"\xff"}', b'{"x":"\\ud800"}'):
                with self.subTest(payload=repr(payload)):
                    path.write_bytes(payload)
                    with self.assertRaises(ContractError):
                        load_json(path)

    def test_canonical_json_and_query_hash_use_original_unicode(self):
        self.assertEqual('{"a":"中文","z":[1,2]}', canonical_json({"z": [1, 2], "a": "中文"}))
        query = "原始问题？\n保留空白 "
        self.assertEqual(hashlib.sha256(query.encode("utf-8")).hexdigest(), query_sha256(query))
        self.assertNotEqual(query_sha256(query), query_sha256(query.strip()))

    def test_config_hash_ignores_only_absolute_machine_cache_locations_and_credentials(self):
        first = {
            "model": "synthetic-model", "top_k": 5,
            "cache_dir": "C:\\Users\\member-c\\cache",
            "nested": [{"model_cache_path": "D:\\models\\cache", "revision": "fixed-v1"}],
            "api_key": "SYNTHETIC_NOT_A_REAL_KEY_1",
        }
        second = copy.deepcopy(first)
        second["cache_dir"] = "/home/member-d/cache"
        second["nested"][0]["model_cache_path"] = "/tmp/model-cache"
        second["api_key"] = "SYNTHETIC_NOT_A_REAL_KEY_2"
        self.assertEqual(config_sha256(first), config_sha256(second))
        self.assertEqual("C:\\Users\\member-c\\cache", first["cache_dir"], "Hashing must not mutate the config.")

    def test_experimental_parameters_versions_and_prompts_change_config_hash(self):
        base = {"model": "synthetic-v1", "revision": "fixed-v1", "top_k": 5,
                "temperature": 0, "max_tokens": 100, "prompt_templates": copy.deepcopy(TEMPLATES)}
        changes = {"model": "synthetic-v2", "revision": "fixed-v2", "top_k": 6,
                   "temperature": 0.5, "max_tokens": 75,
                   "prompt_templates": {**TEMPLATES, "system": "Changed answer constraint."}}
        for key, value in changes.items():
            with self.subTest(setting=key):
                updated = copy.deepcopy(base)
                updated[key] = value
                self.assertNotEqual(config_sha256(base), config_sha256(updated))

    def test_relative_cache_and_noncache_absolute_paths_are_not_silently_removed(self):
        for key, first, second in (
            ("cache_dir", "cache/version-a", "cache/version-b"),
            ("prompt_path", "C:\\prompts\\a.txt", "D:\\prompts\\b.txt"),
        ):
            with self.subTest(key=key):
                self.assertNotEqual(config_sha256({key: first}), config_sha256({key: second}))

    def test_prompt_reconstruction_preserves_query_and_selected_evidence_as_data(self):
        config = {"prompt_templates": copy.deepcopy(TEMPLATES)}
        query = "What does the literal {ground_truth} token mean?"
        evidence = [{"doc_id": "synthetic-doc", "text": "Literal {query} in source text."}]
        self.assertEqual([
            {"role": "system", "content": TEMPLATES["system"]},
            {"role": "user", "content": "Question: " + query},
        ], render_messages(config, "B0", query, []))
        self.assertEqual([
            {"role": "system", "content": TEMPLATES["system"]},
            {"role": "user", "content": "Evidence:\n[synthetic-doc]\nLiteral {query} in source text.\nQuestion: " + query},
        ], render_messages(config, "B1", query, evidence))

    def test_invalid_templates_and_forbidden_b0_evidence_are_rejected(self):
        bad_templates = (
            ("B0", "{ground_truth}"), ("B0", "{query.attr}"),
            ("B0", "{query[0]}"), ("B0", "{query!r}"),
            ("B0", "{query:>10}"), ("B0", "{"),
            ("B0", "No question field"), ("B0", "{query} {evidence}"),
            ("B1", "{query}"),
        )
        for baseline, template in bad_templates:
            with self.subTest(baseline=baseline, template=template):
                config = {"prompt_templates": copy.deepcopy(TEMPLATES)}
                config["prompt_templates"]["b0_user" if baseline == "B0" else "b1_user"] = template
                with self.assertRaises(ContractError):
                    render_messages(config, baseline, "Synthetic question", [])
        with self.assertRaises(ContractError):
            render_messages({"prompt_templates": TEMPLATES}, "B0", "Synthetic question",
                            [{"doc_id": "synthetic-doc", "text": "Unexpected B0 evidence"}])
        with self.assertRaises(ContractError):
            render_messages({"prompt_templates": {**TEMPLATES, "system": " "}}, "B0", "Q", [])

    def test_prompt_hash_ignores_object_key_order_but_preserves_message_order_and_content(self):
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}]
        reordered_keys = [{"content": "S", "role": "system"}, {"content": "Q", "role": "user"}]
        self.assertEqual(prompt_sha256(messages), prompt_sha256(reordered_keys))
        self.assertNotEqual(prompt_sha256(messages), prompt_sha256(list(reversed(messages))))
        self.assertNotEqual(prompt_sha256(messages), prompt_sha256([
            messages[0], {"role": "user", "content": "Q changed"}]))


class ContractCLIControlsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="m3-contract-controls-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        runpy.run_path(str(FIXTURE_BUILDER))["build"](self.directory)

    def rows(self, name):
        return [json.loads(line) for line in (self.directory / name).read_text(encoding="utf-8").splitlines()]

    def write_rows(self, name, rows):
        (self.directory / name).write_bytes(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))

    def write_json(self, name, value):
        (self.directory / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def add_development_group(self):
        """One disjoint dev row belonging to the same rebuilt manifest."""
        manifest = load_json(self.directory / "manifest.json")
        ident = "synthetic-development-001"
        manifest["subsets"]["dev"] = {"ids": [ident], "count": 1}
        self.write_json("manifest.json", manifest)
        manifest_hash = hashlib.sha256((self.directory / "manifest.json").read_bytes()).hexdigest()
        for path in self.directory.glob("*.jsonl"):
            rows = self.rows(path.name)
            for row in rows:
                row["dataset_manifest_sha256"] = manifest_hash
            self.write_rows(path.name, rows)
        question = copy.deepcopy(self.rows("questions.jsonl")[0])
        question.update(subset="dev", interaction_id=ident, session_id="synthetic-development-session",
                        query="What is the separate synthetic development label?")
        metadata = copy.deepcopy(self.rows("metadata.jsonl")[0])
        metadata.update(subset="dev", interaction_id=ident, source_interaction_id=ident,
                        session_id=question["session_id"], image_group_id="synthetic-development-image")
        self.write_rows("other_questions.jsonl", [question])
        self.write_rows("other_metadata.jsonl", [metadata])

    def check(self, *extra):
        arguments = [sys.executable, "-X", "utf8", str(SCRIPT)]
        for kind in ("manifest", "questions", "answers", "metadata"):
            extension = ".json" if kind == "manifest" else ".jsonl"
            arguments.extend(["--" + kind, str(self.directory / (kind + extension))])
        report_path = self.directory / "report.json"
        arguments.extend([*extra, "--report", str(report_path)])
        result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", timeout=20)
        self.assertTrue(report_path.is_file(), result.stdout + result.stderr)
        return result, json.loads(report_path.read_text(encoding="utf-8"))

    def group_check(self):
        return self.check("--group-questions", str(self.directory / "other_questions.jsonl"),
                          "--group-metadata", str(self.directory / "other_metadata.jsonl"))

    def assert_group_failure(self, field):
        result, report = self.group_check()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertTrue(any(item["code"] == "group_overlap" and field in item["message"]
                            for item in report["errors"]), report)

    def test_complete_disjoint_cross_subset_grouping_is_valid(self):
        self.add_development_group()
        result, report = self.group_check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], report["errors"])
        self.assertFalse(any("Cross-subset" in item and "incomplete" in item
                             for item in report["unverified_checks"]), report)

    def test_same_session_cannot_cross_subsets(self):
        self.add_development_group()
        shared = self.rows("questions.jsonl")[0]["session_id"]
        for name in ("other_questions.jsonl", "other_metadata.jsonl"):
            rows = self.rows(name)
            rows[0]["session_id"] = shared
            self.write_rows(name, rows)
        self.assert_group_failure("session_id")

    def test_same_image_group_cannot_cross_subsets(self):
        self.add_development_group()
        rows = self.rows("other_metadata.jsonl")
        rows[0]["image_group_id"] = self.rows("metadata.jsonl")[0]["image_group_id"]
        self.write_rows("other_metadata.jsonl", rows)
        self.assert_group_failure("image_group_id")

    def test_duplicate_query_cannot_cross_subsets_after_case_and_whitespace_normalization(self):
        self.add_development_group()
        rows = self.rows("other_questions.jsonl")
        original = self.rows("questions.jsonl")[0]["query"]
        rows[0]["query"] = "  " + original.upper().replace(" ", "\t  ") + "\n"
        self.write_rows("other_questions.jsonl", rows)
        self.assert_group_failure("query")

    def test_cli_reconstructs_frozen_prompt_and_rejects_self_consistent_extra_content(self):
        config = load_json(self.directory / "generation.json")
        config["prompt_templates"] = copy.deepcopy(TEMPLATES)
        self.write_json("generation.json", config)
        requests = self.rows("requests_b0.jsonl")
        predictions = self.rows("predictions_b0.jsonl")
        questions = {row["interaction_id"]: row for row in self.rows("questions.jsonl")}
        for request, prediction in zip(requests, predictions):
            query = questions[request["interaction_id"]]["query"]
            messages = [{"role": "system", "content": TEMPLATES["system"]},
                        {"role": "user", "content": "Question: " + query}]
            request.update(messages=messages, prompt_sha256=prompt_sha256(messages))
            prediction.update(prompt_sha256=request["prompt_sha256"], generation_config_sha256=config_sha256(config))
        self.write_rows("requests_b0.jsonl", requests)
        self.write_rows("predictions_b0.jsonl", predictions)
        arguments = ("--predictions", str(self.directory / "predictions_b0.jsonl"),
                     "--requests", str(self.directory / "requests_b0.jsonl"),
                     "--config", "generation=" + str(self.directory / "generation.json"))
        result, report = self.check(*arguments)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(3, report["provenance"]["requests"]["template_reconstructed"])
        requests[0]["messages"][-1]["content"] += "\nUnapproved synthetic answer instruction."
        requests[0]["prompt_sha256"] = prompt_sha256(requests[0]["messages"])
        predictions[0]["prompt_sha256"] = requests[0]["prompt_sha256"]
        self.write_rows("requests_b0.jsonl", requests)
        self.write_rows("predictions_b0.jsonl", predictions)
        result, report = self.check(*arguments)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("request_content", {item["code"] for item in report["errors"]})


if __name__ == "__main__":
    unittest.main()
