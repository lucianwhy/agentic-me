"""Map retrieved chunks to the structured resume entries shown in the sidebar.

Each source in the /chat done event gets ``resume_entry_ids`` (e.g. ["projects-0"]) so the
frontend can highlight the matching card. The mapping uses the FULL chunk text (sources are
truncated to 300 chars on the wire) and two signals:

1. Position: the chunk is located inside its full source document (CV pages joined, or
   about_me.md). Each entry owns the span from its header (first mention of its title /
   organization) to the next entry header or section heading, so a chunk that continues an
   entry without repeating its title (e.g. CV page 2) still maps to it.
2. Mentions: entries whose title / organization appear in the chunk (e.g. an FAQ line).

Ids are ordered by positional overlap (largest first), then mention-only entries.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from app.config import ResumeEntry, config
from app.utils.logging_config import rag_logger

ENTRY_KINDS = ("internships", "projects", "education")

# Section headings that end the previous entry's span (normalized: no whitespace, lowercase).
SECTION_STOPS = (
    "教育经历", "专业技能", "实习经历", "项目经历", "个人评价",
    "##简介", "##教育", "##实习经历", "##项目", "##技能", "##faq",
)

# Minimum overlap (normalized chars) for a positional match; chunk overlaps are ~200 chars
# of the previous chunk, so a tiny tail of an entry should not count.
MIN_OVERLAP = 40


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def entry_id(kind: str, index: int) -> str:
    return f"{kind}-{index}"


def entry_keys(entry: ResumeEntry) -> list[str]:
    """Names an entry is recognisable by: title, its short form, organization (+ short form)."""
    raw = [
        entry.title,
        re.split(r"\s+[-·]\s+", entry.title)[0],
        entry.organization,
        re.sub(r"(科技)?有限公司$", "", entry.organization),
    ]
    keys: list[str] = []
    for k in map(_norm, raw):
        if len(k) >= 2 and k not in keys:
            keys.append(k)
    return keys


def _entries(resume: Any) -> list[tuple[str, list[str]]]:
    return [
        (entry_id(kind, i), entry_keys(e))
        for kind in ENTRY_KINDS
        for i, e in enumerate(getattr(resume, kind, []) or [])
    ]


def entry_spans(doc_norm: str, entries: list[tuple[str, list[str]]]) -> list[tuple[str, int, int]]:
    """(entry id, start, end) spans in a normalized document."""
    marks: list[tuple[int, str | None]] = []
    for eid, keys in entries:
        positions = [doc_norm.find(k) for k in keys]
        positions = [p for p in positions if p >= 0]
        if positions:
            marks.append((min(positions), eid))
    for stop in SECTION_STOPS:
        marks.extend((m.start(), None) for m in re.finditer(re.escape(stop), doc_norm))
    marks.sort(key=lambda m: m[0])
    spans = []
    for i, (pos, eid) in enumerate(marks):
        if eid is None:
            continue
        end = next((p for p, _ in marks[i + 1 :] if p > pos), len(doc_norm))
        spans.append((eid, pos, end))
    return spans


def map_chunk(
    chunk: str,
    documents: Iterable[str],
    entries: list[tuple[str, list[str]]],
) -> list[str]:
    """Entry ids for one chunk given candidate full documents (normalized or not)."""
    c = _norm(chunk)
    if not c:
        return []
    overlaps: dict[str, int] = {}
    for doc in documents:
        d = _norm(doc)
        start = d.find(c)
        if start < 0 and len(c) > 80:  # tolerate small differences at the chunk's tail
            start = d.find(c[:80])
        if start < 0:
            continue
        end = start + len(c)
        threshold = min(MIN_OVERLAP, max(1, len(c) // 2))  # short chunks: half of it is enough
        for eid, s, e in entry_spans(d, entries):
            ov = min(end, e) - max(start, s)
            if ov >= threshold:
                overlaps[eid] = max(overlaps.get(eid, 0), ov)
        break
    ids = sorted(overlaps, key=lambda k: -overlaps[k])
    for eid, keys in entries:
        if eid not in ids and any(k in c for k in keys):
            ids.append(eid)
    return ids


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


@lru_cache(maxsize=4)
def _load_cv(path: str, _mtime_key: float) -> str:
    from langchain_community.document_loaders import PyPDFLoader

    return "\n".join(d.page_content for d in PyPDFLoader(path).load() if d.page_content)


@lru_cache(maxsize=4)
def _load_text(path: str, _mtime_key: float) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def source_documents() -> dict[str, str]:
    """Full text of each ingested source, keyed like chunk metadata['source']."""
    docs: dict[str, str] = {}
    try:
        docs["cv"] = _load_cv(config.data.cv_path, _mtime(config.data.cv_path))
    except Exception as exc:  # mapping is best effort
        rag_logger.info(f"resume_links: CV not loaded ({type(exc).__name__})")
    try:
        docs["about_me"] = _load_text(config.data.about_me_path, _mtime(config.data.about_me_path))
    except Exception as exc:
        rag_logger.info(f"resume_links: about_me not loaded ({type(exc).__name__})")
    return docs


def resume_entry_ids(content: str, metadata: dict[str, Any] | None = None) -> list[str]:
    """Sidebar entry ids for a retrieved chunk ([] when nothing matches or on any error)."""
    try:
        entries = _entries(config.resume)
        if not entries:
            return []
        src = str((metadata or {}).get("source") or "")
        if src == "tool":  # tool write-ups map to sidebar tool rows instead (app.modules.tools)
            return []
        docs = source_documents()
        candidates = [docs[src]] if src in docs else list(docs.values())
        return map_chunk(content, candidates, entries)
    except Exception as exc:
        rag_logger.info(f"resume_links: mapping failed ({type(exc).__name__}: {exc})")
        return []
