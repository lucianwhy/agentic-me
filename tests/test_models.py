"""Admin-managed chat model list: storage, hot reload, admin API, request resolution."""

import json
import os
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from app.config import config
from app.model_registry import ModelRegistry, ModelRegistryError, get_model_registry
from app.modules.rag_pipeline import ChatRAGPipeline, answer_text_from_chunk
from app.modules.readiness import LLMNotConfigured
from main import app

SEED_IDS = ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"]
ENDPOINT_NULLS = {"base_url": None, "api_key_env": None, "thinking": None}
ZHIPU_BASE = "https://open.bigmodel.cn/api/paas/v4"


@pytest.fixture
def registry(tmp_path):
    return ModelRegistry(tmp_path / "models.json")


class TestRegistry:
    def test_seeds_on_first_use(self, registry):
        data = registry.snapshot()
        assert [m["id"] for m in data["models"]] == SEED_IDS
        assert data["default"] == "gpt-5.6-sol"
        assert registry.path.exists()

    def test_add_update_delete(self, registry):
        registry.add("test-model-x", "测试模型", "low")
        assert registry.get("test-model-x") == {
            "id": "test-model-x",
            "label": "测试模型",
            "reasoning_effort": "low",
            **ENDPOINT_NULLS,
        }
        registry.update("test-model-x", "改名", None)
        assert registry.get("test-model-x")["label"] == "改名"
        assert registry.get("test-model-x")["reasoning_effort"] is None
        registry.delete("test-model-x")
        assert registry.ids() == SEED_IDS

    def test_label_defaults_to_id(self, registry):
        registry.add("m-1")
        assert registry.get("m-1")["label"] == "m-1"

    @pytest.mark.parametrize(
        ("model_id", "effort"),
        [("", None), ("bad id", None), ("x" * 129, None), ("ok", "turbo")],
    )
    def test_rejects_invalid(self, registry, model_id, effort):
        with pytest.raises(ModelRegistryError):
            registry.add(model_id, None, effort)

    def test_rejects_duplicate(self, registry):
        with pytest.raises(ModelRegistryError):
            registry.add("gpt-5.6-sol")

    def test_cannot_delete_default_or_missing(self, registry):
        with pytest.raises(ModelRegistryError):
            registry.delete("gpt-5.6-sol")
        with pytest.raises(ModelRegistryError):
            registry.delete("nope")

    def test_set_default_and_reorder(self, registry):
        registry.set_default("gpt-5.6-luna")
        registry.reorder(["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"])
        data = registry.snapshot()
        assert data["default"] == "gpt-5.6-luna"
        assert [m["id"] for m in data["models"]] == ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"]
        with pytest.raises(ModelRegistryError):
            registry.reorder(["gpt-5.6-sol"])
        with pytest.raises(ModelRegistryError):
            registry.set_default("nope")

    def test_resolve(self, registry):
        assert registry.resolve("gpt-5.6-luna") == ("gpt-5.6-luna", True)
        assert registry.resolve(None) == ("gpt-5.6-sol", True)
        assert registry.resolve("evil-model") == ("gpt-5.6-sol", False)

    def test_hot_reloads_external_edit(self, registry):
        registry.snapshot()
        doc = json.loads(registry.path.read_text(encoding="utf-8"))
        doc["models"].append({"id": "hand-added", "label": "手动"})
        time.sleep(0.01)
        registry.path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        os.utime(registry.path, ns=(time.time_ns(), time.time_ns()))
        assert "hand-added" in registry.ids()

    def test_broken_file_keeps_last_good_list(self, registry):
        registry.snapshot()
        registry.path.write_text("{not json", encoding="utf-8")
        os.utime(registry.path, ns=(time.time_ns(), time.time_ns()))
        assert registry.ids() == SEED_IDS

    def test_public_shape_has_no_admin_fields(self, registry):
        registry.add("m-2", "M2", "high")
        pub = registry.public()
        assert pub["default"] == "gpt-5.6-sol"
        assert pub["models"][-1] == "m-2" and pub["labels"]["m-2"] == "M2"
        blob = json.dumps(pub)
        for hidden in ("reasoning_effort", "base_url", "api_key_env", "thinking", "api_key_present"):
            assert hidden not in blob

    def test_endpoint_fields_round_trip_and_legacy_load(self, registry):
        registry.add(
            "glm-5.3-flash",
            "智谱 Flash",
            None,
            base_url=ZHIPU_BASE + "/",
            api_key_env="ZHIPU_API_KEY",
            thinking="enabled",
        )
        entry = registry.get("glm-5.3-flash")
        assert entry["base_url"] == ZHIPU_BASE
        assert entry["api_key_env"] == "ZHIPU_API_KEY"
        assert entry["thinking"] == "enabled"
        persisted = json.loads(registry.path.read_text(encoding="utf-8"))
        saved = next(m for m in persisted["models"] if m["id"] == "glm-5.3-flash")
        assert saved["base_url"] == ZHIPU_BASE
        assert saved["api_key_env"] == "ZHIPU_API_KEY"
        assert saved["thinking"] == "enabled"

        registry.update("glm-5.3-flash", "改名", None)  # omitted endpoint fields stay
        assert registry.get("glm-5.3-flash")["base_url"] == ZHIPU_BASE
        registry.update("glm-5.3-flash", "改名", None, thinking=None)
        assert registry.get("glm-5.3-flash")["thinking"] is None
        assert registry.get("glm-5.3-flash")["api_key_env"] == "ZHIPU_API_KEY"

        other = ModelRegistry(registry.path)
        assert other.get("gpt-5.6-sol")["base_url"] is None
        assert other.get("glm-5.3-flash")["api_key_env"] == "ZHIPU_API_KEY"

    def test_legacy_file_without_new_keys_normalizes(self, tmp_path):
        path = tmp_path / "legacy.json"
        path.write_text(
            json.dumps(
                {
                    "default": "old-one",
                    "models": [{"id": "old-one", "label": "旧模型"}],
                }
            ),
            encoding="utf-8",
        )
        registry = ModelRegistry(path)
        entry = registry.get("old-one")
        assert entry == {
            "id": "old-one",
            "label": "旧模型",
            "reasoning_effort": None,
            **ENDPOINT_NULLS,
        }
        registry.set_default("old-one")  # any write persists the normalized keys
        saved = json.loads(path.read_text(encoding="utf-8"))["models"][0]
        assert saved["base_url"] is None and saved["api_key_env"] is None
        assert saved["thinking"] is None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"base_url": "http://open.bigmodel.cn/api/paas/v4"},
            {"base_url": "https://user:pass@open.bigmodel.cn/api/paas/v4"},
            {"base_url": "https://open.bigmodel.cn/api/paas/v4?x=1"},
            {"base_url": "https://open.bigmodel.cn/api/paas/v4#frag"},
            {"base_url": "https://" + "a" * 200 + ".example/v1"},
            {"api_key_env": "ADMIN_PASSWORD"},
            {"api_key_env": "openai_api_key"},
            {"api_key_env": "a" * 32},
            {"api_key_env": "sk-this-looks-like-a-key-value"},
            {"api_key_env": "0123456789abcdef0123456789abcdef"},
            {"thinking": "auto"},
            {"thinking": "true"},
        ],
    )
    def test_rejects_invalid_endpoint_fields(self, registry, kwargs):
        with pytest.raises(ModelRegistryError):
            registry.add("glm-bad", "bad", **kwargs)


