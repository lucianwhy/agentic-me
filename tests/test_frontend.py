"""React frontend serving + public profile endpoint."""

import json

import pytest

from fastapi.testclient import TestClient

import main
from app.config import config
from main import app

client = TestClient(app)


class TestPublicProfile:
    def test_profile_fields(self):
        response = client.get("/api/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == config.candidate.name
        assert data["cv_url"] == config.cv_public_url()
        assert data["avatar_url"].startswith("/static/")
        assert len(data["suggested_questions"]) == 5
        assert all(q["label"] and q["question"] for q in data["suggested_questions"])
        types = {c["type"] for c in data["contacts"]}
        if config.candidate.email:
            assert "email" in types

    def test_profile_exposes_no_secrets(self):
        blob = json.dumps(client.get("/api/profile").json()).lower()
        for needle in ("api_key", "password", "invite", "token", "secret", "base_url"):
            assert needle not in blob
        admin_pw = config.resolved_admin_password()
        if admin_pw:
            assert admin_pw.lower() not in blob


class TestIndexServing:
    def test_index_never_500s(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_falls_back_to_jinja_when_build_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path / "missing-dist")
        response = client.get("/")
        assert response.status_code == 200
        assert 'id="chat-form"' in response.text

    def test_serves_react_build_when_present(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
        monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path)
        response = client.get("/")
        assert response.status_code == 200
        assert '<div id="root"></div>' in response.text
        assert response.headers.get("cache-control") == "no-cache"

    def test_admin_still_jinja(self):
        response = client.get("/admin")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestProfileSkills:
    def test_skills_from_config(self, monkeypatch):
        monkeypatch.setattr(config.candidate, "skills", ["RAG", " ", "FastAPI"])
        data = client.get("/api/profile").json()
        assert data["skills"] == ["RAG", "FastAPI"]

    def test_skills_optional(self, monkeypatch):
        monkeypatch.setattr(config.candidate, "skills", [])
        assert client.get("/api/profile").json()["skills"] == []


class TestStreamStatusEvents:
    def test_status_and_sources_are_forwarded(self, monkeypatch):
        from app.api import routes

        def fake_stream(query, user_metadata=None, model=None):
            yield {"type": "status", "stage": "retrieving"}
            yield {"type": "status", "stage": "generating", "source_count": 1}
            yield {"type": "token", "content": "你好"}
            yield {"type": "done", "sources": [{"content": "片段", "metadata": {"source": "cv"}}]}

        monkeypatch.setattr(routes, "is_llm_configured", lambda: True)
        monkeypatch.setattr(routes, "get_chat_stream", fake_stream)
        response = client.post("/chat/stream", json={"query": "介绍一下"})
        assert response.status_code == 200
        events = [
            json.loads(line[5:])
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        assert [e["type"] for e in events] == ["status", "status", "token", "done"]
        assert events[1]["stage"] == "generating"
        assert events[-1]["sources"][0]["metadata"]["source"] == "cv"


class TestDataExposure:
    """Only the CV PDF is public under /data; logs, the vector store and notes are not."""

    def test_cv_pdf_downloadable(self):
        url = config.cv_public_url()
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
        assert client.head(url).status_code == 200

    def test_cv_pdf_percent_encoded_url(self):
        from urllib.parse import quote

        response = client.get(quote(config.cv_public_url()))
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "path",
        [
            "/data/analytics.log",
            "/data/vector_db/chroma.sqlite3",
            "/data/about_me.md",
            "/data/sample_job_description.txt",
            "/data/",
            "/data/vector_db/",
            "/data/../main.py",
            "/data/%2e%2e/main.py",
            "/data/does-not-exist.pdf",
        ],
    )
    def test_everything_else_404(self, path):
        assert client.get(path).status_code == 404
