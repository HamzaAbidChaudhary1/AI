"""Agent state (docs/AGENT.md "State")."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    locale: Literal["en", "ur"] = "en"
    user_id: str | None = None
    session_id: str | None = None
    case_id: str | None = None
    service_type: str | None = None
    destination: str | None = None
    visa_type: str | None = None
    trip: dict[str, Any] = Field(default_factory=dict)
    traveller_profiles: list[dict[str, Any]] = Field(default_factory=list)
    messages: Annotated[list[dict[str, Any]], operator.add] = Field(default_factory=list)
    # per-turn fields (reset by the router every turn)
    payload: dict[str, Any] = Field(default_factory=dict)   # structured UI input (profile form, choice, ...)
    intent: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    allowed_amounts: list[str] = Field(default_factory=list)
    pending_action: dict[str, Any] | None = None
    reply: str | None = None