def _admin_client(monkeypatch):
    client = TestClient(app, base_url="https://testserver")
    monkeypatch.setattr(config, "admin_password", "test-admin-pass")
    assert client.post("/api/admin/session", json={"password": "test-admin-pass"}).status_code == 200
    return client


class TestAdminModelApi:
    def test_requires_admin_session(self, monkeypatch):
        client = TestClient(app, base_url="https://testserver")
        monkeypatch.setattr(config, "admin_password", "test-admin-pass")
        assert client.get("/api/admin/models").status_code == 401
        assert client.post("/api/admin/models", json={"id": "x"}).status_code == 401
        assert client.delete("/api/admin/models/gpt-5.6-luna").status_code == 401
        assert client.post("/api/admin/models/default", json={"id": "gpt-5.6-luna"}).status_code == 401
        assert client.post("/api/admin/models/order", json={"ids": SEED_IDS}).status_code == 401
        assert get_model_registry().ids() == SEED_IDS

    def test_full_flow_and_public_list(self, monkeypatch):
        monkeypatch.setattr(config.llm, "model", "gpt-5.6-sol")
        client = _admin_client(monkeypatch)
        r = client.post(
            "/api/admin/models",
            json={"id": "test-model-x", "label": "测试", "reasoning_effort": "low"},
        )
        assert r.status_code == 200, r.text
        assert "low" in r.json()["reasoning_efforts"]
        public = client.get("/models").json()
        assert "test-model-x" in public["models"] and public["labels"]["test-model-x"] == "测试"

        assert client.post("/api/admin/models", json={"id": "test-model-x"}).status_code == 422
        assert client.post("/api/admin/models", json={"id": "bad id"}).status_code == 422

        r = client.patch("/api/admin/models/test-model-x", json={"label": "改名"})
        assert r.status_code == 200 and r.json()["models"][-1]["label"] == "改名"

        r = client.post("/api/admin/models/default", json={"id": "test-model-x"})
        assert r.json()["default"] == "test-model-x"
        assert config.llm.model == "test-model-x"  # LLM_MODEL kept in sync
        assert client.delete("/api/admin/models/test-model-x").status_code == 422  # default

        client.post("/api/admin/models/default", json={"id": "gpt-5.6-sol"})
        order = ["gpt-5.6-sol", "test-model-x", "gpt-5.6-luna", "gpt-5.6-terra"]
        assert client.post("/api/admin/models/order", json={"ids": order}).json()["models"][1]["id"] == "test-model-x"
        r = client.delete("/api/admin/models/test-model-x")
        assert r.status_code == 200
        assert client.get("/models").json()["models"] == SEED_IDS

    def test_add_update_endpoint_fields_and_key_presence(self, monkeypatch):
        monkeypatch.setenv("ZHIPU_API_KEY", "test-zhipu-key")
        client = _admin_client(monkeypatch)
        r = client.post(
            "/api/admin/models",
            json={
                "id": "glm-5.3-flash",
                "label": "智谱",
                "base_url": ZHIPU_BASE + "/",
                "api_key_env": "ZHIPU_API_KEY",
                "thinking": "enabled",
            },
        )
        assert r.status_code == 200, r.text
        entry = r.json()["models"][-1]
        assert entry["base_url"] == ZHIPU_BASE
        assert entry["api_key_env"] == "ZHIPU_API_KEY"
        assert entry["thinking"] == "enabled"
        assert entry["api_key_present"] is True
        assert "test-zhipu-key" not in r.text

        public = client.get("/models").json()
        blob = json.dumps(public)
        assert "glm-5.3-flash" in public["models"]
        for hidden in ("base_url", "api_key_env", "thinking", "api_key_present"):
            assert hidden not in blob

        monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
        listed = client.get("/api/admin/models").json()["models"][-1]
        assert listed["api_key_present"] is False
        assert "test-zhipu-key" not in json.dumps(listed)

        r = client.patch(
            "/api/admin/models/glm-5.3-flash",
            json={"label": "智谱 Flash", "thinking": "disabled"},
        )
        assert r.status_code == 200
        updated = r.json()["models"][-1]
        assert updated["label"] == "智谱 Flash"
        assert updated["thinking"] == "disabled"
        assert updated["base_url"] == ZHIPU_BASE
        assert updated["api_key_env"] == "ZHIPU_API_KEY"

        r = client.patch(
            "/api/admin/models/glm-5.3-flash",
            json={"label": "智谱 Flash", "base_url": "http://example.com/v1"},
        )
        assert r.status_code == 422

        r = client.post(
            "/api/admin/models",
            json={"id": "evil", "api_key_env": "ADMIN_PASSWORD"},
        )
        assert r.status_code == 422


