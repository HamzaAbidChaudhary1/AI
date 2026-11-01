"""LLM access with model routing (docs/AGENT.md "Model routing").

Tiers: fast (routing, quick facts), standard (quotes, itineraries, scam check, extraction),
deep (assessment, document review, Umrah planning, refusal analysis).

When no Anthropic credentials are configured (LLM_MODE=offline, or auto without a key) the
agent still works: every node computes its facts deterministically and composes replies from
templates. The LLM only ever *phrases* facts that came from tools.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .config import Settings, get_settings

log = logging.getLogger(__name__)

Tier = Literal["fast", "standard", "deep"]

# effort per tier: deep work gets real thinking, routing stays cheap
_EFFORT: dict[Tier, str] = {"fast": "low", "standard": "medium", "deep": "high"}
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5", "claude-fable-5-1"}


class LLMUnavailable(RuntimeError):
    pass


class LLMRefused(RuntimeError):
    pass


@dataclass
class Usage:
    model: str
    input_tokens: int
    output_tokens: int


UsageHook = Callable[[Usage, str | None], None]


class LLM:
    def __init__(self, settings: Settings | None = None, usage_hook: UsageHook | None = None) -> None:
        import anthropic

        self.s = settings or get_settings()
        self.client = anthropic.Anthropic(api_key=self.s.anthropic_api_key or None, max_retries=3)
        self.usage_hook = usage_hook

    def model_for(self, tier: Tier) -> str:
        return {"fast": self.s.model_fast, "standard": self.s.model_standard, "deep": self.s.model_deep}[tier]

    def _create(self, tier: Tier, node: str | None, **kwargs: Any) -> Any:
        import anthropic

        model = self.model_for(tier)
        extra: dict[str, Any] = {}
        if model in _FALLBACK_MODELS:
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            if extra:
                resp = self.client.beta.messages.create(model=model, **kwargs, **extra)
            else:
                resp = self.client.messages.create(model=model, **kwargs)
        except anthropic.APIConnectionError as e:
            raise LLMUnavailable(str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 or e.status_code == 429:
                raise LLMUnavailable(f"{e.status_code}") from e
            raise
        if resp.stop_reason == "refusal":
            raise LLMRefused(getattr(getattr(resp, "stop_details", None), "category", None) or "refusal")
        if self.usage_hook:
            try:
                self.usage_hook(Usage(resp.model, resp.usage.input_tokens, resp.usage.output_tokens), node)
            except Exception:  # usage accounting must never break a reply
                log.exception("usage hook failed")
        return resp

    def text(self, tier: Tier, system: str, messages: list[dict[str, Any]], *, node: str | None = None,
             max_tokens: int = 4000) -> str:
        resp = self._create(
            tier, node, max_tokens=max_tokens, system=system, messages=messages,
            thinking={"type": "adaptive"}, output_config={"effort": _EFFORT[tier]},
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def json(self, tier: Tier, system: str, prompt: str, schema: dict[str, Any], *, node: str | None = None,
             max_tokens: int = 8000) -> dict[str, Any]:
        """Structured output via output_config.format (forced tool_choice is rejected on 5.5 models)."""
        resp = self._create(
            tier, node, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={"effort": _EFFORT[tier], "format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text)


_llm: LLM | None = None
_override: LLM | None | bool = False  # tests can force None (offline) or a fake


def get_llm(usage_hook: UsageHook | None = None) -> LLM | None:
    """Returns an LLM client, or None when running offline."""
    global _llm
    if _override is not False:
        return _override  # type: ignore[return-value]
    s = get_settings()
    if not s.use_anthropic:
        return None
    if _llm is None:
        _llm = LLM(s, usage_hook)
    return _llm


def set_llm(llm: LLM | None | bool) -> None:
    """Test hook: set_llm(None) forces offline; set_llm(False) restores auto."""
    global _override
    _override = llm
