"""Strict JSON and deterministic hashes shared by the five M3 modules.

This module does not import model/search libraries or contact a provider.
Config hashes remove credentials and absolute *cache* paths only. All
experiment settings (including prompts and versions) remain in the hash.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from string import Formatter
from typing import Any

SCHEMA_VERSION = "m3.v1"
SUBSETS = ("smoke", "dev", "eval")
RESPONSE_TOKENIZER = "meta-llama/Llama-3.2-1B-Instruct"
SECRET_KEYS = frozenset({
    "api_key", "apikey", "access_token", "api_token", "auth_token",
    "authorization", "password", "secret", "client_secret",
    "nvidia_api_key", "openai_api_key", "cloudflare_api_token",
    "hf_token", "hugging_face_hub_token", "bearer_token",
})


class ContractError(ValueError):
    """Malformed data, without echoing possibly sensitive input values."""


def is_secret_key(key: str) -> bool:
    name = key.lower().replace("-", "_")
    return name in SECRET_KEYS or name.endswith(("_api_key", "_password", "_secret"))


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError("Duplicate JSON object key")
        value[key] = item
    return value


def _constant(_: str) -> None:
    raise ContractError("NaN/Infinity are not allowed in JSON")


def _float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ContractError("Non-finite JSON number is not allowed")
    return value


def _check_strings(value: Any) -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractError("JSON string contains an unpaired Unicode surrogate") from exc
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_strings(key)
            _check_strings(item)
    elif isinstance(value, list):
        for item in value:
            _check_strings(item)


def parse_json(text: str) -> Any:
    if text.startswith("\ufeff"):
        raise ContractError("UTF-8 BOM is not allowed")
    try:
        value = json.loads(text, object_pairs_hook=_object, parse_constant=_constant,
                           parse_float=_float)
        _check_strings(value)
        return value
    except json.JSONDecodeError as exc:
        raise ContractError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}") from exc


def load_json(path: str | Path) -> Any:
    try:
        return parse_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ContractError("File could not be read as UTF-8") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def query_sha256(query: str) -> str:
    try:
        return sha256_bytes(query.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ContractError("String cannot be encoded as UTF-8") from exc


def prompt_sha256(messages: list[dict[str, str]]) -> str:
    return query_sha256(canonical_json(messages))


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_config(value: Any) -> Any:
    """Canonical hash policy; relative cache paths are kept conservatively."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if is_secret_key(key):
                continue
            name = key.lower()
            absolute = isinstance(item, str) and (
                PureWindowsPath(item).is_absolute() or PurePosixPath(item).is_absolute())
            if absolute and "cache" in name and (
                name.endswith(("_path", "_dir", "_directory")) or name == "cache"):
                continue
            result[key] = clean_config(item)
        return result
    if isinstance(value, list):
        return [clean_config(item) for item in value]
    return value


def config_sha256(config: dict[str, Any]) -> str:
    return query_sha256(canonical_json(clean_config(config)))


def find_secret_keys(value: Any, prefix: str = "") -> list[str]:
    """Return paths to forbidden keys, never their values."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}/{key}"
            if is_secret_key(key):
                found.append(path)
            found.extend(find_secret_keys(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(find_secret_keys(item, f"{prefix}/{index}"))
    return found


def render_messages(config: dict[str, Any], baseline: str, query: str,
                    evidence_used: list[dict[str, str]]) -> list[dict[str, str]]:
    """The audited text-only prompt envelope. D may import this helper.

    Config must contain prompt_templates.system/b0_user/b1_user. Templates
    allow only {query}/{evidence}; system is literal. Evidence selection and
    budget remain D's job and must refer to C's returned hits.
    """
    templates = config.get("prompt_templates", {})
    if not isinstance(templates, dict) or not all(isinstance(templates.get(key), str) and templates[key].strip()
               for key in ("system", "b0_user", "b1_user")):
        raise ContractError("Missing nonempty prompt_templates.system/b0_user/b1_user")
    if baseline not in ("B0", "B1"):
        raise ContractError("Unknown baseline")
    if baseline == "B0" and evidence_used:
        raise ContractError("B0 must not use evidence")
    template = templates["b0_user" if baseline == "B0" else "b1_user"]
    try:
        fields = []
        for _, field, spec, conversion in Formatter().parse(template):
            if field is not None:
                if field not in {"query", "evidence"} or spec or conversion:
                    raise ContractError("Unsupported prompt template field")
                fields.append(field)
        if "query" not in fields or (baseline == "B0" and "evidence" in fields):
            raise ContractError("Prompt template must include query; B0 cannot include evidence")
        if baseline == "B1" and "evidence" not in fields:
            raise ContractError("B1 template must include evidence")
        evidence = "\n\n".join(f"[{hit['doc_id']}]\n{hit['text']}" for hit in evidence_used)
        user = template.format(query=query, evidence=evidence)
    except (ValueError, KeyError) as exc:
        raise ContractError("Invalid prompt template/evidence structure") from exc
    return [{"role": "system", "content": templates["system"]},
            {"role": "user", "content": user}]
