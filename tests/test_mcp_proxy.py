"""Public knowledge-base MCP proxy (GET /api/mcp/tools, POST /api/mcp/call)."""

import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.config import config
from app.modules import mcp_proxy
from main import app

client = TestClient(app)

_CALL_KEYS = {
    "tool",
    "arguments",
    "latency_ms",
    "result",
    "is_error",
    "error_text",
    "mock",
    "clamped",
}


def _refuse(request: httpx.Request) -> httpx.Response:
    host = request.url.host or "mcp"
    raise AssertionError(f"unexpected MCP network call to {host}")


@pytest.fixture(autouse=True)
def _isolate_mcp(monkeypatch, tmp_path):
    """Drop MCP env, disable the demo limiter, and refuse real network calls."""
    for key in (
        "MCP_URL",
        "MCP_TOKEN",
        "MCP_ENABLE_CHUNK_CONTEXT",
        "MCP_ALLOW_PAID",
        "MCP_MOCK",
        "MCP_NOTICE",
        "MCP_RATE_MIN_INTERVAL_MS",
        "MCP_RATE_PER_MINUTE",
    ):
        monkeypatch.delenv(key, raising=False)
    # pydantic-settings does not export .env into os.environ; keep tests off the repo file.
    monkeypatch.setattr(mcp_proxy, "_DOTENV_PATH", tmp_path / "absent.env")
    mcp_proxy._dotenv_cache = None
    monkeypatch.setattr(config.rate_limit, "enabled", False)
    with mcp_proxy.mcp_limiter._lock:
        mcp_proxy.mcp_limiter._hits.clear()
    with mcp_proxy._cache_lock:
        mcp_proxy._tools_cache = None
    mcp_proxy.refresh_rate_limits()
    monkeypatch.setattr(
        mcp_proxy, "_client", httpx.Client(transport=httpx.MockTransport(_refuse))
    )


def _install(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        mcp_proxy, "_client", httpx.Client(transport=httpx.MockTransport(handler))
    )


def _post(tool: str, arguments: dict | None = None):
    return client.post(
        "/api/mcp/call", json={"tool": tool, "arguments": arguments or {}}
    )


def _enable(monkeypatch, url: str = "http://mcp.test/mcp") -> None:
    monkeypatch.setenv("MCP_URL", url)


class TestWhitelist:
    def test_unknown_tool_is_400_and_not_forwarded(self, monkeypatch):
        _enable(monkeypatch)
        response = _post("search_fengshu_knowledge_multi", {"query": "增长"})
        assert response.status_code == 400
        assert response.json()["message"] == "不支持该工具。"

        response = _post("not_a_tool", {})
        assert response.status_code == 400
        assert "不支持" in response.json()["message"]

    def test_chunk_context_disabled_by_default(self, monkeypatch):
        _enable(monkeypatch)
        response = _post(
            "get_chunk_context",
            {"document_id": "doc-1", "chunk_id": "chunk-1"},
        )
        assert response.status_code == 400
        assert response.json()["message"] == "get_chunk_context 暂未开放。"

    @pytest.mark.parametrize(
        ("flag", "allowed"),
        [
            ("1", True),
            ("true", True),
            ("TRUE", True),
            (" true ", True),
            ("yes", False),
            ("0", False),
        ],
    )
    def test_chunk_context_flag(self, monkeypatch, flag, allowed):
        monkeypatch.setenv("MCP_MOCK", "1")
        monkeypatch.setenv("MCP_ENABLE_CHUNK_CONTEXT", flag)
        response = _post(
            "get_chunk_context",
            {"document_id": "doc-1", "chunk_id": "chunk-1", "before": 5, "after": 3},
        )
        if not allowed:
            assert response.status_code == 400
            return
        assert response.status_code == 200
        body = response.json()
        assert body["mock"] is True
        assert body["arguments"]["before"] == 2
        assert body["arguments"]["after"] == 2
        assert "before 5 → 2" in body["clamped"]
        assert "after 3 → 2" in body["clamped"]
        relations = [chunk["relation"] for chunk in body["result"]["chunks"]]
        assert relations.count("before") == 2
        assert "target" in relations
        assert relations.count("after") == 2


