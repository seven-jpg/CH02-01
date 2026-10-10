"""Validate the current m3.v1 contract and resolve relocated generation provenance."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
from typing import Any

from src.contracts.m3 import (ContractError, config_sha256, file_sha256, find_secret_keys,
                              load_json, prompt_sha256, query_sha256)
from src.evaluation.score import ROOT, read_rows


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def relative(path: Path, directory: Path) -> str:
    return os.path.relpath(path, directory).replace(os.sep, "/")


class Inputs:
    def __init__(self, paths: dict[str, Path], batch: Path | None = None):
        from jsonschema import Draft202012Validator
        self.paths = paths
        self.schema = load_json(ROOT / "docs/M2_M3_execution/接口字段.schema.json")
        self.validator_class = Draft202012Validator
        self.manifest = load_json(paths["manifest"])
        self.validate(self.manifest, "manifest")
        if self.manifest["revision"] in ("main", "master", "latest"):
            raise ContractError("Manifest revision must be immutable")
        self.manifest_hash = file_sha256(paths["manifest"])
        self.hashes = {name: file_sha256(path) for name, path in paths.items()}
        for spec in self.manifest["subsets"].values():
            if len(spec["ids"]) != spec["count"]:
                raise ContractError("Manifest subset count mismatch")
        all_ids = [i for spec in self.manifest["subsets"].values() for i in spec["ids"]]
        if len(set(all_ids)) != len(all_ids):
            raise ContractError("Manifest subsets overlap")
        rows = {kind: self.index(read_rows(paths[kind]), kind) for kind in
                ("questions", "answers", "metadata", "predictions")}
        subsets = {row["subset"] for row in rows["questions"].values()}
        if len(subsets) != 1:
            raise ContractError("Questions must identify one nonempty subset")
        self.subset = subsets.pop()
        full = set(self.manifest["subsets"][self.subset]["ids"])
        self.ids = load_json(batch) if batch else list(self.manifest["subsets"][self.subset]["ids"])
        if (not isinstance(self.ids, list) or not self.ids or any(not isinstance(i, str) for i in self.ids)
                or len(set(self.ids)) != len(self.ids) or not set(self.ids).issubset(full)):
            raise ContractError("Invalid batch ID list or empty selected subset")
        expected = set(self.ids)
        for kind, mapping in rows.items():
            if any(row["subset"] != self.subset for row in mapping.values()) or not set(mapping).issubset(full):
                raise ContractError(f"{kind}: unknown ID or wrong subset")
            selected = {i: row for i, row in mapping.items() if i in expected}
            if kind == "predictions" and set(mapping) != expected:
                raise ContractError("Predictions must cover precisely the selected batch/subset")
            if set(selected) != expected:
                raise ContractError(f"{kind}: missing selected IDs")
            rows[kind] = selected
        self.rows = rows
        self.baseline = self.single("baseline")
        self.generation_run_id = self.single("run_id")
        for field in ("provider", "model", "generation_config_sha256", "retrieval_config_sha256"):
            self.single(field)
        for i in self.ids:
            q, p, meta = rows["questions"][i], rows["predictions"][i], rows["metadata"][i]
            if p["query_sha256"] != query_sha256(q["query"]):
                raise ContractError(f"Query SHA256 mismatch: {i}")
            if q["session_id"] != meta["session_id"]:
                raise ContractError(f"Question/metadata session mismatch: {i}")
            for source, manifest_key in (("source_dataset", "dataset_id"), ("source_split", "split"), ("source_revision", "revision")):
                if meta[source] is not None and meta[source] != self.manifest[manifest_key]:
                    raise ContractError(f"Metadata source identity mismatch: {i}")
            if p["generation_status"] == "ok" and not p["agent_response"].strip():
                raise ContractError(f"Whitespace-only generation response: {i}")
        self.batch_hash = file_sha256(batch) if batch else None
        if batch:
            self.paths["batch_ids"] = batch
            self.hashes["batch_ids"] = self.batch_hash

    def validate(self, value: Any, kind: str) -> None:
        if find_secret_keys(value):
            raise ContractError(f"{kind}: forbidden credential fields")
        validator = self.validator_class({"$schema": self.schema["$schema"], "$defs": self.schema["$defs"],
                                          "$ref": f"#/$defs/{kind}"})
        error = next(validator.iter_errors(value), None)
        if error:
            raise ContractError(f"{kind}: schema constraint {error.validator} failed")

    def index(self, rows: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
        result = {}
        for row in rows:
            self.validate(row, kind)
            i = row["interaction_id"]
            if i in result:
                raise ContractError(f"{kind}: duplicate ID {i}")
            if row["dataset_manifest_sha256"] != self.manifest_hash:
                raise ContractError(f"{kind}: manifest hash mismatch {i}")
            result[i] = row
        return result

    def single(self, key: str) -> Any:
        values = {row[key] for row in self.rows["predictions"].values()}
        if len(values) != 1:
            raise ContractError(f"Mixed prediction {key}")
        return values.pop()

    def provenance(self, meta_path: Path | None = None) -> dict[str, Any]:
        directory = self.paths["predictions"].parent
        suffix = self.baseline.lower()
        meta_path = meta_path or directory / f"run_meta_{suffix}.json"
        requests_path = directory / f"requests_{suffix}.jsonl"
        known = {**self.paths, "generation_meta": meta_path, "requests": requests_path}
        if self.baseline == "B1":
            known["evidence"] = directory / "evidence.jsonl"
        if any(not path.is_file() for path in known.values()):
            raise ContractError("Generation provenance files are missing")
        meta = load_json(meta_path)
        if find_secret_keys(meta):
            raise ContractError("Generation metadata contains credential fields")
        if (meta.get("stage") != "generation" or meta.get("schema_version") != "m3.v1"
                or meta.get("subset") != self.subset or meta.get("run_id") != self.generation_run_id
                or meta.get("baseline") != self.baseline
                or config_sha256(meta.get("config", {})) != self.single("generation_config_sha256")
                or meta.get("config_sha256") != self.single("generation_config_sha256")):
            raise ContractError("Generation metadata identity/config mismatch")
        # Older sidecars may omit measured counts; when present they must agree.
        for field, count in (("N_expected", len(self.ids)),
                ("N_success", sum(p["generation_status"] == "ok" for p in self.rows["predictions"].values())),
                ("N_failed", sum(p["generation_status"] != "ok" for p in self.rows["predictions"].values()))):
            if field in meta and (type(meta[field]) is not int or meta[field] != count):
                raise ContractError("Generation metadata count mismatch")
        if self.batch_hash and meta.get("batch_ids") is not None and set(meta["batch_ids"]) != set(self.ids):
            raise ContractError("Generation metadata batch mismatch")
        for key in ("provider", "model"):
            if meta["config"].get(key) != self.single(key):
                raise ContractError("Generation metadata provider/model mismatch")
        resolution = []
        for field in ("input_files_sha256", "output_files_sha256"):
            mapping = meta.get(field)
            if not isinstance(mapping, dict) or not mapping:
                raise ContractError("Generation provenance hash mapping missing")
            for original, digest in mapping.items():
                name = PureWindowsPath(original).name
                candidates = [p for p in known.values() if p.name == name and file_sha256(p) == digest]
                if not candidates:
                    raise ContractError("Generation provenance does not match the supplied local files")
                resolution.append({"field": field, "basename": name, "sha256": digest,
                                   "resolved_project_path": relative(candidates[0], ROOT),
                                   "policy": "Explicit local input, matching basename and raw-byte SHA256; original sidecar unchanged"})
        for field, required in (("input_files_sha256", ("manifest", "questions")),
                                 ("output_files_sha256", ("predictions", "requests"))):
            if any(file_sha256(known[k]) not in meta[field].values() for k in required):
                raise ContractError("Generation provenance required input/output hash missing")
        requests = self.index(read_rows(requests_path), "requests")
        predictions = self.rows["predictions"]
        expected_requests = {i for i, p in predictions.items() if p["prompt_sha256"] is not None}
        if set(requests) != expected_requests:
            raise ContractError("Generation requests coverage mismatch")
        for i, r in requests.items():
            p = predictions[i]
            if (r["run_id"] != p["run_id"] or r["baseline"] != p["baseline"] or
                    r["query_sha256"] != p["query_sha256"] or
                    prompt_sha256(r["messages"]) != r["prompt_sha256"] or
                    r["prompt_sha256"] != p["prompt_sha256"]):
                raise ContractError("Generation actual request hash/identity mismatch")
        for name, path in known.items():
            self.paths[name] = path
            self.hashes[name] = file_sha256(path)
        return {"generation_run_id": self.generation_run_id, "resolved_files": resolution,
                "source_authenticity": "D-reported provider runs; file identity verified locally; no API contacted"}
