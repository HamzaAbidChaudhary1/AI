"""LangGraph graph (docs/AGENT.md "Graph")."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import AgentState

ROUTES = {
    "smalltalk": "smalltalk", "quick_answer": "quick_answer", "consult": "consult", "assess_eligibility": "assess_eligibility",
    "build_quote": "build_quote", "scam_check": "scam_check", "plan_umrah": "plan_umrah", "booking_flow": "booking_flow",
    "work_visa": "work_visa", "fraud_request": "refuse_fraud", "refusal_analysis": "refusal_analysis",
    "submit_pack": "submit_pack",
}


def _route(state: AgentState) -> str:
    if state.payload.get("action") == "submit_pack":
        return "submit_pack"
    return ROUTES.get(state.intent or "", "consult")


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> Any:
    g = StateGraph(AgentState)
    g.add_node("router", nodes.router_node)
    g.add_node("smalltalk", nodes.smalltalk_node)
    g.add_node("quick_answer", nodes.quick_answer_node)
    g.add_node("consult", nodes.consult_node)
    g.add_node("assess_eligibility", nodes.assess_node)
    g.add_node("build_quote", nodes.build_quote_node)
    g.add_node("scam_check", nodes.scam_node)
    g.add_node("plan_umrah", nodes.umrah_node)
    g.add_node("booking_flow", nodes.booking_node)
    g.add_node("work_visa", nodes.work_visa_node)
    g.add_node("refuse_fraud", nodes.fraud_node)
    g.add_node("refusal_analysis", nodes.refusal_node)
    g.add_node("submit_pack", nodes.submit_pack_node)
    g.add_node("request_user_confirmation", nodes.confirm_node)
    g.add_node("respond", nodes.respond_node)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", _route, list(set(ROUTES.values())))
    for n in set(ROUTES.values()) - {"submit_pack"}:
        g.add_edge(n, "respond")
    g.add_edge("submit_pack", "request_user_confirmation")
    g.add_edge("request_user_confirmation", "respond")
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer)


def thread_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}


def turn_input(text: str, *, locale: str, user_id: str | None, session_id: str | None, case_id: str | None,
               payload: dict[str, Any] | None = None) -> dict[str, Any]:
    inp: dict[str, Any] = {"messages": [{"role": "user", "content": text}], "locale": locale, "user_id": user_id,
                           "session_id": session_id, "payload": payload or {}}
    if case_id:
        inp["case_id"] = case_id
    return inp
