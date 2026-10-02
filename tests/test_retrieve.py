"""POST /api/retrieve (retrieval-only demo) and its rate limiter."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.config import config
from app.modules.retrieval_demo import RetrievalRateLimiter
from main import app

client = TestClient(app)

FAKE_RESULT = {
    "query": "LangGraph",
    "k": 1,
    "metric": "cosine",
    "total_chunks": 7,
    "embedding_dims": 2048,
    "embed_ms": 10.0,
    "search_ms": 1.0,
    "took_ms": 11.0,
    "chunks": [
        {
            "rank": 1,
            "source": "cv",
            "source_label": "简历 PDF",
            "page": 1,
            "content": "…",
            "chars": 1,
            "similarity": 0.42,
            "distance": 1.16,
        }
    ],
}


@pytest.fixture
def ready(monkeypatch):
    calls = []

    def fake_retrieve(query):
        calls.append(query)
        return {**FAKE_RESULT, "query": query}

    monkeypatch.setattr(routes, "is_llm_configured", lambda: True)
    monkeypatch.setattr(routes, "retrieve_with_scores", fake_retrieve)
    monkeypatch.setattr(routes, "retrieval_limiter", RetrievalRateLimiter(0, 1000))
    return calls


class TestRetrieveEndpoint:
    def test_returns_chunks_with_scores(self, ready):
        response = client.post("/api/retrieve", json={"query": "  LangGraph  "})
        assert response.status_code == 200
        data = response.json()
        assert ready == ["LangGraph"]
        assert data["chunks"][0]["similarity"] == 0.42
        assert data["embedding_dims"] == 2048

    def test_rejects_empty_and_too_long(self, ready):
        assert client.post("/api/retrieve", json={"query": "   "}).status_code == 422
        too_long = "x" * (config.security.max_query_length + 1)
        assert client.post("/api/retrieve", json={"query": too_long}).status_code == 422
        assert ready == []

    def test_rate_limited(self, ready, monkeypatch):
        monkeypatch.setattr(config.rate_limit, "enabled", True)
        monkeypatch.setattr(routes, "retrieval_limiter", RetrievalRateLimiter(60_000, 1000))
        assert client.post("/api/retrieve", json={"query": "a"}).status_code == 200
        response = client.post("/api/retrieve", json={"query": "b"})
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1
        assert response.json()["message"]
        assert ready == ["a"]

    def test_not_configured_is_503(self, monkeypatch):
        monkeypatch.setattr(routes, "is_llm_configured", lambda: False)
        assert client.post("/api/retrieve", json={"query": "hi"}).status_code == 503

    def test_failure_is_generic_502(self, ready, monkeypatch):
        def boom(query):
            raise RuntimeError("upstream said sk-secret-123")

        monkeypatch.setattr(routes, "retrieve_with_scores", boom)
        response = client.post("/api/retrieve", json={"query": "hi"})
        assert response.status_code == 502
        assert "sk-secret" not in json.dumps(response.json())


class TestRateLimiter:
    def test_min_interval(self):
        limiter = RetrievalRateLimiter(1000, 100)
        assert limiter.check("ip", now=0.0) == 0
        assert limiter.check("ip", now=0.5) == pytest.approx(0.5)
        assert limiter.check("other", now=0.5) == 0
        assert limiter.check("ip", now=1.1) == 0

    def test_per_minute_cap(self):
        limiter = RetrievalRateLimiter(0, 3)
        for t in (0.0, 1.0, 2.0):
            assert limiter.check("ip", now=t) == 0
        assert limiter.check("ip", now=3.0) == pytest.approx(57.0)
        assert limiter.check("ip", now=61.0) == 0


class TestClientKey:
    def _req(self, peer, headers):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234),
        }
        return Request(scope)

    def test_trusts_headers_from_local_proxy(self):
        assert routes._client_key(self._req("127.0.0.1", {"X-Real-IP": "1.2.3.4"})) == "1.2.3.4"
        req = self._req("127.0.0.1", {"X-Forwarded-For": "6.6.6.6, 5.6.7.8"})
        assert routes._client_key(req) == "5.6.7.8"  # last hop (added by Nginx), not the forged first

    def test_ignores_headers_from_direct_clients(self):
        req = self._req("9.9.9.9", {"X-Real-IP": "1.2.3.4", "X-Forwarded-For": "1.2.3.4"})
        assert routes._client_key(req) == "9.9.9.9"
