"""CLAUDE.md rule 1: a lint/test that scans all outbound templates for guarantee language.

Scans UI message catalogues (en/ur), server-side case-event strings, form declarations, scam-checker
texts and the system prompt. Negated statements ("no one can guarantee a visa") and quoted reported
speech are allowed; any promise is a failure."""

import json
from pathlib import Path

import pytest
from rahbar_agent import i18n, scam
from rahbar_agent.forms import gb, tr
from rahbar_agent.guardrails import find_guarantee_language

ROOT = Path(__file__).resolve().parents[3]


def _strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k != "code":  # identifiers, not user-facing text
                yield from _strings(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            yield from _strings(v)
    elif isinstance(obj, str):
        yield obj


SOURCES = {
    "messages/en.json": lambda: json.loads((ROOT / "apps/web/messages/en.json").read_text()),
    "messages/ur.json": lambda: json.loads((ROOT / "apps/web/messages/ur.json").read_text()),
    "i18n.EVENTS": lambda: i18n.EVENTS,
    "forms.gb": lambda: gb.DECLARATIONS,
    "forms.tr": lambda: tr.DECLARATIONS,
    "scam.FLAGS": lambda: [(en, ur) for _c, _rx, en, ur in scam.FLAGS],
    "scam.steps": lambda: scam.verification_steps(True),
    "prompts/system.md": lambda: [(ROOT / "services/agent/rahbar_agent/prompts/system.md").read_text()],
}


@pytest.mark.parametrize("name", SOURCES)
def test_no_guarantee_language_in_templates(name):
    hits = [h for s in _strings(SOURCES[name]()) for h in find_guarantee_language(s)]
    assert not hits, f"{name}: {hits}"


def test_lint_catches_a_bad_template():
    assert find_guarantee_language("Get your guaranteed UK visa today!")
