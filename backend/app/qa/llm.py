"""LLM access with per-call token accounting.

Every call is logged so the cost of a question can be measured, and the whole
pipeline degrades to deterministic behaviour when no API key is configured.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when no model is configured or every attempt failed."""


def estimate_tokens(text: str) -> int:
    """Rough token estimate used when the provider omits usage data."""
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class TokenUsage:
    purpose: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated: bool = False
    duration_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict:
        return {
            "purpose": self.purpose, "model": self.model, "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens, "total_tokens": self.total_tokens,
            "estimated": self.estimated, "duration_ms": self.duration_ms,
        }


@dataclass
class UsageLog:
    """Collects token usage for one question."""

    calls: list[TokenUsage] = field(default_factory=list)

    def add(self, usage: TokenUsage) -> TokenUsage:
        self.calls.append(usage)
        logger.info(
            "llm usage purpose=%s model=%s prompt_tokens=%d completion_tokens=%d total_tokens=%d estimated=%s",
            usage.purpose, usage.model, usage.prompt_tokens, usage.completion_tokens,
            usage.total_tokens, usage.estimated,
        )
        return usage

    @property
    def total_tokens(self) -> int:
        return sum(call.total_tokens for call in self.calls)

    def totals(self) -> dict:
        return {
            "calls": len(self.calls),
            "prompt_tokens": sum(call.prompt_tokens for call in self.calls),
            "completion_tokens": sum(call.completion_tokens for call in self.calls),
            "total_tokens": self.total_tokens,
        }

    def to_list(self) -> list[dict]:
        return [call.to_dict() for call in self.calls]


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: TokenUsage


class LLMClient:
    """Thin wrapper over an OpenAI-compatible chat completions endpoint."""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, fallback_model: str | None = None,
                 client: Any | None = None, usage_log: UsageLog | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self.model = model or "gpt-4o-mini"
        self.fallback_model = fallback_model
        self._client = client
        self.usage_log = usage_log or UsageLog()

    @classmethod
    def from_settings(cls, settings: Any, *, usage_log: UsageLog | None = None) -> "LLMClient":
        return cls(api_key=getattr(settings, "llm_api_key", None),
                   base_url=getattr(settings, "llm_base_url", None),
                   model=getattr(settings, "llm_default_model", None),
                   fallback_model=getattr(settings, "llm_fallback_model", None),
                   usage_log=usage_log)

    @property
    def available(self) -> bool:
        return self._client is not None or bool(self._api_key)

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise LLMUnavailable("No LLM API key configured")
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def complete(self, purpose: str, system: str, user: str, *, json_object: bool = False,
                 temperature: float = 0.0, max_tokens: int = 700) -> LLMResponse:
        """Run one chat completion, recording token usage."""
        client = self._ensure_client()
        models = [model for model in (self.model, self.fallback_model) if model]
        last_error: Exception | None = None
        for model in models:
            started = time.perf_counter()
            try:
                request: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_object:
                    request["response_format"] = {"type": "json_object"}
                completion = client.chat.completions.create(**request)
            except Exception as error:  # noqa: BLE001 - provider errors vary
                last_error = error
                logger.warning("llm call failed purpose=%s model=%s error=%s", purpose, model, error)
                continue
            text = (completion.choices[0].message.content or "").strip()
            reported = getattr(completion, "usage", None)
            prompt_tokens = int(getattr(reported, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(reported, "completion_tokens", 0) or 0)
            estimated = not (prompt_tokens or completion_tokens)
            if estimated:
                prompt_tokens = estimate_tokens(system) + estimate_tokens(user)
                completion_tokens = estimate_tokens(text)
            usage = self.usage_log.add(TokenUsage(
                purpose=purpose, model=model, prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens, estimated=estimated,
                duration_ms=int((time.perf_counter() - started) * 1000),
            ))
            return LLMResponse(text=text, usage=usage)
        raise LLMUnavailable(f"All models failed for {purpose}: {last_error}")
