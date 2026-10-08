"""Tool write-ups (data/tools/*.md) as a RAG knowledge source + chunk → tool mapping.

Each file starts with a small YAML front matter block::

    ---
    id: fengshu-mcp            # stable id, also used by frontend/src/data/tools.ts
    title: 风叔知识库 MCP
    aliases: [风叔 MCP, search_fengshu_knowledge]
    ---

The body is split per ``##`` section (long sections are split again), and every chunk is
prefixed with ``【工具：<title> · <section>】`` so a chunk retrieved on its own still says
which tool it is about. Chunks carry ``metadata = {source: "tool", tool_id, title, section}``.

These files are private knowledge-base input: main.py only ever serves the CV PDF under
/data, never data/tools/.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from langchain_core.documents import Document

from app.config import config
from app.utils.logging_config import rag_logger

TOOL_SOURCE = "tool"
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ToolDoc:
    id: str
    title: str
    body: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


def tools_dir() -> Path:
    return Path(getattr(config.data, "tools_dir", "") or "data/tools")


def parse_tool_markdown(text: str, fallback_id: str) -> ToolDoc:
    """Split front matter from the body. Missing fields fall back to the file name / H1."""
    meta: dict[str, Any] = {}
    body = text
    m = FRONT_MATTER.match(text)
    if m:
        loaded = yaml.safe_load(m.group(1)) or {}
        meta = loaded if isinstance(loaded, dict) else {}
        body = text[m.end() :]
    title = str(meta.get("title") or "").strip()
    if not title:
        h1 = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = h1.group(1).strip() if h1 else fallback_id
    aliases = tuple(str(a).strip() for a in (meta.get("aliases") or []) if str(a).strip())
    return ToolDoc(id=str(meta.get("id") or fallback_id).strip(), title=title, body=body.strip(), aliases=aliases)


def _dir_key(path: Path) -> tuple:
    try:
        return tuple(sorted((p.name, p.stat().st_mtime) for p in path.glob("*.md")))
    except OSError:
        return ()


@lru_cache(maxsize=4)
def _load_tools(path: str, _key: tuple) -> tuple[ToolDoc, ...]:
    docs: list[ToolDoc] = []
    for file in sorted(Path(path).glob("*.md")):
        try:
            docs.append(parse_tool_markdown(file.read_text(encoding="utf-8"), file.stem))
        except Exception as exc:  # one broken file must not break the rest
            rag_logger.warning(f"tools: skipped {file.name} ({type(exc).__name__}: {exc})")
    return tuple(docs)


def load_tools() -> tuple[ToolDoc, ...]:
    """All tool write-ups (cached; reloaded when a file changes)."""
    path = tools_dir()
    if not path.is_dir():
        return ()
    return _load_tools(str(path), _dir_key(path))


def _sections(body: str) -> list[tuple[str, str]]:
    """[(section title, text)] by ``##`` heading; text before the first heading is 'intro'."""
    marks = list(SECTION.finditer(body))
    out: list[tuple[str, str]] = []
    head = body[: marks[0].start()] if marks else body
    head = re.sub(r"^#\s+.*$", "", head, flags=re.MULTILINE).strip()
    if head:
        out.append(("简介", head))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        text = body[m.end() : end].strip()
        if text:
            out.append((m.group(1).strip(), text))
    return out


def tool_chunks(tool: ToolDoc, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[Document]:
    """One chunk per section (long sections re-split), each prefixed with the tool name."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[Document] = []
    for section, text in _sections(tool.body):
        for part in splitter.split_text(text) if len(text) > chunk_size else [text]:
            chunks.append(
                Document(
                    page_content=f"【工具：{tool.title} · {section}】\n{part}",
                    metadata={"source": TOOL_SOURCE, "tool_id": tool.id, "title": tool.title, "section": section},
                )
            )
    return chunks


def load_tool_chunks(chunk_size: int = 1000, chunk_overlap: int = 200) -> list[Document]:
    out: list[Document] = []
    for tool in load_tools():
        out.extend(tool_chunks(tool, chunk_size, chunk_overlap))
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def tool_ids(content: str, metadata: dict[str, Any] | None = None) -> list[str]:
    """Left-sidebar tool rows a retrieved chunk is about ([] if none, never raises).

    A chunk from data/tools/<x>.md maps to its own tool; any other chunk (CV, about_me)
    maps to tools whose title / aliases it mentions.
    """
    try:
        meta = metadata or {}
        own = str(meta.get("tool_id") or "") if meta.get("source") == TOOL_SOURCE else ""
        ids = [own] if own else []
        c = _norm(content)
        for tool in load_tools():
            if tool.id in ids:
                continue
            keys = [k for k in map(_norm, (tool.title, *tool.aliases)) if len(k) >= 2]
            if any(k in c for k in keys):
                ids.append(tool.id)
        return ids
    except Exception as exc:
        rag_logger.info(f"tools: mapping failed ({type(exc).__name__}: {exc})")
        return []
