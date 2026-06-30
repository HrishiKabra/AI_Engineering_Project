"""Agent graph nodes (corrective RAG).

router -> retrieve -> grade -> (rewrite -> retrieve)* -> generate -> verify
Each guardrail plugs into a node: input hygiene + scope at router, refuse-on-low-
coverage at grade, citation verification at verify.
"""

from __future__ import annotations

from app.agent import prompts
from app.agent.context import ctx_from_config
from app.agent.state import AgentState
from app.guardrails.citation import normalize_article, verify_citations
from app.guardrails.coverage import REFUSAL_MESSAGE
from app.guardrails.input import strip_prompt_injection


def _accum_usage(state: AgentState, out: dict) -> None:
    u = state.setdefault("usage", {})
    u["prompt_tokens"] = u.get("prompt_tokens", 0) + out.get("prompt_tokens", 0)
    u["completion_tokens"] = u.get("completion_tokens", 0) + out.get("completion_tokens", 0)
    u["chat_model"] = out.get("model", u.get("chat_model", ""))


def router(state: AgentState, config: dict) -> AgentState:
    ctx = ctx_from_config(config)
    question = strip_prompt_injection(state["question"]).strip()
    state["query_text"] = question
    state.setdefault("attempts", 0)
    state.setdefault("regens", 0)
    state.setdefault("usage", {})

    out = ctx.llm.chat_json(prompts.ROUTER_SYS, prompts.router_user(question), temperature=0.0)
    _accum_usage(state, out)
    route = out["data"].get("route", "single_rule")
    if route not in ("single_rule", "precedent", "out_of_scope"):
        route = "single_rule"
    state["route"] = route

    if route == "out_of_scope":
        state["refused"] = True
        state["answer"] = (
            "I can only help with Formula 1 rules, penalties, and steward decisions. "
            "Ask me about an incident, a penalty, or what a sporting regulation says."
        )
        state["docs"] = []
        state["citations"] = []
        state["verified"] = True
    return state


def retrieve(state: AgentState, config: dict) -> AgentState:
    from app.retrieval.hybrid import (
        detect_grand_prix,
        detect_season,
        expand_to_parents,
        hybrid_retrieve,
        is_standings_query,
        latest_season,
    )

    ctx = ctx_from_config(config)
    cfg = state.get("config", {})
    mode = cfg.get("mode", ctx.settings.retrieval_mode)
    top_k = cfg.get("top_k", ctx.settings.top_k)
    candidate_k = cfg.get("candidate_k", ctx.settings.candidate_k)
    table = cfg.get("table", ctx.embedder.table)

    # Scope to the Grand Prix named in the question (if any) so the many near-identical
    # session-result chunks from other races don't crowd retrieval. Keeps global regs.
    filters = dict(cfg.get("filters") or {})
    question = state["question"]
    gp = detect_grand_prix(state.get("query_text") or question)
    if gp and "grand_prix" not in filters:
        filters["grand_prix"] = gp
    if "season" not in filters:
        # An explicit year scopes to that season; a bare standings/results query
        # ("who's leading the championship") defaults to the latest season ingested.
        season = detect_season(question)
        if season is None and is_standings_query(question):
            season = latest_season(ctx.conn)
        if season:
            filters["season"] = season
    filters = filters or None

    query = state["query_text"]
    query_vec = None
    if mode in ("dense", "hybrid"):
        before = getattr(ctx.embedder, "embed_tokens", 0)
        query_vec = ctx.embedder.embed([query])[0]
        delta = getattr(ctx.embedder, "embed_tokens", 0) - before
        state["usage"]["embed_tokens"] = state["usage"].get("embed_tokens", 0) + delta
        state["usage"]["embed_model_name"] = getattr(ctx.embedder, "model", ctx.embedder.name)

    ids = hybrid_retrieve(
        ctx.conn, query, query_vec, table=table, k=candidate_k, mode=mode, filters=filters
    )
    docs = expand_to_parents(ctx.conn, ids)

    if ctx.reranker is not None and docs:
        docs = ctx.reranker.rerank(query, docs, top_n=top_k)
    else:
        docs = docs[:top_k]

    state["docs"] = docs
    return state


def grade(state: AgentState, config: dict) -> AgentState:
    ctx = ctx_from_config(config)
    docs = state.get("docs", [])
    if not docs:
        state["grade"] = 0.0
        state["grade_missing"] = "no documents retrieved"
        return state
    out = ctx.llm.chat_json(
        prompts.GRADER_SYS, prompts.grader_user(state["question"], docs), temperature=0.0
    )
    _accum_usage(state, out)
    try:
        state["grade"] = max(0.0, min(1.0, float(out["data"].get("grade", 0.0))))
    except (TypeError, ValueError):
        state["grade"] = 0.0
    state["grade_missing"] = str(out["data"].get("missing", ""))
    return state


def rewrite(state: AgentState, config: dict) -> AgentState:
    ctx = ctx_from_config(config)
    out = ctx.llm.chat(
        prompts.REWRITE_SYS,
        prompts.rewrite_user(state["question"], state.get("grade_missing", "")),
        temperature=0.3,
        max_tokens=80,
    )
    _accum_usage(state, out)
    new_q = out["text"].strip().strip('"')
    if new_q:
        state["query_text"] = new_q
    state["attempts"] = state.get("attempts", 0) + 1
    return state


def refuse(state: AgentState, config: dict) -> AgentState:
    state["refused"] = True
    state["answer"] = REFUSAL_MESSAGE
    state["citations"] = []
    state["verified"] = True
    return state


def generate(state: AgentState, config: dict) -> AgentState:
    ctx = ctx_from_config(config)
    out = ctx.llm.chat(
        prompts.GENERATOR_SYS,
        prompts.generator_user(state["question"], state.get("docs", [])),
    )
    _accum_usage(state, out)
    state["answer"] = out["text"].strip()
    state["refused"] = False
    return state


def _build_citations(verified: list[str], docs: list[dict]) -> list[dict]:
    by_article: dict[str, dict] = {}
    for d in docs:
        if d.get("article_id"):
            by_article.setdefault(normalize_article(d["article_id"]), d)
    cites = []
    for art in verified:
        d = by_article.get(normalize_article(art))
        cites.append(
            {
                "article_id": art,
                "doc": (d or {}).get("source_file", ""),
                "doc_subtype": (d or {}).get("doc_subtype"),
                "snippet": (d or {}).get("snippet", ""),
                "verified": True,
            }
        )
    return cites


def verify(state: AgentState, config: dict) -> AgentState:
    docs = state.get("docs", [])
    article_ids = [d.get("article_id") for d in docs]
    verified, unverified = verify_citations(state["answer"], article_ids)
    state["citations"] = _build_citations(verified, docs)

    if not unverified:
        state["verified"] = True
        return state

    # Unverified citations remain. Allow one regeneration; otherwise finalize with
    # a caveat (do not loop / burn cost).
    if state.get("regens", 0) < 1:
        state["regens"] = state.get("regens", 0) + 1
        state["verified"] = False
        return state

    state["verified"] = False
    state["answer"] += (
        "\n\n_Note: some cited articles could not be verified against the retrieved "
        f"sources ({', '.join(unverified)}); treat those with caution._"
    )
    return state
