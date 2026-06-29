"""LangGraph wiring for the corrective-RAG agent.

    router ─route─▶ retrieve ─▶ grade ─cond─▶ generate ─▶ verify ─cond─▶ END
       │                          │                          │
       └─out_of_scope─▶ END       ├─rewrite─▶ retrieve       └─regen─▶ generate
                                  └─refuse──▶ END

Compiled once; per-request runtime (db connection, llm, embedder) is passed via
the config ``configurable.ctx`` so the graph is stateless and reusable.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from app.agent import nodes
from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.config import get_settings
from app.guardrails.coverage import coverage_decision


def _grade_branch(state: AgentState) -> str:
    return coverage_decision(state.get("grade", 0.0), state.get("attempts", 0), get_settings())


def _verify_branch(state: AgentState) -> str:
    return "end" if state.get("verified") else "generate"


@lru_cache
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("router", nodes.router)
    g.add_node("retrieve", nodes.retrieve)
    g.add_node("grader", nodes.grade)
    g.add_node("rewrite", nodes.rewrite)
    g.add_node("refuse", nodes.refuse)
    g.add_node("generate", nodes.generate)
    g.add_node("verify", nodes.verify)

    g.set_entry_point("router")
    g.add_conditional_edges(
        "router",
        lambda s: s.get("route", "single_rule"),
        {"single_rule": "retrieve", "precedent": "retrieve", "out_of_scope": END},
    )
    g.add_edge("retrieve", "grader")
    g.add_conditional_edges(
        "grader",
        _grade_branch,
        {"generate": "generate", "rewrite": "rewrite", "refuse": "refuse"},
    )
    g.add_edge("rewrite", "retrieve")
    g.add_edge("refuse", END)
    g.add_edge("generate", "verify")
    g.add_conditional_edges("verify", _verify_branch, {"end": END, "generate": "generate"})
    return g.compile()


def run_agent(ctx: AgentContext, question: str, config_overrides: dict | None = None) -> AgentState:
    """Invoke the full graph and return the final state."""
    graph = build_graph()
    initial: AgentState = {"question": question, "config": config_overrides or {}}
    return graph.invoke(initial, config={"configurable": {"ctx": ctx}})