class TestChatModelResolution:
    def _capture(self, monkeypatch):
        from app.api import routes

        seen = {}

        def fake_stream(query, user_metadata=None, model=None, history=None):
            seen["model"] = model
            yield {"type": "done", "sources": []}

        monkeypatch.setattr(routes, "is_llm_configured", lambda: True)
        monkeypatch.setattr(routes, "get_chat_stream", fake_stream)
        return TestClient(app), seen

    def test_listed_model_is_used(self, monkeypatch):
        client, seen = self._capture(monkeypatch)
        assert client.post("/chat/stream", json={"query": "你好", "model": "gpt-5.6-luna"}).status_code == 200
        assert seen["model"] == "gpt-5.6-luna"

    @pytest.mark.parametrize("model", [None, "", "not-in-list", "gpt-4o"])
    def test_unlisted_model_falls_back_to_default(self, monkeypatch, model):
        client, seen = self._capture(monkeypatch)
        assert client.post("/chat/stream", json={"query": "你好", "model": model}).status_code == 200
        assert seen["model"] == "gpt-5.6-sol"

    def test_removed_model_is_no_longer_accepted(self, monkeypatch):
        client, seen = self._capture(monkeypatch)
        get_model_registry().set_default("gpt-5.6-luna")
        get_model_registry().delete("gpt-5.6-terra")
        client.post("/chat/stream", json={"query": "你好", "model": "gpt-5.6-terra"})
        assert seen["model"] == "gpt-5.6-luna"


