from fastapi.testclient import TestClient

from app.modules.readiness import chinese_not_ready_error, is_llm_configured
from main import app

client = TestClient(app)


def test_health_includes_readiness_flags():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "llm_configured" in data
    assert "vectorstore_ready" in data
    assert data["auth_enabled"] is False


def test_homepage_chinese_without_key():
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "智能简历" in body or "对话" in body
    assert "login-modal" in body


def test_chat_returns_chinese_error_when_unconfigured():
    if is_llm_configured():
        return
    response = client.post("/chat", json={"query": "介绍一下项目经验"})
    assert response.status_code == 503
    data = response.json()
    assert data.get("error") is True
    assert data.get("code") == "llm_not_configured"
    assert "API" in data.get("message", "")


def test_summary_returns_chinese_error_when_unconfigured():
    if is_llm_configured():
        return
    response = client.post("/summary")
    assert response.status_code == 503
    assert response.json().get("error") is True


def test_chinese_not_ready_payload_shape():
    payload = chinese_not_ready_error()
    assert payload["error"] is True
    assert payload["code"] in {
        "llm_not_configured",
        "vectorstore_not_ready",
        "not_ready",
    }
    assert isinstance(payload["message"], str)
