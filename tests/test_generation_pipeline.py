"""Generation recovery and credential gates using temporary, synthetic inputs."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from models.text_agent import GenerationResult
from scripts import generate


class GenerationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="crag-generation-test-")
        self.addCleanup(self.temp.cleanup)
        self.tmp_path = Path(self.temp.name)
        self.manifest = self.tmp_path / "manifest.json"
        self.questions = self.tmp_path / "questions.jsonl"
        self.evidence = self.tmp_path / "evidence.jsonl"
        self.config_path = self.tmp_path / "generation.json"
        self.output = self.tmp_path / "predictions_b1.jsonl"
        self.requests = self.tmp_path / "requests_b1.jsonl"
        self.meta = self.tmp_path / "run_meta_b1.json"
        self.config = {"provider": "nvidia", "model": "synthetic-model",
                       "max_retries": 0, "evidence_token_budget": 1500,
                       "prompt_templates": {"system": "Synthetic system.",
                                            "b0_user": "Question: {query}",
                                            "b1_user": "Evidence: {evidence}\nQuestion: {query}"}}
        self.write_json(self.manifest, {"schema_version": "m3.v1",
                                      "subsets": {"dev": {"ids": ["synthetic-id"]}}})
        self.question = {"schema_version": "m3.v1", "subset": "dev",
                         "interaction_id": "synthetic-id", "query": "Synthetic question?",
                         "dataset_manifest_sha256": generate.file_sha256(self.manifest)}
        self.evidence_row = {"interaction_id": "synthetic-id",
                             "dataset_manifest_sha256": self.question["dataset_manifest_sha256"],
                             "query_sha256": generate.query_sha256(self.question["query"]),
                             "retrieval_status": "ok", "retrieval_config_sha256": "f" * 64,
                             "hits": [{"doc_id": "synthetic-doc", "text": "Original evidence."}]}
        self.write_json(self.questions, self.question)
        self.write_json(self.evidence, self.evidence_row)
        self.write_json(self.config_path, self.config)
        self.args = ["--manifest", str(self.manifest), "--questions", str(self.questions),
                     "--evidence", str(self.evidence), "--config", str(self.config_path),
                     "--output", str(self.output), "--baseline", "B1", "--run-id", "synthetic-run"]
        # Any accidental unmocked HTTP attempt fails; no credentials are read.
        network = patch("requests.Session.post", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)
        agent = Mock()
        agent.credential_configured.return_value = False
        constructor = patch.object(generate, "TextAgent", return_value=agent)
        self.agent_constructor = constructor.start()
        self.addCleanup(constructor.stop)
        commit = patch.object(generate, "git_commit", return_value="synthetic-commit")
        commit.start()
        self.addCleanup(commit.stop)

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    @staticmethod
    def read_json(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def seed_success(self):
        with patch.object(generate, "retry_generate",
                          return_value=(GenerationResult("Synthetic old answer", 5, 3), None, 0)) as call:
            self.assertEqual(0, generate.main(self.args))
            call.assert_called_once()
        return self.read_json(self.output)

    def test_successful_resume_keeps_prediction_without_a_new_call(self):
        old = self.seed_success()
        with patch.object(generate, "retry_generate", side_effect=AssertionError("Unexpected request")) as call:
            self.assertEqual(0, generate.main(self.args))
            call.assert_not_called()
        self.assertEqual(old, self.read_json(self.output))

    def test_resume_regenerates_old_prediction_after_request_only_update(self):
        old = self.seed_success()
        self.evidence_row["hits"][0]["text"] = "Changed evidence."
        self.write_json(self.evidence, self.evidence_row)
        request = self.read_json(self.requests)
        used = generate.select_evidence(self.evidence_row, 1500)
        messages = generate.render_messages(self.config, "B1", self.question["query"], used)
        request.update(messages=messages, evidence_used=used,
                       prompt_sha256=generate.prompt_sha256(messages))
        self.write_json(self.requests, request)
        self.assertNotEqual(old["prompt_sha256"], request["prompt_sha256"])
        with patch.object(generate, "retry_generate",
                          return_value=(GenerationResult("Synthetic new answer", 7, 3), None, 0)) as call:
            self.assertEqual(0, generate.main(self.args))
            call.assert_called_once()
        prediction = self.read_json(self.output)
        self.assertEqual("Synthetic new answer", prediction["agent_response"])
        self.assertEqual(request["prompt_sha256"], prediction["prompt_sha256"])

    def test_resume_does_not_trust_sidecar_hash_without_its_messages(self):
        self.seed_success()
        request = self.read_json(self.requests)
        request["messages"][1]["content"] = "Synthetic stale sidecar body."
        self.assertNotEqual(request["prompt_sha256"], generate.prompt_sha256(request["messages"]))
        self.write_json(self.requests, request)
        with patch.object(generate, "retry_generate",
                          return_value=(GenerationResult("Synthetic regenerated answer", 5, 3), None, 0)) as call:
            self.assertEqual(0, generate.main(self.args))
            call.assert_called_once()
        rebuilt = self.read_json(self.requests)
        self.assertEqual(rebuilt["prompt_sha256"], generate.prompt_sha256(rebuilt["messages"]))
        self.assertEqual(rebuilt["prompt_sha256"], self.read_json(self.output)["prompt_sha256"])

    def test_secret_config_is_rejected_before_agent_or_output_creation(self):
        for secret_field in ({"api_key": "synthetic-secret-do-not-copy"},
                             {"nested": [{"NVIDIA_API_KEY": "synthetic-secret-do-not-copy"}]}):
            with self.subTest(field=next(iter(secret_field))):
                self.write_json(self.config_path, {**self.config, **secret_field})
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(1, generate.main(self.args))
                self.agent_constructor.assert_not_called()
                self.assertIn("credential fields", stderr.getvalue())
                self.assertNotIn("synthetic-secret-do-not-copy", stderr.getvalue())
                self.assertFalse(self.output.exists())
                self.assertFalse(self.requests.exists())
                self.assertFalse(self.meta.exists())


if __name__ == "__main__":
    unittest.main()
