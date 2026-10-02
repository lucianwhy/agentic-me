"""Admin-managed chat model list: storage, hot reload, admin API, request resolution."""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.model_registry import ModelRegistry, ModelRegistryError, get_model_registry
from main import app

SEED_IDS = ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"]


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
            "id": "test-model-x", "label": "测试模型", "reasoning_effort": "low",
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
        assert "reasoning_effort" not in json.dumps(pub)


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


def test_models_file_is_not_publicly_served():
    client = TestClient(app)
    get_model_registry().snapshot()
    assert client.get("/data/models.json").status_code == 404
