"""Run provenance controls using explicitly synthetic, local files."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fixtures.synthetic.integration.build_fixture import build
from src.contracts.m3 import ContractError, config_sha256, file_sha256, render_messages


class RunMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m3-run-meta-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        build(self.directory)
        self.meta_path = self.directory / "run_meta_b0.json"
        config = json.loads((self.directory / "generation.json").read_text(encoding="utf-8"))
        self.meta = {
            "run_id": "synthetic-generation-B0", "stage": "generation", "subset": "smoke",
            "schema_version": "m3.v1", "baseline": "B0", "code_commit": "synthetic-test-code",
            "config": config, "config_sha256": config_sha256(config),
            "input_files_sha256": {name: file_sha256(self.directory / name)
                                   for name in ("manifest.json", "questions.jsonl")},
            "output_files_sha256": {"predictions_b0.jsonl": file_sha256(self.directory / "predictions_b0.jsonl")},
            "started_at": "2026-10-07T00:00:00+08:00", "finished_at": "2026-10-07T00:00:01+08:00",
            "hardware": {"notice": "synthetic test only"}, "N_expected": 3,
            "N_success": 3, "N_failed": 0, "retries": 0, "peak_memory_mb": None,
        }
        # Fixture's run ID is authoritative, independent of this test's template.
        pred = json.loads((self.directory / "predictions_b0.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.meta["run_id"] = pred["run_id"]

    def run_cli(self, *extra, expected=0, report_input=None):
        self.meta_path.write_bytes((json.dumps(self.meta, ensure_ascii=False) + "\n").encode("utf-8"))
        command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/check_artifacts.py")]
        for field, name in (("manifest", "manifest.json"), ("questions", "questions.jsonl"),
                            ("answers", "answers.jsonl"), ("metadata", "metadata.jsonl"),
                            ("predictions", "predictions_b0.jsonl")):
            command += [f"--{field}", str(self.directory / name)]
        command += ["--config", f"generation={self.directory / 'generation.json'}",
                    "--run-meta", f"{self.meta['stage']}={self.meta_path}"]
        if report_input:
            command += ["--report", str(self.directory / report_input)]
        result = subprocess.run(command + list(extra), cwd=ROOT, capture_output=True,
                                encoding="utf-8", timeout=20)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_code(self, code, **kwargs):
        report = self.run_cli(expected=1, **kwargs)
        self.assertIn(code, {error["code"] for error in report["errors"]})

    def test_valid_sidecar_is_linked_without_claiming_real_results(self):
        report = self.run_cli()
        self.assertTrue(report["valid"])
        self.assertEqual("synthetic_development", report["data_classification"])
        self.assertFalse(any("predictions: linked run metadata" in text for text in report["unverified_checks"]))

    def test_wrong_success_count_is_rejected(self):
        self.meta.update(N_success=2, N_failed=1)
        self.assert_code("run_meta_count")

    def test_wrong_output_file_is_rejected(self):
        self.meta["output_files_sha256"] = {"questions.jsonl": file_sha256(self.directory / "questions.jsonl")}
        self.assert_code("run_meta_output")

    def test_missing_question_input_hash_is_rejected(self):
        self.meta["input_files_sha256"].pop("questions.jsonl")
        self.assert_code("run_meta_input")

    def test_generation_must_not_read_answers(self):
        self.meta["input_files_sha256"]["answers.jsonl"] = file_sha256(self.directory / "answers.jsonl")
        self.assert_code("run_meta_answer_leakage")

    def test_embedded_config_hash_is_recomputed(self):
        self.meta["config"]["temperature"] = 0.5
        self.assert_code("run_meta_config")

    def test_finished_before_started_is_rejected(self):
        self.meta["finished_at"] = "2026-10-06T23:59:59+08:00"
        self.assert_code("run_meta_time")

    def test_relative_paths_are_resolved_at_sidecar_directory(self):
        self.run_cli()

    def test_secret_values_are_not_echoed(self):
        marker = "FAKE_CREDENTIAL_FOR_REDACTION_TEST_DO_NOT_USE"
        self.meta["api_key"] = marker
        report = self.run_cli(expected=1)
        self.assertNotIn(marker, json.dumps(report))
        self.assertIn("secret_keys", {error["code"] for error in report["errors"]})

    def test_report_cannot_overwrite_input(self):
        path = self.directory / "answers.jsonl"
        before = path.read_bytes()
        self.assert_code("report_path", report_input="answers.jsonl")
        self.assertEqual(before, path.read_bytes())

    def test_non_object_prompt_templates_fail_with_contract_error(self):
        with self.assertRaises(ContractError):
            render_messages({"prompt_templates": ["invalid"]}, "B0", "query", [])

    def test_scoring_requires_actual_prediction_input_hash(self):
        config = json.loads((self.directory / "evaluation.json").read_text(encoding="utf-8"))
        row = json.loads((self.directory / "scores_b0.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.meta.update(stage="evaluation", run_id=row["run_id"], config=config, config_sha256=config_sha256(config))
        self.meta["input_files_sha256"]["answers.jsonl"] = file_sha256(self.directory / "answers.jsonl")
        self.meta["output_files_sha256"] = {"scores_b0.jsonl": file_sha256(self.directory / "scores_b0.jsonl")}
        extra = ("--scores", str(self.directory / "scores_b0.jsonl"),
                 "--config", f"evaluation={self.directory / 'evaluation.json'}")
        report = self.run_cli(*extra, expected=1)
        self.assertIn("run_meta_stage_input", {item["code"] for item in report["errors"]})
        self.meta["input_files_sha256"]["predictions_b0.jsonl"] = file_sha256(self.directory / "predictions_b0.jsonl")
        self.run_cli(*extra)

    def test_b1_requires_actual_evidence_input_hash(self):
        row = json.loads((self.directory / "predictions_b1.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.meta.update(run_id=row["run_id"], baseline="B1")
        self.meta["output_files_sha256"] = {"predictions_b1.jsonl": file_sha256(self.directory / "predictions_b1.jsonl")}
        extra = ("--predictions", str(self.directory / "predictions_b1.jsonl"),
                 "--evidence", str(self.directory / "evidence.jsonl"))
        report = self.run_cli(*extra, expected=1)
        self.assertIn("run_meta_stage_input", {item["code"] for item in report["errors"]})
        self.meta["input_files_sha256"]["evidence.jsonl"] = file_sha256(self.directory / "evidence.jsonl")
        self.run_cli(*extra)

    def test_claimed_exact_match_must_match_reference_text(self):
        path = self.directory / "scores_b0.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["scoring_method"] = "exact_match"
        path.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode("utf-8"))
        report = self.run_cli("--scores", str(path), expected=1)
        self.assertIn("exact_match", {item["code"] for item in report["errors"]})

    def test_claimed_idk_must_match_official_abstention_rule(self):
        path = self.directory / "scores_b0.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0].update(scoring_method="idk", verdict="MISSING", score=0)
        path.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode("utf-8"))
        report = self.run_cli("--scores", str(path), expected=1)
        self.assertIn("idk", {item["code"] for item in report["errors"]})

    def test_baseline_comparison_cannot_hide_changed_user_templates(self):
        config = dict(self.meta["config"])
        config["prompt_templates"] = {"system": "Synthetic test only", "b0_user": "{query}",
                                      "b1_user": "{query}\nEvidence: {evidence}"}
        changed = {**config, "prompt_templates": {**config["prompt_templates"],
                                                  "b1_user": "Changed wrapper: {query}\n{evidence}"}}
        for baseline, cfg in (("b0", config), ("b1", changed)):
            cfg_name = "generation.json" if baseline == "b0" else "generation_b1.json"
            (self.directory / cfg_name).write_bytes(json.dumps(cfg).encode("utf-8"))
            path = self.directory / f"predictions_{baseline}.jsonl"
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                row["generation_config_sha256"] = config_sha256(cfg)
            path.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode("utf-8"))
        self.meta.update(config=config, config_sha256=config_sha256(config))
        self.meta["output_files_sha256"]["predictions_b0.jsonl"] = file_sha256(self.directory / "predictions_b0.jsonl")
        report = self.run_cli("--compare-predictions", str(self.directory / "predictions_b1.jsonl"),
                              "--evidence", str(self.directory / "evidence.jsonl"),
                              "--config", f"generation={self.directory / 'generation_b1.json'}", expected=1)
        self.assertIn("comparison_config", {item["code"] for item in report["errors"]})


if __name__ == "__main__":
    unittest.main()
