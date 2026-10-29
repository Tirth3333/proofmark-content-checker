"""Provider-independent LLM access.

Only two wire formats are implemented, which covers most hosted and local models:
  - "openai": any OpenAI-compatible /chat/completions endpoint (OpenAI, Groq,
    OpenRouter, Together, Ollama, LM Studio, vLLM ...) via LLM_BASE_URL.
  - "anthropic": the Anthropic Messages API.
Both use httpx directly so no vendor SDK is required.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional, Protocol

import httpx

from ..config import settings


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    async def complete_json(self, system: str, user: str) -> dict[str, Any]: ...


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fence:
        raw = fence.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model response did not contain a JSON object.")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"Model returned invalid JSON: {e.msg}") from e


class OpenAICompatible:
    name = "openai-compatible"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.api_key, self.model, self.timeout, self.transport = api_key, model or "gpt-4o-mini", timeout, transport
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as c:
            try:
                r = await c.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
            except httpx.HTTPError as e:
                raise LLMError(f"Could not reach the AI provider ({type(e).__name__}).") from e
        if r.status_code >= 400:
            raise LLMError(f"AI provider returned HTTP {r.status_code}.")
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError("Unexpected response shape from AI provider.") from e
        return _parse_json(content)


class Anthropic:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.api_key, self.timeout, self.transport = api_key, timeout, transport
        self.model = model or "claude-haiku-4-5"
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = {"model": self.model, "max_tokens": 4096, "temperature": 0, "system": system, "messages": [{"role": "user", "content": user}]}
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as c:
            try:
                r = await c.post(f"{self.base_url}/v1/messages", json=body, headers=headers)
            except httpx.HTTPError as e:
                raise LLMError(f"Could not reach the AI provider ({type(e).__name__}).") from e
        if r.status_code >= 400:
            raise LLMError(f"AI provider returned HTTP {r.status_code}.")
        try:
            content = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
        except (KeyError, ValueError, TypeError) as e:
            raise LLMError("Unexpected response shape from AI provider.") from e
        return _parse_json(content)


def get_provider(transport: Optional[httpx.AsyncBaseTransport] = None) -> tuple[Optional[LLMProvider], str]:
    """Return (provider, reason). provider is None when AI is not configured."""
    p = settings.llm_provider
    if p in ("", "none", "off", "disabled"):
        return None, "No AI provider configured (LLM_PROVIDER=none)."
    if p not in ("openai", "anthropic"):
        return None, f"Unknown LLM_PROVIDER '{p}'. Use 'openai' or 'anthropic'."
    local = settings.llm_base_url.startswith(("http://localhost", "http://127.0.0.1"))
    if not settings.llm_api_key and not local:
        return None, "LLM_PROVIDER is set but LLM_API_KEY is missing."
    cls = OpenAICompatible if p == "openai" else Anthropic
    return cls(settings.llm_api_key, settings.llm_model, settings.llm_base_url, settings.llm_timeout, transport), "configured"
