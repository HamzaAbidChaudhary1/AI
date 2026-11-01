"""Reply composition: LLM phrasing over tool facts -> guardrail validation -> retry -> template fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .guardrails import validate_reply
from .llm import LLMRefused, LLMUnavailable, get_llm

log = logging.getLogger(__name__)
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")


def system_prompt(locale: str) -> str:
    return SYSTEM_PROMPT.replace("{language}", "Urdu (اردو script)" if locale == "ur" else "English")


def compose(*, locale: str, intent: str, user_text: str, history: list[dict[str, Any]], facts: dict[str, Any],
            citations: list[dict[str, Any]], allowed_amounts: list[str], template: str,
            tier: str = "standard") -> tuple[str, str]:
    """Returns (text, method). The template is always compliant by construction and is the fallback."""
    llm = get_llm()
    if llm is None:
        return template, "template"
    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-8:] if m["role"] in ("user", "assistant")]
    facts_block = json.dumps({"intent": intent, "facts": facts, "citations": citations}, ensure_ascii=False, default=str)
    prompt = (f"<FACTS>\n{facts_block}\n</FACTS>\n\nDraft answer you may rephrase (keep every fact, add none):\n"
              f"<DRAFT>\n{template}\n</DRAFT>\n\nUser message:\n{user_text}")
    msgs = [*msgs, {"role": "user", "content": prompt}]
    feedback = ""
    for _attempt in range(2):
        try:
            text = llm.text(tier, system_prompt(locale) + feedback, msgs, node=intent)  # type: ignore[arg-type]
        except (LLMUnavailable, LLMRefused) as e:
            log.warning("llm compose failed: %s", e)
            break
        result = validate_reply(text, citations, allowed_amounts)
        if result.ok and text:
            return text, "llm"
        feedback = ("\n\nYour previous draft was rejected by the compliance validator: "
                    + "; ".join(result.violations) + ". Fix these problems.")
    return template, "template"
