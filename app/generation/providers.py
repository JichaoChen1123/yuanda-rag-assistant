"""LLM provider adapters with automatic fallback.

Each provider exposes the same `complete(prompt, system, ...)` method. The
`MultiProviderLLM` wrapper tries them in configured order and falls back
on failure — useful when running Ollama locally but wanting a cloud safety
net for production.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import get_logger, log_event

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: float
    raw: dict | None = None


class BaseLLM(ABC):
    name: str
    model: str

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> LLMResponse: ...

    def health(self) -> bool:
        try:
            r = self.complete("ping", max_tokens=4)
            return bool(r.text)
        except Exception:
            return False


# ---------- Ollama ----------

class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self._timeout = settings.ollama_timeout

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        t0 = time.perf_counter()
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        latency_ms = (time.perf_counter() - t0) * 1000

        text = data.get("message", {}).get("content", "")
        return LLMResponse(text=text, provider=self.name, model=self.model,
                           latency_ms=latency_ms, raw=data)


# ---------- OpenAI ----------

class OpenAILLM(BaseLLM):
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        with httpx.Client(timeout=60) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        latency_ms = (time.perf_counter() - t0) * 1000

        text = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, provider=self.name, model=self.model,
                           latency_ms=latency_ms, raw=data)


# ---------- Anthropic ----------

class AnthropicLLM(BaseLLM):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> LLMResponse:
        # Anthropic doesn't have a native json_mode flag (use prompt-level
        # instruction); we still set temperature low to reduce variance.
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        t0 = time.perf_counter()
        with httpx.Client(timeout=60) as client:
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        latency_ms = (time.perf_counter() - t0) * 1000

        # Concatenate any text blocks Anthropic returns.
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return LLMResponse(text=text, provider=self.name, model=self.model,
                           latency_ms=latency_ms, raw=data)


# ---------- Multi-provider wrapper ----------

class MultiProviderLLM:
    """Tries providers in `order`, falling back to the next on error.

    Each provider is constructed lazily so missing API keys for a given
    provider don't crash the whole system at startup.
    """

    def __init__(self, order: list[str] | None = None) -> None:
        self.order = order or settings.llm_fallback_order
        self._cache: dict[str, BaseLLM] = {}

    def _get(self, name: str) -> BaseLLM:
        if name in self._cache:
            return self._cache[name]
        if name == "ollama":
            llm = OllamaLLM()
        elif name == "openai":
            llm = OpenAILLM()
        elif name == "anthropic":
            llm = AnthropicLLM()
        elif name == "codex":
            from app.generation.codex_provider import CodexLLM
            llm = CodexLLM()
        else:
            raise ValueError(f"Unknown LLM provider: {name}")
        self._cache[name] = llm
        return llm

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        json_mode: bool = False,
        preferred: str | None = None,
    ) -> LLMResponse:
        if preferred and preferred not in self.order:
            raise ValueError("Requested LLM provider is not enabled in LLM_FALLBACK_ORDER")
        order = [preferred, *self.order] if preferred else list(self.order)
        # de-dup while preserving order
        seen: set[str] = set()
        ordered = [p for p in order if p and not (p in seen or seen.add(p))]

        last_err: Exception | None = None
        for provider_name in ordered:
            try:
                llm = self._get(provider_name)
            except Exception as e:
                logger.debug(f"Provider {provider_name} unavailable: {e}")
                last_err = e
                continue
            try:
                resp = llm.complete(
                    prompt=prompt, system=system,
                    max_tokens=max_tokens, temperature=temperature,
                    json_mode=json_mode,
                )
                log_event(logger, "llm_call",
                          provider=provider_name, model=llm.model,
                          latency_ms=f"{resp.latency_ms:.0f}")
                return resp
            except Exception as e:
                logger.warning(f"Provider {provider_name} failed: {e}; trying next")
                last_err = e
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_err}")


_multi: MultiProviderLLM | None = None


def get_llm() -> MultiProviderLLM:
    global _multi
    if _multi is None:
        _multi = MultiProviderLLM()
    return _multi
