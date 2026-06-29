"""Observability: write one query_log row per request and aggregate metrics."""

from __future__ import annotations

import json

from psycopg import Connection
from psycopg.types.json import Jsonb


def write_query_log(conn: Connection, payload: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO query_log
                (question, route, retrieved_ids, grade, attempts, verified, refused,
                 answer, citations, latency_ms, ttft_ms, prompt_tokens,
                 completion_tokens, embed_tokens, cost_usd, config)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                payload.get("question"),
                payload.get("route"),
                payload.get("retrieved_ids") or [],
                payload.get("grade"),
                payload.get("attempts"),
                payload.get("verified"),
                payload.get("refused"),
                payload.get("answer"),
                Jsonb(payload.get("citations") or []),
                payload.get("latency_ms"),
                payload.get("ttft_ms"),
                payload.get("prompt_tokens"),
                payload.get("completion_tokens"),
                payload.get("embed_tokens"),
                payload.get("cost_usd"),
                Jsonb(payload.get("config") or {}),
            ),
        )
    conn.commit()


def requests_today(conn: Connection) -> int:
    """Count /ask requests logged since the start of the current UTC day."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM query_log WHERE ts >= date_trunc('day', now())")
        return cur.fetchone()[0]


def aggregate_metrics(conn: Connection) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                count(*) AS n,
                percentile_disc(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency,
                percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency,
                avg(cost_usd) AS avg_cost,
                avg(latency_ms) AS avg_latency,
                count(*) FILTER (WHERE refused) AS refused,
                count(*) FILTER (WHERE verified) AS verified
            FROM query_log
            """
        )
        row = cur.fetchone()
        cur.execute(
            """SELECT width_bucket(grade, 0, 1.0001, 5) AS b, count(*)
               FROM query_log WHERE grade IS NOT NULL GROUP BY b ORDER BY b"""
        )
        hist = {int(b): int(c) for b, c in cur.fetchall()}

    n = row[0] or 0
    return {
        "queries": n,
        "p50_latency_ms": row[1],
        "p95_latency_ms": row[2],
        "avg_cost_usd": round(float(row[3]), 6) if row[3] is not None else 0.0,
        "avg_latency_ms": round(float(row[4]), 1) if row[4] is not None else 0.0,
        "refusal_rate": round((row[5] or 0) / n, 3) if n else 0.0,
        "verified_rate": round((row[6] or 0) / n, 3) if n else 0.0,
        "grade_histogram": hist,
    }


def to_json(obj: dict) -> str:
    return json.dumps(obj, default=str)
