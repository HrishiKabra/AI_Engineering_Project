"""API tests with the agent + DB mocked, so they run offline (no OpenAI, no live data)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.agent.state import AgentState
from app.deps import get_ctx
from app.main import create_app


class _FakeCtx:
    """Stand-in for AgentContext; the conn is only used by the (mocked) logger."""

    conn = None


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_ctx] = lambda: _FakeCtx()

    # Mock the agent so no OpenAI/db is touched.
    def fake_run_agent(ctx, question, config=None) -> AgentState:
        if "weather" in question.lower():
            return {"answer": "out of scope", "route": "out_of_scope", "refused": True,
                    "verified": True, "citations": [], "docs": [], "usage": {}}
        return {
            "answer": "Lap times are deleted under [Article 33.3].",
            "route": "single_rule", "grade": 0.9, "attempts": 0,
            "verified": True, "refused": False,
            "citations": [{"article_id": "33.3", "doc": "x.pdf", "snippet": "...",
                           "verified": True}],
            "docs": [{"chunk_id": 1, "article_id": "33.3"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "embed_tokens": 5,
                      "chat_model": "gpt-4o-mini", "embed_model_name": "text-embedding-3-small"},
        }

    monkeypatch.setattr("app.routes.ask.run_agent", fake_run_agent)
    monkeypatch.setattr("app.routes.ask.write_query_log", lambda conn, payload: None)
    return TestClient(app)


def test_ask_non_stream(client):
    r = client.post("/ask", json={"question": "Why are lap times deleted?", "stream": False})
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "single_rule"
    assert body["verified"] is True
    assert body["citations"][0]["article_id"] == "33.3"
    assert body["cost_usd"] > 0
    assert body["prompt_tokens"] == 100


def test_ask_refusal(client):
    r = client.post("/ask", json={"question": "what's the weather?", "stream": False})
    assert r.json()["refused"] is True


def test_ask_stream_sse(client):
    r = client.post("/ask", json={"question": "Why are lap times deleted?", "stream": True})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    body = r.text
    assert "event: token" in body
    assert "event: citation" in body
    assert "event: done" in body
    # The done event carries the full structured response.
    done_line = [ln for ln in body.splitlines() if ln.startswith("data:") and "answer" in ln][-1]
    payload = json.loads(done_line[len("data:") :].strip())
    assert payload["route"] == "single_rule"
