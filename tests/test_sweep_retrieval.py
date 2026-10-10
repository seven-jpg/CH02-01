"""Synthetic sweep boundary checks. Every fixture lives in a temporary tmp_path."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import sweep_retrieval as sweep
from src.contracts.m3 import config_sha256, file_sha256, query_sha256


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="m3-sweep-test-")
        self.addCleanup(self.temporary.cleanup)
        self.tmp_path = Path(self.temporary.name)
        self.manifest_path = self.tmp_path / "manifest.json"
        self.questions_path = self.tmp_path / "questions with space & apostrophe's.jsonl"
        self.config_path = self.tmp_path / "retrieval.json"
        self.output = self.tmp_path / "prepared"
        self.manifest = {"schema_version": "m3.v1", "data_origin": "official",
            "dataset_id": "crag-mm-2025/crag-mm-single-turn-public", "revision": "a" * 40,
            "split": "validation", "seed": 42, "fixture_notice": "synthetic development only",
            "subsets": {"smoke": {"ids": ["smoke-1"], "count": 1},
                        "dev": {"ids": ["dev-1", "dev-2", "dev-3"], "count": 3},
                        "eval": {"ids": ["eval-1"], "count": 1}}}
        self.write_json(self.manifest_path, self.manifest)
        self.questions = [{"schema_version": "m3.v1", "subset": "dev", "interaction_id": ident,
            "dataset_manifest_sha256": file_sha256(self.manifest_path),
            "session_id": ident + "-session", "query": "Synthetic query " + ident}
            for ident in self.manifest["subsets"]["dev"]["ids"]]
        self.write_rows(self.questions_path, self.questions)
        self.config = {"top_k": 5, "index_repo": "synthetic/index", "index_revision": "b" * 40,
            "encoder_id": "synthetic/encoder", "encoder_revision": "c" * 40,
            "index_cache_dir": "D:\\unavailable\\C-machine-index"}
        self.write_json(self.config_path, self.config)

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def write_rows(path, rows):
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def arguments(self, *extra):
        return ["--manifest", str(self.manifest_path), "--questions", str(self.questions_path),
                "--config", str(self.config_path), "--output-dir", str(self.output), *extra]

    def call(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return sweep.main(self.arguments(*extra))

    def test_default_prepares_three_independent_candidates_without_running(self):
        source = self.config_path.read_bytes()
        with patch.object(sweep.subprocess, "run") as child, patch.object(sweep.importlib.util, "find_spec") as modules:
            self.assertEqual(self.call(), 0)
        child.assert_not_called()
        modules.assert_not_called()
        plan = json.loads((self.output / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual([row["top_k"] for row in plan["variants"]], [1, 3, 5])
        self.assertEqual(plan["N_expected"], 3)
        self.assertIsNone(plan["optimal_top_k"])
        self.assertEqual(plan["answer_quality_evaluation"], "not_run")
        self.assertEqual(self.config_path.read_bytes(), source)
        for variant in plan["variants"]:
            config = json.loads(Path(variant["config_path"]).read_text(encoding="utf-8"))
            self.assertEqual(config["top_k"], variant["top_k"])
            self.assertFalse(Path(variant["evidence_path"]).exists())
            self.assertEqual(variant["command"][0], sys.executable)
            self.assertIn(str(self.questions_path), variant["command"])
            self.assertIn("apostrophe''s", variant["powershell_command"])
            self.assertTrue(variant["powershell_command"].startswith("& '"))

    def test_same_preparation_preserves_files_and_existing_results(self):
        self.assertEqual(self.call(), 0)
        result = self.output / "top_k_1" / "evidence.jsonl"
        result.write_bytes(b"old result, not an experiment fixture\n")
        files = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.output.rglob("*") if path.is_file()}
        self.assertEqual(self.call(), 0)
        self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}, files)

    def test_different_preparation_is_not_overwritten(self):
        self.assertEqual(self.call(), 0)
        original = (self.output / "plan.json").read_bytes()
        self.assertEqual(self.call("--top-k", "1", "5"), 1)
        self.assertEqual((self.output / "plan.json").read_bytes(), original)

    def test_config_conflict_is_detected_before_any_new_file(self):
        target = self.output / "top_k_3"
        target.mkdir(parents=True)
        (target / "retrieval.json").write_text("different", encoding="utf-8")
        self.assertEqual(self.call(), 1)
        self.assertFalse((self.output / "top_k_1").exists())

    def test_invalid_candidates_and_timeout(self):
        for extra in (("--top-k", "0"), ("--top-k", "-1"), ("--top-k", "1", "1"), ("--timeout-seconds", "0")):
            with self.subTest(extra=extra):
                self.assertEqual(self.call(*extra), 1)
        self.assertFalse(self.output.exists())

    def test_eval_and_extra_leaking_fields_are_rejected(self):
        for field, value in (("subset", "eval"), ("ground_truth", "forbidden"), ("image_url", "forbidden")):
            with self.subTest(field=field):
                rows = [dict(row) for row in self.questions]
                rows[0][field] = value
                self.write_rows(self.questions_path, rows)
                self.assertEqual(self.call(), 1)
        self.assertFalse(self.output.exists())

    def test_missing_duplicate_unknown_ids_and_wrong_hash_are_rejected(self):
        variants = [self.questions[:-1], self.questions + [self.questions[0]],
                    [{**self.questions[0], "interaction_id": "eval-1"}, *self.questions[1:]],
                    [{**self.questions[0], "dataset_manifest_sha256": "d" * 64}, *self.questions[1:]]]
        for rows in variants:
            with self.subTest(rows=len(rows)):
                self.write_rows(self.questions_path, rows)
                self.assertEqual(self.call(), 1)

    def test_manifest_counts_overlap_and_mutable_revision_are_rejected(self):
        for change in ("count", "overlap", "revision", "empty"):
            manifest = json.loads(json.dumps(self.manifest))
            if change == "count":
                manifest["subsets"]["dev"]["count"] = True
            elif change == "overlap":
                manifest["subsets"]["eval"] = {"ids": ["dev-1"], "count": 1}
            elif change == "revision":
                manifest["revision"] = "main"
            else:
                manifest["subsets"]["dev"] = {"ids": [], "count": 0}
            self.write_json(self.manifest_path, manifest)
            self.assertEqual(self.call(), 1)

    def test_fetch_k_and_credentials_are_rejected(self):
        for extra in ({"fetch_k": 10}, {"nested": {"fetch_k": 10}}, {"api_key": "synthetic-secret-marker"}):
            self.write_json(self.config_path, {**self.config, **extra})
            self.assertEqual(self.call(), 1)

    def test_help_does_not_import_heavy_modules(self):
        code = ("import runpy,sys\n"
                "sys.argv=['sweep_retrieval.py','--help']\n"
                "try:\n"
                f"    runpy.run_path({str(ROOT / 'scripts/sweep_retrieval.py')!r},run_name='__main__')\n"
                "except SystemExit as exc:\n"
                "    assert exc.code == 0\n"
                "assert not {'torch','transformers','chromadb','cragmm_search'} & set(sys.modules)\n"
                "print('HEAVY_IMPORTS_ABSENT')")
        result = subprocess.run([sys.executable, "-B", "-c", code],
                                capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--run", result.stdout)
        self.assertIn("HEAVY_IMPORTS_ABSENT", result.stdout)
        self.assertFalse(self.output.exists())

    def local_index(self):
        path = self.tmp_path / "local index"
        path.mkdir()
        (path / "chroma.sqlite3").write_bytes(b"synthetic placeholder: never opened")
        return path

    def test_run_checks_missing_index_before_dependencies(self):
        with patch.object(sweep.importlib.util, "find_spec") as modules, patch.object(sweep.subprocess, "run") as child:
            self.assertEqual(self.call("--run", "--index-path", str(self.tmp_path / "missing")), 1)
        modules.assert_not_called()
        child.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_run_checks_missing_dependencies(self):
        index = self.local_index()
        with patch.object(sweep.importlib.util, "find_spec", return_value=None), patch.object(sweep.subprocess, "run") as child:
            self.assertEqual(self.call("--run", "--index-path", str(index)), 1)
        child.assert_not_called()
        self.assertFalse(self.output.exists())

    def fake_child(self, command, **kwargs):
        def argument(name):
            return Path(command[command.index(name) + 1])
        config = json.loads(argument("--config").read_text(encoding="utf-8"))
        digest = config_sha256(config)
        manifest_hash = file_sha256(self.manifest_path)
        run_id = f"retrieval-dev-{digest[:12]}-{manifest_hash[:8]}"
        rows = [{"schema_version": "m3.v1", "subset": "dev", "interaction_id": question["interaction_id"],
            "dataset_manifest_sha256": manifest_hash, "query_sha256": query_sha256(question["query"]),
            "run_id": run_id, "retrieval_status": "empty", "retrieval_config_sha256": digest,
            "index_revision": config["index_revision"], "encoder_revision": config["encoder_revision"],
            "latency_ms": 1, "error_code": None, "hits": []} for question in self.questions]
        self.write_rows(argument("--output"), rows)
        self.write_json(argument("--run-meta"), {"schema_version": "m3.v1", "stage": "retrieval", "subset": "dev",
            "run_id": run_id, "config_sha256": digest, "config": config, "N_expected": 3, "N_success": 3,
            "N_failed": 0, "input_files_sha256": {"manifest": manifest_hash, "questions": file_sha256(self.questions_path)},
            "output_files_sha256": {"evidence": file_sha256(argument("--output"))}})
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["timeout"], 3600)
        return subprocess.CompletedProcess(command, 0, "synthetic child only", "")

    def test_run_is_sequential_uses_safe_argv_and_does_not_select_winner(self):
        index = self.local_index()
        candidates = []
        def child(command, **kwargs):
            candidates.append(json.loads(Path(command[command.index("--config") + 1]).read_text())["top_k"])
            self.assertEqual(command[command.index("--index-path") + 1], str(index.resolve()))
            return self.fake_child(command, **kwargs)
        with patch.object(sweep.importlib.util, "find_spec", return_value=object()), patch.object(sweep.subprocess, "run", side_effect=child):
            self.assertEqual(self.call("--run", "--index-path", str(index)), 0)
        self.assertEqual(candidates, [1, 3, 5])
        execution = json.loads((self.output / "execution.json").read_text())
        self.assertEqual(execution["status"], "retrieval_complete")
        self.assertIsNone(execution["optimal_top_k"])
        self.assertEqual(execution["answer_quality_evaluation"], "not_run")

    def test_zero_exit_with_empty_evidence_is_not_success(self):
        index = self.local_index()
        def child(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(b"")
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(sweep.importlib.util, "find_spec", return_value=object()), patch.object(sweep.subprocess, "run", side_effect=child) as run:
            self.assertEqual(self.call("--run", "--index-path", str(index)), 2)
        self.assertEqual(run.call_count, 1)
        execution = json.loads((self.output / "execution.json").read_text())
        self.assertEqual(execution["status"], "failed")
        self.assertEqual(execution["not_run_top_k"], [3, 5])

    def test_nonzero_or_timeout_stops_without_claiming_success(self):
        index = self.local_index()
        for timeout in (False, True):
            self.output = self.tmp_path / ("timeout" if timeout else "nonzero")
            effect = subprocess.TimeoutExpired(["synthetic"], 3600) if timeout else None
            with patch.object(sweep.importlib.util, "find_spec", return_value=object()), patch.object(sweep.subprocess, "run",
                              side_effect=effect, return_value=subprocess.CompletedProcess([], 2, "", "")) as run:
                self.assertEqual(self.call("--run", "--index-path", str(index)), 2)
                self.assertEqual(run.call_count, 1)

    def test_run_never_overwrites_previous_results(self):
        index = self.local_index()
        self.assertEqual(self.call("--index-path", str(index)), 0)
        evidence = self.output / "top_k_1" / "evidence.jsonl"
        evidence.write_bytes(b"preserve me")
        with patch.object(sweep.importlib.util, "find_spec", return_value=object()), patch.object(sweep.subprocess, "run") as run:
            self.assertEqual(self.call("--run", "--index-path", str(index)), 1)
        run.assert_not_called()
        self.assertEqual(evidence.read_bytes(), b"preserve me")


if __name__ == "__main__":
    unittest.main()
