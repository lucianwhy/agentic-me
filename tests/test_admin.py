import os

from fastapi.testclient import TestClient

from app import admin
from app.config import config
from main import app


def _restore_environment(values: dict[str, str | None]) -> None:
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_admin_page_is_available_but_settings_require_password():
    client = TestClient(app, base_url="https://testserver")
    assert client.get("/admin").status_code == 200
    assert client.get("/api/admin/settings").status_code == 401
    assert client.post("/api/admin/session", json={"password": "wrong"}).status_code == 401


def test_admin_can_save_runtime_model_settings_without_exposing_api_key(
    tmp_path, monkeypatch
):
    client = TestClient(app, base_url="https://testserver")
    monkeypatch.setattr(admin, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "admin_password", "admin123")
    original_env = {
        key: os.environ.get(key)
        for key in (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "LLM_PROVIDER",
            "LLM_MODEL",
            "REASONING_EFFORT",
        )
    }
    original_config = {
        "api_key": config.openai_api_key,
        "base_url": config.openai_base_url,
        "llm_base_url": config.llm_base_url,
        "provider": config.llm.provider,
        "model": config.llm.model,
        "effort": config.llm.reasoning_effort,
        "llm_url": config.llm.base_url,
    }
    try:
        assert client.post("/api/admin/session", json={"password": "admin123"}).status_code == 200
        response = client.post(
            "/api/admin/settings",
            json={
                "api_key": "test-secret-key",
                "base_url": "https://example.test/v1",
                "model": "gpt-5.6-terra",
                "reasoning_effort": "high",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["api_key_configured"] is True
        assert "test-secret-key" not in response.text
        assert data["model"] == "gpt-5.6-terra"
        assert data["reasoning_effort"] == "high"
        saved = (tmp_path / ".env").read_text(encoding="utf-8")
        assert 'OPENAI_API_KEY="test-secret-key"' in saved
        assert 'LLM_MODEL="gpt-5.6-terra"' in saved
    finally:
        config.openai_api_key = original_config["api_key"]
        config.openai_base_url = original_config["base_url"]
        config.llm_base_url = original_config["llm_base_url"]
        config.llm.provider = original_config["provider"]
        config.llm.model = original_config["model"]
        config.llm.reasoning_effort = original_config["effort"]
        config.llm.base_url = original_config["llm_url"]
        _restore_environment(original_env)
