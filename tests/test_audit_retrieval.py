"""Synthetic cache diagnostics; no official index, model or API is used."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.audit_retrieval import inspect
from scripts.retrieve import StructuralError
from src.contracts.m3 import config_sha256, file_sha256, query_sha256
from src.retrieval.text_retrieval import ConfigError, RetrievalConfig


class RetrievalAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-retrieval-audit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"top_k": 5, "index_repo": "synthetic/index", "index_revision": "fixed-index",
                       "encoder_id": "synthetic/encoder", "encoder_revision": "fixed-encoder"}
        self.manifest = {"schema_version": "m3.v1", "data_origin": "synthetic", "revision": "fixed-data",
                         "subsets": {s: {"ids": ["a", "b"] if s == "dev" else [],
                                          "count": 2 if s == "dev" else 0}
                                     for s in ("smoke", "dev", "eval")}}
        self.write_json("manifest.json", self.manifest)
        self.manifest_hash = file_sha256(self.root / "manifest.json")
        common = {"schema_version": "m3.v1", "subset": "dev",
                  "dataset_manifest_sha256": self.manifest_hash}
        self.questions = [{**common, "interaction_id": i, "session_id": i, "query": "Synthetic " + i}
                          for i in ("a", "b")]
        self.evidence = [{**common, "interaction_id": q["interaction_id"],
            "query_sha256": query_sha256(q["query"]), "run_id": "synthetic-run",
            "retrieval_config_sha256": config_sha256(self.config),
            "index_revision": "fixed-index", "encoder_revision": "fixed-encoder",
            "retrieval_status": "ok", "latency_ms": 1, "error_code": None,
            "hits": [{"rank": 1, "doc_id": "synthetic-" + q["interaction_id"], "url": None,
                      "title": "Synthetic title", "text": "Synthetic title", "score": .75,
                      "score_kind": "similarity"}]} for q in self.questions]
        self.save()

    def write_json(self, name, value):
        (self.root / name).write_text(json.dumps(value) + "\n", encoding="utf-8")

    def save(self):
        self.write_json("config.json", self.config)
        for name, rows in (("questions.jsonl", self.questions), ("evidence.jsonl", self.evidence)):
            (self.root / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def inspect(self):
        return inspect(*(self.root / name for name in ("manifest.json", "questions.jsonl",
                                                      "evidence.jsonl", "config.json")))

    def test_diagnostic_without_answers_reports_missing_content(self):
        report, samples = self.inspect()
        self.assertEqual(report["statuses"], {"ok": 2, "empty": 0, "error": 0})
        self.assertEqual(report["title_only_hits"], 2)
        self.assertEqual(report["cached_prefix_hit_counts"], {"1": 2, "3": 2, "5": 2})
        self.assertEqual(samples[0]["review_status"], "unreviewed")

    def test_missing_row_rejected(self):
        self.evidence.pop()
        self.save()
        with self.assertRaises(StructuralError): self.inspect()

    def test_duplicate_row_rejected(self):
        self.evidence.append(copy.deepcopy(self.evidence[0]))
        self.save()
        with self.assertRaises(StructuralError): self.inspect()

    def test_query_tampering_rejected(self):
        self.questions[0]["query"] = "Changed synthetic query"
        self.save()
        with self.assertRaises(StructuralError): self.inspect()

    def test_config_tampering_rejected(self):
        self.config["top_k"] = 3
        self.save()
        with self.assertRaises(StructuralError): self.inspect()

    def test_eval_cannot_be_used_for_parameter_diagnostics(self):
        self.questions[0]["subset"] = self.questions[1]["subset"] = "eval"
        self.save()
        with self.assertRaises(StructuralError): self.inspect()

    def test_technical_failure_is_preserved(self):
        self.evidence[0].update(retrieval_status="error", hits=[], error_code="synthetic_failure")
        self.save()
        report, _ = self.inspect()
        self.assertEqual(report["statuses"]["error"], 1)

    def test_fetch_k_cannot_be_silently_ignored(self):
        with self.assertRaisesRegex(ConfigError, "not implemented"):
            RetrievalConfig.from_dict({**self.config, "fetch_k": 20})

    def test_legacy_config_retains_top_k(self):
        self.assertEqual(RetrievalConfig.from_dict(self.config).top_k, 5)


if __name__ == "__main__":
    unittest.main()
