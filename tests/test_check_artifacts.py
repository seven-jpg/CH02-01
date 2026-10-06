"""Black-box behavior tests for A's checker, using only synthetic artifacts.

The subprocess invokes the public CLI instead of importing its implementation.
No API, model, dataset or index is used. Tests operate in temporary directories.
"""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "synthetic" / "integration"
SCRIPT = ROOT / "scripts" / "check_artifacts.py"
SCHEMA = ROOT / "docs" / "M2_M3_execution" / "接口字段.schema.json"


def canonical_hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ArtifactCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m3-synthetic-check-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        # Rebuild byte hashes in isolation: Git line-ending conversion must not
        # make a structurally valid fixture appear corrupt on another platform.
        runpy.run_path(str(FIXTURE / "build_fixture.py"))["build"](self.directory)

    def rows(self, name):
        return [json.loads(line) for line in (self.directory / name).read_text(encoding="utf-8").splitlines()]

    def write_rows(self, name, rows):
        (self.directory / name).write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def change_row(self, name, change, index=0):
        rows = self.rows(name)
        change(rows[index])
        self.write_rows(name, rows)

    def write_json(self, name, value):
        (self.directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def refresh_manifest_hash(self):
        value = hashlib.sha256((self.directory / "manifest.json").read_bytes()).hexdigest()
        for path in self.directory.glob("*.jsonl"):
            rows = self.rows(path.name)
            for row in rows:
                row["dataset_manifest_sha256"] = value
            self.write_rows(path.name, rows)

    def run_checker(self, *, baseline=None, scores=False, evidence=False, requests=False,
                    compare=False, compare_scores=False, batch=False, extra=()):
        args = [sys.executable, "-X", "utf8", str(SCRIPT)]
        for option in ("manifest", "questions", "answers", "metadata"):
            suffix = ".json" if option == "manifest" else ".jsonl"
            args += ["--" + option, str(self.directory / (option + suffix))]
        if baseline:
            args += ["--predictions", str(self.directory / f"predictions_{baseline}.jsonl")]
        if scores:
            args += ["--scores", str(self.directory / f"scores_{baseline}.jsonl")]
        if evidence:
            args += ["--evidence", str(self.directory / "evidence.jsonl")]
        if requests:
            args += ["--requests", str(self.directory / f"requests_{baseline}.jsonl")]
        if compare:
            args += ["--compare-predictions", str(self.directory / "predictions_b1.jsonl")]
        if compare_scores:
            args += ["--compare-scores", str(self.directory / "scores_b1.jsonl")]
        if batch:
            args += ["--batch-ids", str(self.directory / "batch_ids.json")]
        args += list(extra)
        report_path = self.directory / "report.json"
        args += ["--report", str(report_path)]
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertTrue(report_path.is_file(), f"No JSON report. code={result.returncode}\n{result.stdout}\n{result.stderr}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertIsInstance(report.get("valid"), bool)
        self.assertIsInstance(report.get("errors"), list)
        self.assertIsInstance(report.get("warnings"), list)
        self.assertIsInstance(report.get("counts"), dict)
        self.assertIn("paired_comparison", report)
        for item in report["errors"]:
            self.assertIsInstance(item, dict)
            self.assertIn("code", item)
            self.assertIn("message", item)
        return result, report

    def assert_exit(self, expected, **kwargs):
        result, report = self.run_checker(**kwargs)
        self.assertEqual(expected, result.returncode, f"{result.stdout}\n{result.stderr}\n{json.dumps(report, ensure_ascii=False, indent=2)}")
        if expected == 0:
            self.assertTrue(report["valid"])
            self.assertEqual([], report["errors"])
        elif expected == 1:
            self.assertFalse(report["valid"])
            self.assertTrue(report["errors"])
        return report

    def update_request_hash(self, baseline="b0", index=0):
        rows = self.rows(f"requests_{baseline}.jsonl")
        rows[index]["prompt_sha256"] = canonical_hash(rows[index]["messages"])
        self.write_rows(f"requests_{baseline}.jsonl", rows)
        self.change_row(f"predictions_{baseline}.jsonl",
                        lambda row: row.update(prompt_sha256=rows[index]["prompt_sha256"]), index)

    def mark_generation_error(self, baseline="b0", index=0):
        self.change_row(f"predictions_{baseline}.jsonl", lambda row: row.update(
            generation_status="error", agent_response=None, error_code="SYNTHETIC_TIMEOUT"), index)

    def mark_unscored(self, baseline="b0", index=0):
        self.change_row(f"scores_{baseline}.jsonl", lambda row: row.update(
            judge_status="unscored", verdict=None, score=None, agent_response_scored=None,
            scoring_method="unscored", error_code="SYNTHETIC_GENERATION_FAILED"), index)

    def test_fixture_matches_published_row_schemas(self):
        import jsonschema
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        for definition, names in {
            "questions": ["questions.jsonl"], "answers": ["answers.jsonl"],
            "metadata": ["metadata.jsonl"], "evidence": ["evidence.jsonl"],
            "predictions": ["predictions_b0.jsonl", "predictions_b1.jsonl"],
            "scores": ["scores_b0.jsonl", "scores_b1.jsonl"],
            "requests": ["requests_b0.jsonl", "requests_b1.jsonl"],
        }.items():
            validator = jsonschema.Draft202012Validator({
                "$schema": schema["$schema"], "$defs": schema["$defs"],
                "$ref": "#/$defs/" + definition,
            })
            for name in names:
                for row in self.rows(name):
                    with self.subTest(name=name, interaction_id=row["interaction_id"]):
                        validator.validate(row)

    def test_complete_data_package(self):
        self.assert_exit(0)

    def test_complete_b0_predictions_and_scores(self):
        self.assert_exit(0, baseline="b0", scores=True)

    def test_complete_b1_with_evidence(self):
        self.assert_exit(0, baseline="b1", scores=True, evidence=True)

    def test_pair_baselines_by_id(self):
        report = self.assert_exit(0, baseline="b0", scores=True, compare=True, compare_scores=True, evidence=True)
        self.assertIsInstance(report["paired_comparison"], dict)

    def test_row_order_is_not_alignment(self):
        names = ["questions.jsonl", "answers.jsonl", "metadata.jsonl", "evidence.jsonl",
                 "predictions_b0.jsonl", "scores_b0.jsonl", "predictions_b1.jsonl", "scores_b1.jsonl"]
        for i, name in enumerate(names):
            rows = self.rows(name)
            shift = i % len(rows)
            self.write_rows(name, rows[shift:] + rows[:shift])
        self.assert_exit(0, baseline="b0", scores=True, compare=True, compare_scores=True, evidence=True)

    def test_duplicate_id_is_rejected(self):
        self.write_rows("answers.jsonl", self.rows("answers.jsonl") + self.rows("answers.jsonl")[:1])
        self.assert_exit(1)

    def test_missing_row_is_rejected(self):
        self.write_rows("metadata.jsonl", self.rows("metadata.jsonl")[1:])
        self.assert_exit(1)

    def test_unexpected_id_is_rejected(self):
        self.change_row("answers.jsonl", lambda row: row.update(interaction_id="unexpected-synthetic-id"))
        self.assert_exit(1)

    def test_subset_disagreement_is_rejected(self):
        self.change_row("answers.jsonl", lambda row: row.update(subset="eval"))
        self.assert_exit(1)

    def test_manifest_original_bytes_are_hashed(self):
        path = self.directory / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        self.assert_exit(1)

    def test_manifest_count_disagreement_is_rejected(self):
        manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        manifest["subsets"]["smoke"]["count"] = 2
        self.write_json("manifest.json", manifest)
        self.refresh_manifest_hash()
        self.assert_exit(1)

    def test_manifest_subset_overlap_is_rejected(self):
        manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        manifest["subsets"]["dev"] = {"ids": ["synthetic-001"], "count": 1}
        self.write_json("manifest.json", manifest)
        self.refresh_manifest_hash()
        self.assert_exit(1)

    def test_mutable_dataset_revision_is_rejected(self):
        manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        manifest["revision"] = "main"
        self.write_json("manifest.json", manifest)
        self.refresh_manifest_hash()
        self.assert_exit(1)

    def test_dataset_revision_must_be_exactly_40_or_64_hex_digits(self):
        manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        manifest["revision"] = "a" * 41
        self.write_json("manifest.json", manifest)
        rows = self.rows("metadata.jsonl")
        for row in rows:
            row["source_revision"] = manifest["revision"]
        self.write_rows("metadata.jsonl", rows)
        self.refresh_manifest_hash()
        self.assert_exit(1)

    def test_query_hash_mismatch_is_rejected(self):
        self.change_row("predictions_b0.jsonl", lambda row: row.update(query_sha256="a" * 64))
        self.assert_exit(1, baseline="b0")

    def test_metadata_session_must_match_question(self):
        self.change_row("metadata.jsonl", lambda row: row.update(session_id="different-synthetic-session"))
        self.assert_exit(1)

    def test_metadata_source_revision_must_match_manifest(self):
        self.change_row("metadata.jsonl", lambda row: row.update(source_revision="a" * 40))
        self.assert_exit(1)

    def test_query_text_changed_without_downstream_refresh_is_rejected(self):
        self.change_row("questions.jsonl", lambda row: row.update(query=row["query"] + " changed"))
        self.assert_exit(1, baseline="b0")

    def test_question_cannot_contain_answer_field(self):
        self.change_row("questions.jsonl", lambda row: row.update(ground_truth="reference answer"))
        self.assert_exit(1)

    def test_bad_json_is_rejected(self):
        (self.directory / "answers.jsonl").write_text('{"broken":\n', encoding="utf-8")
        self.assert_exit(1)

    def test_utf8_bom_is_rejected(self):
        path = self.directory / "answers.jsonl"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.assert_exit(1)

    def test_nan_is_rejected(self):
        self.change_row("evidence.jsonl", lambda row: row.update(latency_ms=float("nan")))
        self.assert_exit(1, evidence=True)

    def test_json_number_overflow_to_infinity_is_rejected(self):
        path = self.directory / "evidence.jsonl"
        source = path.read_text(encoding="utf-8")
        self.assertIn('"latency_ms":null', source)
        path.write_text(source.replace('"latency_ms":null', '"latency_ms":1e999', 1), encoding="utf-8")
        self.assert_exit(1, evidence=True)

    def test_unpaired_json_unicode_surrogate_is_rejected(self):
        path = self.directory / "answers.jsonl"
        source = path.read_text(encoding="utf-8")
        path.write_text(source.replace("reference-answer-marker-001", "\\ud800", 1), encoding="utf-8")
        self.assert_exit(1)

    def test_batch_filters_full_data_inputs(self):
        ids = set(json.loads((self.directory / "batch_ids.json").read_text(encoding="utf-8")))
        for name in ["evidence.jsonl", "predictions_b0.jsonl", "scores_b0.jsonl"]:
            self.write_rows(name, [row for row in self.rows(name) if row["interaction_id"] in ids])
        self.assert_exit(0, baseline="b0", scores=True, evidence=True, batch=True)

    def test_200_full_data_rows_with_20_batch_predictions_have_no_180_missing_error(self):
        runpy.run_path(str(FIXTURE / "build_fixture.py"))["build"](
            self.directory, count=200, subset="eval", batch_count=20)
        ids = set(json.loads((self.directory / "batch_ids.json").read_text(encoding="utf-8")))
        for name in ["evidence.jsonl", "predictions_b0.jsonl", "scores_b0.jsonl"]:
            self.write_rows(name, [row for row in self.rows(name) if row["interaction_id"] in ids])
        report = self.assert_exit(0, baseline="b0", scores=True, evidence=True, batch=True)
        self.assertEqual(20, len(report["expected_ids"]))
        self.assertEqual("eval", report["subset"])
        self.assertEqual("batch", report["scope"])

    def test_batch_cannot_filter_out_unknown_extra_data_input_id(self):
        ids = set(json.loads((self.directory / "batch_ids.json").read_text(encoding="utf-8")))
        self.write_rows("predictions_b0.jsonl", [row for row in self.rows("predictions_b0.jsonl")
                                              if row["interaction_id"] in ids])
        self.change_row("answers.jsonl", lambda row: row.update(interaction_id="unknown-synthetic-id"), index=1)
        report = self.assert_exit(1, baseline="b0", batch=True)
        self.assertIn("unexpected_id", {item["code"] for item in report["errors"]})

    def test_partial_file_without_batch_is_rejected(self):
        self.write_rows("predictions_b0.jsonl", self.rows("predictions_b0.jsonl")[:2])
        self.assert_exit(1, baseline="b0")

    def test_batch_output_cannot_include_nonbatch_id(self):
        self.assert_exit(1, baseline="b0", batch=True)

    def test_batch_duplicate_ids_are_rejected(self):
        self.write_json("batch_ids.json", ["synthetic-001", "synthetic-001"])
        self.assert_exit(1, batch=True)

    def test_batch_unknown_ids_are_rejected(self):
        self.write_json("batch_ids.json", ["synthetic-001", "unknown"])
        self.assert_exit(1, batch=True)

    def test_successful_empty_retrieval_is_valid(self):
        self.change_row("evidence.jsonl", lambda row: row.update(retrieval_status="empty", hits=[]))
        self.change_row("predictions_b1.jsonl", lambda row: row.update(evidence_status="empty"))
        self.assert_exit(0, baseline="b1", evidence=True)

    def test_empty_retrieval_cannot_hide_error_code(self):
        self.change_row("evidence.jsonl", lambda row: row.update(retrieval_status="empty", hits=[], error_code="SYNTHETIC_TIMEOUT"))
        self.assert_exit(1, evidence=True)

    def test_retrieval_error_is_technical_failure(self):
        self.change_row("evidence.jsonl", lambda row: row.update(retrieval_status="error", hits=[], error_code="SYNTHETIC_TIMEOUT"))
        self.assert_exit(2, evidence=True)

    def test_b1_blocks_retrieval_error_and_e_leaves_unscored(self):
        self.change_row("evidence.jsonl", lambda row: row.update(retrieval_status="error", hits=[], error_code="SYNTHETIC_TIMEOUT"))
        self.change_row("predictions_b1.jsonl", lambda row: row.update(
            generation_status="blocked", agent_response=None, evidence_status="error",
            prompt_sha256=None, error_code="SYNTHETIC_RETRIEVAL_ERROR"))
        self.mark_unscored("b1")
        self.assert_exit(2, baseline="b1", scores=True, evidence=True)

    def test_b1_cannot_generate_after_retrieval_error(self):
        self.change_row("evidence.jsonl", lambda row: row.update(retrieval_status="error", hits=[], error_code="SYNTHETIC_TIMEOUT"))
        self.assert_exit(1, baseline="b1", evidence=True)

    def test_normal_idk_is_a_valid_generation(self):
        self.change_row("predictions_b0.jsonl", lambda row: row.update(agent_response="I don't know."))
        self.assert_exit(0, baseline="b0")

    def test_api_failure_remains_error(self):
        self.mark_generation_error()
        self.assert_exit(2, baseline="b0")

    def test_api_failure_cannot_be_replaced_with_idk(self):
        self.mark_generation_error()
        self.change_row("predictions_b0.jsonl", lambda row: row.update(agent_response="I don't know."))
        self.assert_exit(1, baseline="b0")

    def test_failed_generation_is_unscored(self):
        self.mark_generation_error()
        self.mark_unscored()
        self.assert_exit(2, baseline="b0", scores=True)

    def test_technical_failure_does_not_invalidate_structure(self):
        self.mark_generation_error()
        self.mark_unscored()
        report = self.assert_exit(2, baseline="b0", scores=True)
        self.assertTrue(report["valid"])
        self.assertEqual([], report["errors"])

    def test_paired_comparison_uses_common_scored_ids(self):
        self.mark_generation_error("b1")
        self.mark_unscored("b1")
        report = self.assert_exit(2, baseline="b0", scores=True, compare=True,
                                  compare_scores=True, evidence=True)
        paired = report["paired_comparison"]
        self.assertEqual(2, paired["n_common_scored"])
        self.assertEqual({"synthetic-002", "synthetic-003"}, set(paired["common_ids"]))
        self.assertEqual(0, paired["accuracy_delta"])
        self.assertEqual(0, paired["truthfulness_delta"])

    def test_failed_generation_cannot_be_scored_wrong(self):
        self.mark_generation_error()
        self.change_row("scores_b0.jsonl", lambda row: row.update(verdict="WRONG", score=-1))
        self.assert_exit(1, baseline="b0", scores=True)

    def test_judge_failure_is_technical_failure(self):
        self.change_row("scores_b0.jsonl", lambda row: row.update(
            judge_status="error", verdict=None, score=None, scoring_method="llm",
            judge_model="synthetic-judge", error_code="SYNTHETIC_JUDGE_TIMEOUT"))
        self.assert_exit(2, baseline="b0", scores=True)

    def test_judge_failure_cannot_be_wrong(self):
        self.change_row("scores_b0.jsonl", lambda row: row.update(
            judge_status="error", verdict="WRONG", score=-1,
            error_code="SYNTHETIC_JUDGE_TIMEOUT"))
        self.assert_exit(1, baseline="b0", scores=True)

    def test_verdict_score_disagreement_is_rejected(self):
        self.change_row("scores_b0.jsonl", lambda row: row.update(verdict="CORRECT", score=-1))
        self.assert_exit(1, baseline="b0", scores=True)

    def test_scoring_source_generation_run_must_match(self):
        self.change_row("scores_b0.jsonl", lambda row: row.update(source_generation_run_id="other-synthetic-run"))
        self.assert_exit(1, baseline="b0", scores=True)

    def test_configuration_cannot_drift_within_one_file(self):
        self.change_row("predictions_b0.jsonl", lambda row: row.update(generation_config_sha256="a" * 64))
        self.assert_exit(1, baseline="b0")

    def test_compare_baselines_cannot_use_different_models(self):
        rows = self.rows("predictions_b1.jsonl")
        for row in rows:
            row["model"] = "different-synthetic-model"
        self.write_rows("predictions_b1.jsonl", rows)
        self.assert_exit(1, baseline="b0", compare=True, evidence=True)

    def test_compare_baselines_cannot_use_different_configurations(self):
        config = json.loads((self.directory / "generation.json").read_text(encoding="utf-8"))
        config["temperature"] = 0.5
        self.write_json("generation_b1.json", config)
        rows = self.rows("predictions_b1.jsonl")
        for row in rows:
            row["generation_config_sha256"] = canonical_hash(config)
        self.write_rows("predictions_b1.jsonl", rows)
        report = self.assert_exit(1, baseline="b0", compare=True, evidence=True, extra=(
            "--config", "generation=" + str(self.directory / "generation.json"),
            "--config", "generation=" + str(self.directory / "generation_b1.json")))
        self.assertIn("comparison_config", {item["code"] for item in report["errors"]})

    def test_compare_config_hashes_without_actual_configs_remain_unverified(self):
        rows = self.rows("predictions_b1.jsonl")
        for row in rows:
            row["generation_config_sha256"] = "a" * 64
        self.write_rows("predictions_b1.jsonl", rows)
        report = self.assert_exit(0, baseline="b0", compare=True, evidence=True)
        messages = json.dumps(report.get("unverified_checks", []) + report["warnings"], ensure_ascii=False).lower()
        self.assertIn("common generation", messages)

    def test_distinct_baseline_specific_configs_with_same_common_settings_are_valid(self):
        config = json.loads((self.directory / "generation.json").read_text(encoding="utf-8"))
        config.update(baseline="B1", evidence_budget_tokens=1500)
        self.write_json("generation_b1.json", config)
        rows = self.rows("predictions_b1.jsonl")
        for row in rows:
            row["generation_config_sha256"] = canonical_hash(config)
        self.write_rows("predictions_b1.jsonl", rows)
        self.assert_exit(0, baseline="b0", compare=True, evidence=True, extra=(
            "--config", "generation=" + str(self.directory / "generation.json"),
            "--config", "generation=" + str(self.directory / "generation_b1.json")))

    def test_paired_metrics_use_correct_wrong_missing_denominator(self):
        self.change_row("scores_b0.jsonl", lambda row: row.update(verdict="WRONG", score=-1), index=1)
        for name in ("scores_b0.jsonl", "scores_b1.jsonl"):
            self.change_row(name, lambda row: row.update(verdict="MISSING", score=0), index=2)
        report = self.assert_exit(0, baseline="b0", scores=True, compare=True,
                                  compare_scores=True, evidence=True)
        paired = report["paired_comparison"]
        self.assertEqual(3, paired["n_common_scored"])
        self.assertAlmostEqual(1 / 3, paired["accuracy_delta"])
        self.assertAlmostEqual(2 / 3, paired["truthfulness_delta"])

    def test_compare_baselines_require_same_id_set(self):
        self.write_rows("predictions_b1.jsonl", self.rows("predictions_b1.jsonl")[1:])
        self.assert_exit(1, baseline="b0", compare=True, evidence=True)

    def test_omitted_requests_emit_unverified_warning(self):
        report = self.assert_exit(0, baseline="b0")
        serialized = json.dumps(report.get("unverified_checks", []) + report["warnings"], ensure_ascii=False).lower()
        self.assertTrue(any(word in serialized for word in ["request", "provenance", "请求", "来源"]), serialized)

    def test_complete_requests_without_templates_are_not_false_proof(self):
        report = self.assert_exit(0, baseline="b0", requests=True)
        messages = json.dumps(report.get("unverified_checks", []) + report["warnings"], ensure_ascii=False).lower()
        self.assertIn("template", messages, "No prompt template was supplied; provenance is still unverified.")

    def test_request_prompt_hash_matches_canonical_messages(self):
        self.change_row("requests_b0.jsonl", lambda row: row["messages"][-1].update(content="changed synthetic input"))
        self.assert_exit(1, baseline="b0", requests=True)

    def test_request_original_query_cannot_be_rewritten(self):
        self.change_row("requests_b0.jsonl", lambda row: row["messages"][-1].update(content="completely different question"))
        self.update_request_hash()
        self.assert_exit(1, baseline="b0", requests=True)

    def test_request_cannot_omit_common_metadata(self):
        self.change_row("requests_b0.jsonl", lambda row: row.pop("dataset_manifest_sha256"))
        self.assert_exit(1, baseline="b0", requests=True)

    def test_request_run_id_must_match_prediction(self):
        self.change_row("requests_b0.jsonl", lambda row: row.update(run_id="other-synthetic-run"))
        self.assert_exit(1, baseline="b0", requests=True)

    def test_request_images_are_rejected_even_with_consistent_hash(self):
        self.change_row("requests_b0.jsonl", lambda row: row["messages"].append(
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.invalid/image.png"}}]}))
        self.update_request_hash()
        self.assert_exit(1, baseline="b0", requests=True)

    def test_request_assistant_history_is_rejected(self):
        self.change_row("requests_b0.jsonl", lambda row: row["messages"].insert(
            1, {"role": "assistant", "content": "Synthetic prior answer"}))
        self.update_request_hash()
        self.assert_exit(1, baseline="b0", requests=True)

    def test_b0_request_cannot_use_retrieved_evidence(self):
        self.change_row("requests_b0.jsonl", lambda row: row.update(
            evidence_used=[{"doc_id": "synthetic-document-1", "text": "Synthetic fixture evidence number 1."}]))
        self.assert_exit(1, baseline="b0", requests=True)

    def test_b1_evidence_used_must_be_traceable(self):
        self.change_row("requests_b1.jsonl", lambda row: row.update(
            evidence_used=[{"doc_id": "synthetic-document-1", "text": "untraceable synthetic invented evidence"}]))
        self.assert_exit(1, baseline="b1", requests=True, evidence=True)

    def test_reference_answer_in_legitimate_retrieved_text_is_not_leak_proof(self):
        text = "Synthetic source says reference-answer-marker-001."
        self.change_row("evidence.jsonl", lambda row: row["hits"][0].update(text=text))
        query = self.rows("questions.jsonl")[0]["query"]
        def change_request(row):
            row["evidence_used"][0]["text"] = text
            row["messages"][-1]["content"] = query + "\nRetrieved evidence:\n" + text
        self.change_row("requests_b1.jsonl", change_request)
        self.update_request_hash("b1")
        self.assert_exit(0, baseline="b1", requests=True, evidence=True)

    def test_help_is_standalone(self):
        result = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), "--help"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--manifest", result.stdout)
        self.assertIn("--batch-ids", result.stdout)


if __name__ == "__main__":
    unittest.main()