class TestClamping:
    def test_search_clamps_and_drops_unknown_keys(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        response = _post(
            "search_fengshu_knowledge",
            {
                "query": "  增长  ",
                "top_k": 50,
                "mode": "bogus",
                "source_scope": "paid",
                "date_from": "2024-01-02",
                "date_to": "2024/01/02",
                "debug": True,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["arguments"] == {
            "query": "增长",
            "top_k": 5,
            "mode": "balanced",
            "source_scope": "free",
            "date_from": "2024-01-02",
        }
        assert "top_k 50 → 5" in body["clamped"]
        assert "mode bogus → balanced" in body["clamped"]
        assert "source_scope → free" in body["clamped"]
        assert "忽略无效日期 date_to" in body["clamped"]
        assert "忽略未知参数 debug" in body["clamped"]

    def test_article_max_chars_clamped(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        high = _post(
            "get_fengshu_article", {"document_id": "doc-1", "max_chars": 99999}
        )
        assert high.status_code == 200
        assert high.json()["arguments"]["max_chars"] == 3000
        assert "max_chars 99999 → 3000" in high.json()["clamped"]

        low = _post("get_fengshu_article", {"document_id": "doc-1", "max_chars": 10})
        assert low.status_code == 200
        assert low.json()["arguments"]["max_chars"] == 500
        assert "max_chars 10 → 500" in low.json()["clamped"]

    def test_query_bounds(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        short = _post("search_fengshu_knowledge", {"query": "  a  "})
        assert short.status_code == 422
        assert short.json()["message"] == "检索词至少需要 2 个字。"

        too_long = _post("search_fengshu_knowledge", {"query": "x" * 201})
        assert too_long.status_code == 422
        assert too_long.json()["message"] == "检索词请控制在 200 个字以内。"

        ok = _post("search_fengshu_knowledge", {"query": "x" * 200})
        assert ok.status_code == 200
        assert ok.json()["arguments"]["query"] == "x" * 200

    def test_bad_document_id(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        assert (
            _post("get_fengshu_article", {"document_id": "../secret"}).status_code
            == 422
        )
        assert (
            _post("get_fengshu_article", {"document_id": "a" * 129}).status_code == 422
        )
        assert _post("get_fengshu_article", {}).status_code == 422
        ok = _post("get_fengshu_article", {"document_id": "a" * 128})
        assert ok.status_code == 200


class TestDotenv:
    def test_file_value_is_used_until_environ_overrides(self, monkeypatch, tmp_path):
        env_file = tmp_path / "demo.env"
        env_file.write_text(
            "MCP_URL=http://from-file.example/mcp\nMCP_RATE_PER_MINUTE=7\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(mcp_proxy, "_DOTENV_PATH", env_file)
        mcp_proxy._dotenv_cache = None
        monkeypatch.delenv("MCP_URL", raising=False)
        monkeypatch.delenv("MCP_RATE_PER_MINUTE", raising=False)

        settings = mcp_proxy.get_settings()
        assert settings.url == "http://from-file.example/mcp"
        assert settings.available is True
        mcp_proxy.refresh_rate_limits()
        assert mcp_proxy.mcp_limiter.per_minute == 7

        monkeypatch.setenv("MCP_URL", "http://from-env.example/mcp")
        monkeypatch.setenv("MCP_RATE_PER_MINUTE", "9")
        assert mcp_proxy.get_settings().url == "http://from-env.example/mcp"
        mcp_proxy.refresh_rate_limits()
        assert mcp_proxy.mcp_limiter.per_minute == 9


class TestAvailability:
    def test_unset_url_is_unavailable(self):
        listed = client.get("/api/mcp/tools")
        assert listed.status_code == 200
        body = listed.json()
        assert body["available"] is False
        assert body["mock"] is False
        assert body["server"] == "fengshu-knowledge"
        assert body["tools"] == []
        assert body["message"] == "体验暂不可用"
        assert body["degraded"] is False

        called = _post("search_fengshu_knowledge", {"query": "增长"})
        assert called.status_code == 503
        assert called.json() == {"message": "体验暂不可用"}


def _rpc_result(request: httpx.Request, result: dict) -> dict:
    body = json.loads(request.content)
    return {"jsonrpc": "2.0", "id": body["id"], "result": result}


def _assert_call_shape(body: dict, *, mock: bool) -> None:
    assert set(body) == _CALL_KEYS
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0
    assert body["mock"] is mock
    assert isinstance(body["clamped"], list)


class TestJsonRpc:
    def test_sse_tools_call_is_sanitized_and_parsed(self, monkeypatch):
        _enable(monkeypatch)
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            payload = json.loads(request.content)
            decoy = {
                "jsonrpc": "2.0",
                "id": "other",
                "result": {
                    "structuredContent": {"query": "WRONG", "count": 1, "results": []}
                },
            }
            result = {
                "content": [{"type": "text", "text": "ok"}],
                "isError": False,
                "structuredContent": {
                    "query": "增长",
                    "count": 3,
                    "results": [
                        {
                            "document_id": "free-1",
                            "title": "免费",
                            "access": "free",
                            "snippet": "长" * 700,
                            "chunk_id": "c1",
                            "chunk_index": 0,
                        },
                        {
                            "document_id": "secret-doc",
                            "title": "付费",
                            "access": "paid",
                            "snippet": "PAIDSNIPPETSECRET",
                            "chunk_id": "c2",
                            "chunk_index": 1,
                        },
                        {
                            "document_id": "free-2",
                            "title": "短",
                            "access": "free",
                            "snippet": "可见片段",
                            "chunk_id": "c3",
                            "chunk_index": 2,
                        },
                    ],
                },
            }
            real = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
            text = (
                "event: message\n"
                f"data: {json.dumps(decoy, ensure_ascii=False)}\n"
                "\n"
                "event: message\n"
                f"data: {json.dumps(real, ensure_ascii=False)}\n"
                "\n"
            )
            return httpx.Response(
                200, text=text, headers={"Content-Type": "text/event-stream"}
            )

        _install(monkeypatch, handler)
        response = _post(
            "search_fengshu_knowledge",
            {
                "query": "  增长  ",
                "top_k": 50,
                "mode": "bogus",
                "source_scope": "paid",
                "date_from": "2024-01-02",
                "date_to": "nope",
                "debug": True,
            },
        )
        assert response.status_code == 200
        assert len(seen) == 1
        request = seen[0]
        sent = json.loads(request.content)
        assert sent["jsonrpc"] == "2.0"
        assert sent["method"] == "tools/call"
        assert sent["params"]["name"] == "search_fengshu_knowledge"
        assert sent["params"]["arguments"] == {
            "query": "增长",
            "top_k": 5,
            "mode": "balanced",
            "source_scope": "free",
            "date_from": "2024-01-02",
        }
        assert "text/event-stream" in request.headers["accept"]
        assert "application/json" in request.headers["accept"]
        assert "authorization" not in request.headers
        assert "mcp-session-id" not in {key.lower() for key in request.headers}

        body = response.json()
        _assert_call_shape(body, mock=False)
        assert body["is_error"] is False
        assert body["error_text"] is None
        assert body["arguments"] == sent["params"]["arguments"]
        assert "PAIDSNIPPETSECRET" not in response.text
        assert "secret-doc" not in response.text
        assert "WRONG" not in response.text
        snippets = {row["document_id"]: row for row in body["result"]["results"]}
        assert set(snippets) == {"free-1", "free-2"}
        assert body["result"]["count"] == 2
        assert len(snippets["free-1"]["snippet"]) == 600
        assert snippets["free-1"]["snippet_truncated"] is True
        assert "长" * 601 not in response.text
        assert snippets["free-2"]["snippet"] == "可见片段"
        assert "snippet_truncated" not in snippets["free-2"]

    def test_bearer_only_when_token_set(self, monkeypatch):
        _enable(monkeypatch)
        monkeypatch.setenv("MCP_TOKEN", "header-secret")
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            result = {
                "content": [{"type": "text", "text": "ok"}],
                "isError": False,
                "structuredContent": {"query": "增长", "count": 0, "results": []},
            }
            return httpx.Response(200, json=_rpc_result(request, result))

        _install(monkeypatch, handler)
        response = _post("search_fengshu_knowledge", {"query": "增长"})
        assert response.status_code == 200
        assert seen[0].headers["authorization"] == "Bearer header-secret"
        assert b"header-secret" not in seen[0].content

    def test_plain_json_body_parsed(self, monkeypatch):
        _enable(monkeypatch)
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            sent = json.loads(request.content)
            assert sent["method"] == "tools/call"
            assert sent["params"]["arguments"]["max_chars"] == 3000
            result = {
                "content": [{"type": "text", "text": "hello"}],
                "isError": False,
                "structuredContent": {
                    "document_id": "doc-1",
                    "title": "示例标题",
                    "access": "free",
                    "content": "hello",
                    "offset": 0,
                    "next_offset": None,
                    "total_chars": 5,
                },
            }
            return httpx.Response(200, json=_rpc_result(request, result))

        _install(monkeypatch, handler)
        response = _post(
            "get_fengshu_article", {"document_id": "doc-1", "max_chars": 99999}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"]["content"] == "hello"
        assert body["is_error"] is False
        assert body["mock"] is False
        assert len(seen) == 1

    def test_jsonrpc_error_is_502(self, monkeypatch):
        _enable(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "error": {
                        "code": -32603,
                        "message": "Traceback (most recent call last): secret-stack",
                    },
                },
            )

        _install(monkeypatch, handler)
        response = _post("search_fengshu_knowledge", {"query": "增长"})
        assert response.status_code == 502
        assert response.json() == {"message": "知识库 MCP 调用失败，请稍后重试"}
        assert "secret-stack" not in response.text
        assert "Traceback" not in response.text

    def test_timeout_is_502(self, monkeypatch):
        _enable(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        _install(monkeypatch, handler)
        response = _post("search_fengshu_knowledge", {"query": "增长"})
        assert response.status_code == 502
        assert response.json() == {"message": "知识库 MCP 响应超时，请稍后重试"}

    def test_http_error_hides_upstream_body(self, monkeypatch):
        _enable(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Traceback secret-stack")

        _install(monkeypatch, handler)
        response = _post("search_fengshu_knowledge", {"query": "增长"})
        assert response.status_code == 502
        assert response.json() == {"message": "知识库 MCP 暂时不可用，请稍后重试"}
        assert "secret-stack" not in response.text

    def test_is_error_is_surfaced(self, monkeypatch):
        _enable(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            result = {
                "isError": True,
                "content": [{"type": "text", "text": "未找到文章"}],
                "structuredContent": {"document_id": "doc-1"},
            }
            return httpx.Response(200, json=_rpc_result(request, result))

        _install(monkeypatch, handler)
        response = _post("get_fengshu_article", {"document_id": "doc-1"})
        assert response.status_code == 200
        body = response.json()
        assert body["is_error"] is True
        assert body["error_text"] == "未找到文章"
        assert body["result"]["document_id"] == "doc-1"

    def test_success_log_omits_url_query(self, monkeypatch, caplog):
        _enable(
            monkeypatch,
            "http://user:header-secret@mcp.test/t/query-secret?token=query-secret",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            result = {
                "isError": False,
                "content": [{"type": "text", "text": "ok"}],
                "structuredContent": {"query": "增长", "count": 0, "results": []},
            }
            return httpx.Response(200, json=_rpc_result(request, result))

        _install(monkeypatch, handler)
        caplog.set_level(logging.DEBUG)
        response = _post("search_fengshu_knowledge", {"query": "增长"})
        assert response.status_code == 200
        assert "query-secret" not in caplog.text
        assert "header-secret" not in caplog.text

    def test_logs_omit_token_and_url_query(self, monkeypatch, caplog):
        _enable(monkeypatch, "http://mcp.test/mcp?token=query-secret")
        monkeypatch.setenv("MCP_TOKEN", "header-secret")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(
                "failed http://mcp.test/mcp?token=query-secret header-secret",
                request=request,
            )

        _install(monkeypatch, handler)
        caplog.set_level(logging.DEBUG)
        response = _post("search_fengshu_knowledge", {"query": "增长"})
        assert response.status_code == 502
        assert "query-secret" not in response.text
        assert "header-secret" not in response.text
        assert "query-secret" not in caplog.text
        assert "header-secret" not in caplog.text


class TestPaidFilter:
    def test_paid_id_rejected_before_call(self, monkeypatch):
        _enable(monkeypatch)
        called: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            called.append(1)
            return httpx.Response(500, text="should-not-run")

        _install(monkeypatch, handler)
        response = _post("get_fengshu_article", {"document_id": "paid-abc"})
        assert response.status_code == 403
        assert response.json() == {"message": "付费文章不在公开体验范围内"}
        assert called == []

    def test_upstream_paid_access_is_403(self, monkeypatch):
        _enable(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            result = {
                "isError": False,
                "content": [{"type": "text", "text": "SECRET_PAID_BODY"}],
                "structuredContent": {
                    "document_id": "doc-hidden",
                    "access": "paid",
                    "content": "SECRET_PAID_BODY",
                    "offset": 0,
                    "next_offset": None,
                    "total_chars": 16,
                },
            }
            return httpx.Response(200, json=_rpc_result(request, result))

        _install(monkeypatch, handler)
        response = _post("get_fengshu_article", {"document_id": "doc-hidden"})
        assert response.status_code == 403
        assert response.json() == {"message": "付费文章不在公开体验范围内"}
        assert "SECRET_PAID_BODY" not in response.text

    def test_allow_paid_keeps_paid_content(self, monkeypatch):
        _enable(monkeypatch)
        monkeypatch.setenv("MCP_ALLOW_PAID", "1")

        def handler(request: httpx.Request) -> httpx.Response:
            sent = json.loads(request.content)
            if sent["params"]["name"] == "search_fengshu_knowledge":
                assert sent["params"]["arguments"]["source_scope"] == "paid"
                result = {
                    "isError": False,
                    "content": [{"type": "text", "text": "ok"}],
                    "structuredContent": {
                        "query": "增长",
                        "count": 1,
                        "results": [
                            {
                                "document_id": "secret-doc",
                                "access": "paid",
                                "snippet": "PAIDSNIPPETSECRET",
                            }
                        ],
                    },
                }
            else:
                result = {
                    "isError": False,
                    "content": [{"type": "text", "text": "SECRET_PAID_BODY"}],
                    "structuredContent": {
                        "document_id": sent["params"]["arguments"]["document_id"],
                        "access": "paid",
                        "content": "SECRET_PAID_BODY",
                    },
                }
            return httpx.Response(200, json=_rpc_result(request, result))

        _install(monkeypatch, handler)
        search = _post(
            "search_fengshu_knowledge",
            {"query": "增长", "source_scope": "paid"},
        )
        assert search.status_code == 200
        assert search.json()["result"]["results"][0]["snippet"] == "PAIDSNIPPETSECRET"
        article = _post("get_fengshu_article", {"document_id": "paid-xyz"})
        assert article.status_code == 200
        assert article.json()["result"]["content"] == "SECRET_PAID_BODY"


class TestToolsList:
    def test_mock_lists_whitelist_without_network(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        monkeypatch.setenv("MCP_URL", "http://mcp.test/mcp?token=query-secret")
        response = client.get("/api/mcp/tools")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["mock"] is True
        assert body["degraded"] is False
        assert body["chunk_context_enabled"] is False
        assert body["server"] == "fengshu-knowledge"
        assert "message" not in body
        assert body["notice"] == mcp_proxy.MOCK_NOTICE
        names = [tool["name"] for tool in body["tools"]]
        assert names == ["search_fengshu_knowledge", "get_fengshu_article"]
        assert "query" in body["tools"][0]["inputSchema"]["properties"]

    def test_notice_override_applies_in_any_mode(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        monkeypatch.setenv("MCP_NOTICE", "自定义说明")
        assert client.get("/api/mcp/tools").json()["notice"] == "自定义说明"

        monkeypatch.delenv("MCP_MOCK")
        monkeypatch.setenv("MCP_URL", "http://mcp.test/mcp")
        monkeypatch.setattr(mcp_proxy, "list_tools", lambda: ([], False))
        live = client.get("/api/mcp/tools").json()
        assert live["mock"] is False
        assert live["notice"] == "自定义说明"

        monkeypatch.delenv("MCP_NOTICE")
        assert client.get("/api/mcp/tools").json()["notice"] is None

    def test_upstream_list_filters_and_caches(self, monkeypatch):
        _enable(monkeypatch)
        monkeypatch.setenv("MCP_TOKEN", "sekret")
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            payload = json.loads(request.content)
            result = {
                "tools": [
                    {
                        "name": "search_fengshu_knowledge",
                        "title": "Search",
                        "description": "find",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                        "annotations": {"secret": "nope"},
                    },
                    {
                        "name": "search_fengshu_knowledge_multi",
                        "title": "Multi",
                        "description": "hidden",
                        "inputSchema": {},
                    },
                    {
                        "name": "get_chunk_context",
                        "title": "Ctx",
                        "description": "ctx",
                        "inputSchema": {},
                    },
                    {
                        "name": "get_fengshu_article",
                        "title": "Article",
                        "description": "read",
                        "inputSchema": {"type": "object"},
                    },
                ]
            }
            real = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
            text = f"event: message\ndata: {json.dumps(real)}\n\n"
            return httpx.Response(
                200, text=text, headers={"Content-Type": "text/event-stream"}
            )

        _install(monkeypatch, handler)
        first = client.get("/api/mcp/tools").json()
        second = client.get("/api/mcp/tools").json()
        assert first == second
        assert first["degraded"] is False
        assert first["available"] is True
        names = [tool["name"] for tool in first["tools"]]
        assert names == ["search_fengshu_knowledge", "get_fengshu_article"]
        assert set(first["tools"][0]) == {"name", "title", "description", "inputSchema"}
        assert first["tools"][0]["title"] == "Search"
        assert (
            first["tools"][0]["inputSchema"]["properties"]["query"]["type"] == "string"
        )
        assert len(seen) == 1
        assert json.loads(seen[0].content)["method"] == "tools/list"
        assert seen[0].headers["authorization"] == "Bearer sekret"

    def test_list_failure_is_degraded_fallback(self, monkeypatch):
        _enable(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Traceback secret-stack")

        _install(monkeypatch, handler)
        response = client.get("/api/mcp/tools")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["degraded"] is True
        assert body["mock"] is False
        names = [tool["name"] for tool in body["tools"]]
        assert names == ["search_fengshu_knowledge", "get_fengshu_article"]
        assert "query" in body["tools"][0]["inputSchema"]["properties"]
        assert "document_id" in body["tools"][1]["inputSchema"]["properties"]
        assert "secret-stack" not in response.text

        monkeypatch.setenv("MCP_ENABLE_CHUNK_CONTEXT", "1")
        with mcp_proxy._cache_lock:
            mcp_proxy._tools_cache = None
        again = client.get("/api/mcp/tools").json()
        assert [tool["name"] for tool in again["tools"]] == [
            "search_fengshu_knowledge",
            "get_fengshu_article",
            "get_chunk_context",
        ]


class TestRateLimit:
    def test_second_immediate_call_is_429(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        monkeypatch.setenv("MCP_RATE_MIN_INTERVAL_MS", "60000")
        monkeypatch.setattr(config.rate_limit, "enabled", True)
        with mcp_proxy.mcp_limiter._lock:
            mcp_proxy.mcp_limiter._hits.clear()
        first = _post("search_fengshu_knowledge", {"query": "增长"})
        second = _post("search_fengshu_knowledge", {"query": "留存"})
        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["message"] == "发送太频繁，请稍后再试。"
        assert second.json()["retry_after"] >= 1
        assert int(second.headers["retry-after"]) >= 1

    def test_per_minute_cap(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        monkeypatch.setenv("MCP_RATE_MIN_INTERVAL_MS", "0")
        monkeypatch.setenv("MCP_RATE_PER_MINUTE", "3")
        monkeypatch.setattr(config.rate_limit, "enabled", True)
        with mcp_proxy.mcp_limiter._lock:
            mcp_proxy.mcp_limiter._hits.clear()
        for _ in range(3):
            assert (
                _post("search_fengshu_knowledge", {"query": "增长"}).status_code == 200
            )
        blocked = _post("search_fengshu_knowledge", {"query": "增长"})
        assert blocked.status_code == 429

    def test_disabled_flag_skips_limiter(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        monkeypatch.setenv("MCP_RATE_MIN_INTERVAL_MS", "60000")
        monkeypatch.setattr(config.rate_limit, "enabled", False)
        assert _post("search_fengshu_knowledge", {"query": "增长"}).status_code == 200
        assert _post("search_fengshu_knowledge", {"query": "留存"}).status_code == 200

    def test_uses_client_key(self, monkeypatch):
        """Same helper as /api/retrieve: proxy headers only from the local hop."""
        assert routes._client_key  # the endpoint closes over this helper
        monkeypatch.setenv("MCP_MOCK", "1")
        monkeypatch.setattr(config.rate_limit, "enabled", True)
        monkeypatch.setenv("MCP_RATE_MIN_INTERVAL_MS", "60000")
        with mcp_proxy.mcp_limiter._lock:
            mcp_proxy.mcp_limiter._hits.clear()
        headers = {"X-Real-IP": "1.2.3.4"}
        first = client.post(
            "/api/mcp/call",
            json={"tool": "search_fengshu_knowledge", "arguments": {"query": "增长"}},
            headers=headers,
        )
        second = client.post(
            "/api/mcp/call",
            json={"tool": "search_fengshu_knowledge", "arguments": {"query": "留存"}},
            headers=headers,
        )
        assert first.status_code == 200
        # TestClient's peer is not a trusted proxy, so the forged header is ignored
        # and both calls share one bucket.
        assert second.status_code == 429


class TestMockMode:
    def test_search_is_labelled_sample(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        response = _post("search_fengshu_knowledge", {"query": "增长", "top_k": 5})
        assert response.status_code == 200
        body = response.json()
        assert body["mock"] is True
        assert body["is_error"] is False
        assert body["error_text"] is None
        results = body["result"]["results"]
        assert len(results) == 3
        assert body["result"]["count"] == 3
        assert body["result"]["query"] == "增长"
        for row in results:
            assert row["title"].startswith("示例")
            assert row["access"] == "free"
            assert row["exact_match"] is False
        assert results[0]["title"] == "示例：增长"
        assert "增长" in results[0]["snippet"]

        exact = _post(
            "search_fengshu_knowledge",
            {"query": "做题家", "mode": "exact", "top_k": 5},
        )
        assert exact.status_code == 200
        exact_rows = exact.json()["result"]["results"]
        assert exact_rows[0]["title"] == "示例：做题家"
        assert exact_rows[0]["exact_match"] is True
        assert all(row["exact_match"] is False for row in exact_rows[1:])

    def test_article_paging_ends_with_null(self, monkeypatch):
        monkeypatch.setenv("MCP_MOCK", "1")
        offset = 0
        pages: list[str] = []
        total = None
        for _ in range(8):
            response = _post(
                "get_fengshu_article",
                {"document_id": "sample-doc-growth", "offset": offset},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["mock"] is True
            result = body["result"]
            assert result["offset"] == offset
            assert len(result["content"]) <= body["arguments"]["max_chars"]
            pages.append(result["content"])
            total = result["total_chars"]
            nxt = result["next_offset"]
            if nxt is None:
                break
            assert nxt == offset + len(result["content"])
            offset = nxt
        else:
            pytest.fail("next_offset never became null")
        assert total is not None
        assert total >= 4000
        assert total == sum(len(page) for page in pages)
        assert len(pages) >= 2
        assert result["title"].startswith("示例")
