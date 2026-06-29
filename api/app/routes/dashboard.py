"""GET /metrics (JSON) and GET /dashboard (HTML) over the query_log."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.db.pool import get_conn
from app.logging_ import aggregate_metrics

router = APIRouter()


@router.get("/metrics")
def metrics() -> dict:
    with get_conn() as conn:
        return aggregate_metrics(conn)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    with get_conn() as conn:
        m = aggregate_metrics(conn)
    hist = m.get("grade_histogram", {})
    bars = "".join(
        f"<div class='bar'><span style='height:{min(100, c * 14)}px'></span>"
        f"<label>{(b - 1) * 20}-{b * 20}%<br>{c}</label></div>"
        for b, c in sorted(hist.items())
    )
    return f"""<!doctype html><html><head><meta charset=utf-8>
<title>F1 RAG — Observability</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;background:#0b0e14;color:#e6e6e6}}
 h1{{font-weight:600}} .grid{{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}}
 .card{{background:#141a24;border:1px solid #232b38;border-radius:10px;padding:1rem 1.4rem;min-width:150px}}
 .card .v{{font-size:1.8rem;font-weight:700;color:#ff2e63}} .card .k{{font-size:.8rem;color:#8a93a2}}
 .bars{{display:flex;gap:.6rem;align-items:flex-end;height:140px;margin-top:1rem}}
 .bar{{display:flex;flex-direction:column;align-items:center;justify-content:flex-end}}
 .bar span{{display:block;width:34px;background:#ff2e63;border-radius:4px 4px 0 0}}
 .bar label{{font-size:.7rem;color:#8a93a2;text-align:center;margin-top:.3rem}}
</style></head><body>
<h1>F1 Rule &amp; Penalty Interpreter — Observability</h1>
<div class=grid>
 <div class=card><div class=v>{m['queries']}</div><div class=k>queries</div></div>
 <div class=card><div class=v>{m['p50_latency_ms'] or 0}</div><div class=k>p50 latency (ms)</div></div>
 <div class=card><div class=v>{m['p95_latency_ms'] or 0}</div><div class=k>p95 latency (ms)</div></div>
 <div class=card><div class=v>${m['avg_cost_usd']:.4f}</div><div class=k>avg cost / query</div></div>
 <div class=card><div class=v>{m['refusal_rate'] * 100:.0f}%</div><div class=k>refusal rate</div></div>
 <div class=card><div class=v>{m['verified_rate'] * 100:.0f}%</div><div class=k>citation-verified rate</div></div>
</div>
<h3>Retrieval grade distribution</h3>
<div class=bars>{bars or '<em>no data yet</em>'}</div>
</body></html>"""
