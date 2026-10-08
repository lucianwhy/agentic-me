"""Tool write-ups (data/tools/*.md): knowledge-base chunks, chunk → tool mapping, no public exposure."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.api.routes import _serialize_sources
from app.config import config
from app.modules import tools as tools_mod
from app.modules.resume_links import resume_entry_ids
from app.modules.tools import load_tools, parse_tool_markdown, tool_chunks, tool_ids
from main import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)

SAMPLE = """---
id: demo-tool
title: 演示工具
aliases: [Demo MCP, demo_search]
---
# 演示工具

开头一段介绍。

## 架构

检索层和上下文层。

## 经验

分页由服务端推进。
"""


@pytest.fixture
def demo_tools_dir(tmp_path, monkeypatch):
    (tmp_path / "demo-tool.md").write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(config.data, "tools_dir", str(tmp_path))
    return tmp_path


def test_parse_front_matter_and_body():
    tool = parse_tool_markdown(SAMPLE, "fallback")
    assert tool.id == "demo-tool"
    assert tool.title == "演示工具"
    assert tool.aliases == ("Demo MCP", "demo_search")
    assert not tool.body.startswith("---") and "aliases" not in tool.body


def test_parse_without_front_matter_falls_back():
    tool = parse_tool_markdown("# 标题工具\n\n## 一\n内容", "file-stem")
    assert (tool.id, tool.title, tool.aliases) == ("file-stem", "标题工具", ())


def test_chunks_are_per_section_and_prefixed():
    chunks = tool_chunks(parse_tool_markdown(SAMPLE, "x"))
    assert [c.metadata["section"] for c in chunks] == ["简介", "架构", "经验"]
    for c in chunks:
        assert c.page_content.startswith(f"【工具：演示工具 · {c.metadata['section']}】")
        assert c.metadata["source"] == "tool" and c.metadata["tool_id"] == "demo-tool"
        assert c.metadata["title"] == "演示工具"


def test_long_section_is_split():
    body = "---\nid: long\ntitle: 长工具\n---\n## 很长\n" + "。".join(["这是一句比较长的说明文字"] * 120)
    chunks = tool_chunks(parse_tool_markdown(body, "long"), chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 3
    assert all(len(c.page_content) <= 300 + 40 for c in chunks)


def test_real_tool_doc_yields_several_chunks():
    ids = [t.id for t in load_tools()]
    assert "rag-knowledge-mcp" in ids
    chunks = [c for c in tools_mod.load_tool_chunks() if c.metadata["tool_id"] == "rag-knowledge-mcp"]
    assert len(chunks) >= 6
    text = "\n".join(c.page_content for c in chunks)
    for needle in ("search_knowledge", "get_chunk_context", "next_offset", "document_id", "Cloudflare"):
        assert needle in text
    assert "风叔" not in chunks[0].page_content.split("\n", 1)[0]  # name is not the blogger's
    assert all(c.page_content.startswith("【工具：RAG 知识库 MCP · ") for c in chunks)


def test_get_chunk_context_is_documented_as_designing():
    """The KB must never let the chat claim get_chunk_context is implemented."""
    text = "\n".join(c.page_content for c in tools_mod.load_tool_chunks() if c.metadata["tool_id"] == "rag-knowledge-mcp")
    status = next(c.page_content for c in tools_mod.load_tool_chunks() if c.metadata["section"].startswith("当前实现状态"))
    assert "get_chunk_context" in status and "设计中" in status and "尚未实现" in status
    for line in text.splitlines():
        if "get_chunk_context" in line and "已实现" in line:
            assert "设计中" in line or "尚未实现" in line, line


def test_frontend_marks_chunk_context_as_designing():
    ts = (ROOT / "frontend/src/data/tools.ts").read_text(encoding="utf-8")
    assert ts.count("status: 'designing'") >= 4  # capability 03, P2, P3, P4 role, resume bullet 3
    sources = (ROOT / "frontend/src/data/diagram-sources.ts").read_text(encoding="utf-8")
    assert re.search(r"get_chunk_context[^\n]*设计中", sources)


def test_resume_highlights_in_frontend_and_kb():
    """tools.ts resumeBullets for rag-knowledge-mcp includes a designing entry; the KB section says 设计中."""
    ts = (ROOT / "frontend/src/data/tools.ts").read_text(encoding="utf-8")
    assert "id: 'rag-knowledge-mcp'" in ts
    block = re.search(r"resumeBullets:\s*\[(.*?)\]\s*,\s*problems:", ts, re.DOTALL)
    assert block, "rag-knowledge-mcp must declare resumeBullets"
    assert "status: 'designing'" in block.group(1)

    md = (ROOT / "data/tools/rag-knowledge-mcp.md").read_text(encoding="utf-8")
    assert "## 简历上怎么写（简历亮点）" in md
    section = md.split("## 简历上怎么写（简历亮点）", 1)[1].split("\n## ", 1)[0]
    assert "设计中" in section
    assert "get_chunk_context" in section
    chunks = [
        c
        for c in tools_mod.load_tool_chunks()
        if c.metadata["tool_id"] == "rag-knowledge-mcp" and str(c.metadata["section"]).startswith("简历上怎么写")
    ]
    assert len(chunks) == 1


def test_tool_ids_from_metadata_and_mentions(demo_tools_dir):
    assert tool_ids("任意内容", {"source": "tool", "tool_id": "demo-tool"}) == ["demo-tool"]
    assert tool_ids("我做过一个 Demo MCP 工具", {"source": "about_me"}) == ["demo-tool"]
    assert tool_ids("调用 demo_search 检索", {"source": "cv"}) == ["demo-tool"]
    assert tool_ids("讯飞聆智实习经历", {"source": "cv"}) == []
    assert tool_ids("", None) == []


def test_tool_ids_never_raise(monkeypatch):
    def boom():
        raise RuntimeError("broken")

    monkeypatch.setattr(tools_mod, "load_tools", boom)
    assert tool_ids("x", {"source": "about_me"}) == []


def test_tool_chunks_do_not_map_to_resume_entries():
    # Even if a tool chunk names a resume entry, it must highlight the tool row, not a resume card.
    title = config.resume.projects[0].title if config.resume.projects else "某项目"
    assert resume_entry_ids(f"【工具：x】和{title}有关", {"source": "tool", "tool_id": "x"}) == []


def test_serialized_sources_carry_tool_ids():
    out = _serialize_sources(
        [
            Document(page_content="【工具：RAG 知识库 MCP · 经验】分页", metadata={"source": "tool", "tool_id": "rag-knowledge-mcp", "title": "RAG 知识库 MCP"}),
            Document(page_content="完全无关的一段内容", metadata={"source": "about_me"}),
        ]
    )
    assert out[0]["tool_ids"] == ["rag-knowledge-mcp"] and out[0]["resume_entry_ids"] == []
    assert out[1]["tool_ids"] == []


def test_setup_vectorstore_indexes_tool_chunks(demo_tools_dir, monkeypatch, tmp_path):
    from app.modules import vectorstore_provider as vp

    captured: dict = {}

    def fake_from_documents(docs, embedding, **kwargs):
        captured["docs"] = docs
        return "db"

    class FakeProvider:
        def get_embedding_model(self):
            return object()

    monkeypatch.setattr(vp.Chroma, "from_documents", staticmethod(fake_from_documents))
    monkeypatch.setattr(config.data, "vector_db_path", str(tmp_path / "vdb"))
    import logging

    manager = vp.VectorStoreManager(config, FakeProvider(), logging.getLogger("test"))
    assert manager.setup_vectorstore() == "db"
    tool_docs = [d for d in captured["docs"] if d.metadata.get("source") == "tool"]
    assert [d.metadata["section"] for d in tool_docs] == ["简介", "架构", "经验"]


class TestToolDataNotServed:
    @pytest.mark.parametrize(
        "path",
        [
            "/data/tools/rag-knowledge-mcp.md",
            "/data/tools/",
            "/data/tools",
            "/data/tools/../tools/rag-knowledge-mcp.md",
            "/data/%2e%2e/data/tools/rag-knowledge-mcp.md",
            "/data/tools%2Frag-knowledge-mcp.md",
            "/static/../data/tools/rag-knowledge-mcp.md",
            "/assets/../data/tools/rag-knowledge-mcp.md",
        ],
    )
    def test_get_and_head_404(self, path):
        assert client.get(path).status_code == 404
        assert client.head(path).status_code == 404

    def test_body_never_leaks(self):
        secret_line = "mcp______search"
        for path in ("/data/tools/rag-knowledge-mcp.md", "/data/rag-knowledge-mcp.md"):
            assert secret_line not in client.get(path).text

    def test_cv_still_served(self):
        cv = ROOT / config.data.cv_path
        if not cv.is_file():
            pytest.skip("CV PDF not present")
        assert client.get(config.cv_public_url()).status_code == 200


def test_frontend_tool_ids_match_knowledge_files():
    """frontend/src/data/tools.ts ids == data/tools/*.md ids; each tool's diagram is prerendered."""
    ts = (ROOT / "frontend/src/data/tools.ts").read_text(encoding="utf-8")
    front_ids = set(re.findall(r"^    id: '([^']+)'", ts, re.MULTILINE))
    back_ids = {t.id for t in load_tools()}
    assert front_ids and front_ids == back_ids
    diagrams = (ROOT / "frontend/src/generated/diagrams.ts").read_text(encoding="utf-8")
    for diagram_id in re.findall(r"diagram: \{\s*id: '([^']+)'", ts):
        assert f'"{diagram_id}": {{' in diagrams
