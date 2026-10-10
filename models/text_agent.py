"""Small, text-only adapters for NVIDIA NIM and Cloudflare Workers AI.

The adapter deliberately accepts only audited chat messages. It never receives
answers, images, image URLs, OCR, captions, full_query, or conversation history.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any

import requests


class GenerationError(RuntimeError):
    """A provider request failed or returned an unusable response."""

    def __init__(self, code: str, message: str = "", *, retryable: bool = True) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message or code)


@dataclass(frozen=True)
class GenerationResult:
    response: str
    input_tokens: int | None
    output_tokens: int | None


def _token_count(usage: Any, *names: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    for name in names:
        value = usage.get(name)
        if isinstance(value, int) and value >= 0:
            return value
    return None


def _choice_text(choices: Any) -> Any:
    """Reject malformed provider envelopes without leaking their contents."""
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise GenerationError("invalid_response_schema")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise GenerationError("invalid_response_schema")
    return message.get("content")


class TextAgent:
    """Provider-neutral client with explicit provider configuration."""

    def __init__(self, config: dict[str, Any], *, session: requests.Session | None = None) -> None:
        self.provider = str(config.get("provider", "")).lower().strip()
        self.model = str(config.get("model", "")).strip()
        if self.provider not in {"nvidia", "cloudflare"}:
            raise ValueError("provider must be nvidia or cloudflare")
        if not self.model:
            raise ValueError("model must be nonempty")
        self.endpoint = str(config.get("endpoint", "")).strip() or self._default_endpoint()
        self.timeout_s = float(config.get("timeout_s", 120))
        self.temperature = config.get("temperature", 0)
        self.top_p = config.get("top_p", 1)
        self.max_tokens = int(config.get("max_tokens", 100))
        self.seed = config.get("seed")
        self.session = session or requests.Session()

    def _default_endpoint(self) -> str:
        if self.provider == "nvidia":
            return "https://integrate.api.nvidia.com/v1/chat/completions"
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{self.model}"

    def credential_configured(self) -> bool:
        if self.provider == "nvidia":
            return bool(os.environ.get("NVIDIA_API_KEY"))
        return bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID")) and bool(os.environ.get("CLOUDFLARE_API_TOKEN"))

    def public_request(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Return the provider payload without credentials or network access."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        if self.provider == "cloudflare":
            return {"messages": messages, "max_tokens": self.max_tokens,
                    "temperature": self.temperature, "top_p": self.top_p,
                    **({"seed": self.seed} if self.seed is not None else {})}
        return payload

    def _headers(self) -> dict[str, str]:
        if self.provider == "nvidia":
            key = os.environ.get("NVIDIA_API_KEY")
            if not key:
                raise GenerationError("missing_nvidia_api_key", retryable=False)
            return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        token = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not token or not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
            raise GenerationError("missing_cloudflare_credentials", retryable=False)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def generate(self, messages: list[dict[str, str]]) -> GenerationResult:
        payload = self.public_request(messages)
        try:
            response = self.session.post(self.endpoint, headers=self._headers(), json=payload,
                                         timeout=self.timeout_s)
        except requests.Timeout as exc:
            raise GenerationError("timeout") from exc
        except requests.RequestException as exc:
            raise GenerationError("request_error", type(exc).__name__) from exc
        status = getattr(response, "status_code", None)
        if type(status) is not int or not callable(getattr(response, "json", None)):
            raise GenerationError("invalid_response_schema")
        try:
            data = response.json()
        except ValueError as exc:
            raise GenerationError("invalid_json_response") from exc
        if status >= 400:
            raise GenerationError(f"http_{status}", retryable=(status == 429 or status >= 500))
        if not isinstance(data, dict):
            raise GenerationError("invalid_response_schema")
        if self.provider == "nvidia":
            text = _choice_text(data.get("choices"))
            usage = data.get("usage")
        else:
            result = data.get("result")
            if not isinstance(result, dict):
                raise GenerationError("invalid_response_schema")
            text = result.get("response")
            usage = result.get("usage")
            if text is None:
                text = _choice_text(result.get("choices"))
        if not isinstance(text, str) or not text.strip():
            raise GenerationError("empty_response")
        return GenerationResult(text.strip(), _token_count(usage, "prompt_tokens", "input_tokens"),
                                _token_count(usage, "completion_tokens", "output_tokens"))


def retry_generate(agent: TextAgent, messages: list[dict[str, str]], *, max_retries: int,
                   backoff_s: float) -> tuple[GenerationResult | None, str | None, int]:
    """Call at most max_retries+1 times; return result, error code, retry count."""
    retries = 0
    for attempt in range(max_retries + 1):
        try:
            return agent.generate(messages), None, retries
        except GenerationError as exc:
            if attempt >= max_retries or not exc.retryable:
                return None, exc.code, retries
            retries += 1
            time.sleep(backoff_s * (2 ** attempt))
    return None, "request_error", retries