def test_per_model_reasoning_effort(monkeypatch):
    from app.modules.model_provider import ModelProvider
    from app.utils.logging_config import rag_logger

    monkeypatch.setattr(config.llm, "provider", "openai")
    monkeypatch.setattr(config.llm, "reasoning_effort", "none")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mp = ModelProvider(config, rag_logger)
    assert mp.get_language_model("gpt-5.6-sol").reasoning_effort == "none"
    assert mp.get_language_model("gpt-5.6-sol", reasoning_effort="high").reasoning_effort == "high"


def test_per_model_endpoint_builds_chat_openai(monkeypatch):
    from app.modules import model_provider as mp_mod
    from app.modules.model_provider import ModelProvider
    from app.utils.logging_config import rag_logger

    monkeypatch.setattr(config.llm, "provider", "openai")
    monkeypatch.setattr(config.llm, "reasoning_effort", "none")
    monkeypatch.setattr(config.llm, "api", "responses")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-global-test")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-zhipu-key")
    mp = ModelProvider(config, rag_logger)
    llm = mp.get_language_model(
        "glm-5.3-flash",
        reasoning_effort=None,
        base_url=ZHIPU_BASE,
        api_key_env="ZHIPU_API_KEY",
        thinking="enabled",
    )
    assert llm.use_responses_api is False
    assert str(llm.openai_api_base).rstrip("/") == ZHIPU_BASE
    assert getattr(llm, "reasoning_effort", None) in (None, "")
    assert dict(llm.extra_body or {}) == {"thinking": {"type": "enabled"}}
    secret = llm.openai_api_key
    value = secret.get_secret_value() if hasattr(secret, "get_secret_value") else secret
    assert value == "test-zhipu-key"
    assert llm.http_client is mp_mod.shared_llm_http_client()

    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    with pytest.raises(LLMNotConfigured, match="ZHIPU_API_KEY"):
        mp.get_language_model(
            "glm-5.3-flash",
            base_url=ZHIPU_BASE,
            api_key_env="ZHIPU_API_KEY",
        )


def test_per_model_endpoint_from_registry_no_global_effort(monkeypatch):
    from app.modules.model_provider import ModelProvider
    from app.utils.logging_config import rag_logger

    get_model_registry().add(
        "glm-5.3-flash",
        "智谱",
        None,
        base_url=ZHIPU_BASE,
        api_key_env="ZHIPU_API_KEY",
        thinking="disabled",
    )
    monkeypatch.setattr(config.llm, "provider", "openai")
    monkeypatch.setattr(config.llm, "reasoning_effort", "none")
    monkeypatch.setattr(config.llm, "api", "responses")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-zhipu-key")
    llm = ModelProvider(config, rag_logger).get_language_model("glm-5.3-flash")
    assert llm.use_responses_api is False
    assert getattr(llm, "reasoning_effort", None) in (None, "")
    assert dict(llm.extra_body or {}) == {"thinking": {"type": "disabled"}}


