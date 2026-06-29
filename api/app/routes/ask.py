"""POST /ask — run the agent and return a grounded, citation-verified answer.

Streaming uses Server-Sent Events. Per the design tradeoff, the compiled graph
runs to completion (so the citation-verification guardrail can act on the full
answer), then the answer is streamed to the client as ``token`` events followed by
``citation`` and a final ``done`` event carrying the full structured response.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.agent.context import AgentContext
from app.agent.graph import run_agent
from app.deps import get_ctx
from app.llm.cost import total_cost
from app.logging_ import to_json, write_query_log
from app.schemas import AskRequest, AskResponse

router = APIRouter()


def _execute(ctx: AgentContext, req: AskRequest) -> tuple[dict, AskResponse, list[int]]:
    t0 = time.perf_counter()
    state = run_agent(ctx, req.question, req.config)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    usage = state.get("usage", {})
    retrieved_ids = [d.get("chunk_id") for d in state.get("docs", []) if d.get("chunk_id")]
    resp = AskResponse(
        answer=state.get("answer", ""),
        citations=state.get("citations", []),
        route=state.get("route", ""),
        grade=round(float(state.get("grade", 0.0)), 3),
        attempts=state.get("attempts", 0),
        verified=bool(state.get("verified", False)),
        refused=bool(state.get("refused", False)),
        latency_ms=latency_ms,
        ttft_ms=latency_ms,  # pseudo-stream: answer is ready before streaming begins
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        embed_tokens=usage.get("embed_tokens", 0),
        cost_usd=total_cost(usage),
    )
    return state, resp, retrieved_ids


def _log(ctx: AgentContext, req: AskRequest, resp: AskResponse, retrieved_ids: list[int]) -> None:
    try:
        write_query_log(
            ctx.conn,
            {
                "question": req.question,
                "route": resp.route,
                "retrieved_ids": retrieved_ids,
                "grade": resp.grade,
                "attempts": resp.attempts,
                "verified": resp.verified,
                "refused": resp.refused,
                "answer": resp.answer,
                "citations": [c.model_dump() for c in resp.citations],
                "latency_ms": resp.latency_ms,
                "ttft_ms": resp.ttft_ms,
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
                "embed_tokens": resp.embed_tokens,
                "cost_usd": resp.cost_usd,
                "config": req.config or {},
            },
        )
    except Exception:
        # Logging must never break the response.
        pass


@router.post("/ask")
def ask(req: AskRequest, ctx: AgentContext = Depends(get_ctx)):
    state, resp, retrieved_ids = _execute(ctx, req)
    _log(ctx, req, resp, retrieved_ids)

    if not req.stream:
        return resp

    def event_gen():
        for word in resp.answer.split(" "):
            yield {"event": "token", "data": word + " "}
        for c in resp.citations:
            yield {"event": "citation", "data": to_json(c.model_dump())}
        yield {"event": "done", "data": to_json(resp.model_dump())}

    return EventSourceResponse(event_gen())