def test_answer_text_from_chunk_keeps_only_content():
    reasoning = "SECRET_REASONING_SHOULD_NOT_LEAK"
    chunk = AIMessageChunk(
        content=[
            {"type": "reasoning", "reasoning": reasoning},
            {"type": "thinking", "thinking": reasoning},
            {"type": "text", "text": "可见"},
            {"type": "output_text", "text": "答案"},
        ],
        additional_kwargs={"reasoning_content": reasoning},
    )
    assert answer_text_from_chunk(chunk) == "可见答案"
    assert reasoning not in answer_text_from_chunk(chunk)
    assert answer_text_from_chunk({"content": reasoning, "answer": "ok"}) == "ok"
    assert answer_text_from_chunk("plain") == "plain"
    assert answer_text_from_chunk(None) == ""


def _sse_chunk(delta: dict, finish: str | None = None) -> str:
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "glm-5.3-flash",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def test_stream_drops_reasoning_content_from_openai_sse(monkeypatch):
    """glm-5.3-flash streams delta.reasoning_content before delta.content."""
    from app.modules import model_provider as mp_mod
    from app.modules import rag_pipeline
    from app.modules.model_provider import ModelProvider
    from app.utils.logging_config import rag_logger

    reasoning = "SECRET_REASONING_SHOULD_NOT_LEAK"
    answer = "可见答案"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.rstrip("/").endswith("/chat/completions"):
            body = (
                _sse_chunk({"role": "assistant", "reasoning_content": reasoning, "content": None})
                + _sse_chunk({"reasoning_content": " more thinking"})
                + _sse_chunk({"content": "可见"})
                + _sse_chunk({"content": "答案"})
                + _sse_chunk({}, finish="stop")
                + "data: [DONE]\n\n"
            )
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=body.encode("utf-8"),
            )
        return httpx.Response(404, text="not found")

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(mp_mod, "_LLM_HTTP_CLIENT", mock_client)
    monkeypatch.setattr(config.llm, "provider", "openai")
    monkeypatch.setattr(config.llm, "reasoning_effort", "none")
    monkeypatch.setattr(config.llm, "api", "responses")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-zhipu-key")
    try:
        llm = ModelProvider(config, rag_logger).get_language_model(
            "glm-5.3-flash",
            base_url=ZHIPU_BASE,
            api_key_env="ZHIPU_API_KEY",
            thinking="enabled",
        )
        pieces = [answer_text_from_chunk(chunk) for chunk in llm.stream("你好")]
        combined = "".join(pieces)
        assert reasoning not in combined
        assert "SECRET" not in combined
        assert answer in combined

        class Chain:
            def stream(self, payload):
                yield from llm.stream("你好")

        fake = SimpleNamespace(
            config=config,
            base_retriever=SimpleNamespace(invoke=lambda q: []),
            query_validator=SimpleNamespace(
                validate_query_input=lambda q: q, validate_response_output=lambda a: a
            ),
            _initialize_qa_chain=lambda model: Chain(),
            _history=lambda h: [],
            _retrieve=lambda q: [],
            _fallback_text=lambda: "fallback",
        )
        monkeypatch.setattr(rag_pipeline, "is_llm_configured", lambda: True)
        events = list(ChatRAGPipeline.stream_completion(fake, "你好"))
        tokens = "".join(e.get("content", "") for e in events if e.get("type") == "token")
        assert reasoning not in tokens
        assert answer in tokens
        assert events[-1]["type"] == "done"
    finally:
        mock_client.close()
        mp_mod._LLM_HTTP_CLIENT = None


def test_models_file_is_not_publicly_served():
    client = TestClient(app)
    get_model_registry().snapshot()
    assert client.get("/data/models.json").status_code == 404


def test_admin_snapshot_api_key_present_from_dotenv(monkeypatch, tmp_path):
    from app.utils import env as env_utils

    env_file = tmp_path / ".env"
    env_file.write_text('ZHIPU_API_KEY="test-zhipu-from-dotenv"\n', encoding="utf-8")
    monkeypatch.setattr(env_utils, "_DOTENV_PATH", env_file)
    env_utils._dotenv_cache = None
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    client = _admin_client(monkeypatch)
    r = client.post(
        "/api/admin/models",
        json={"id": "glm-dotenv", "api_key_env": "ZHIPU_API_KEY", "base_url": ZHIPU_BASE},
    )
    assert r.status_code == 200, r.text
    entry = r.json()["models"][-1]
    assert entry["api_key_present"] is True
    assert "test-zhipu-from-dotenv" not in r.text
