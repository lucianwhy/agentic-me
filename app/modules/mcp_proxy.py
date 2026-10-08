"""Proxy for the public Fengshu knowledge-base MCP demo.

Speaks plain JSON-RPC 2.0 over the server's stateless Streamable HTTP transport
(one POST per call, no initialize and no mcp-session-id). httpx only — the MCP
SDK is intentionally not a dependency.

Visitor-facing limits are stricter than the upstream tool schemas: shorter
queries, smaller top_k / max_chars, and paid content hidden unless MCP_ALLOW_PAID
is set. ``get_chunk_context`` stays off until MCP_ENABLE_CHUNK_CONTEXT is 1 or
true (the site owner has not signed off on that tool). ``search_fengshu_knowledge_multi``
is never exposed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx

from app.modules.retrieval_demo import RetrievalRateLimiter
from app.utils.logging_config import api_logger

# httpx and httpcore log the full request URL (and at DEBUG the request itself).
# MCP_URL may carry a path or query token, so those loggers stay at WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SERVER_NAME = "fengshu-knowledge"
UNAVAILABLE_MESSAGE = "体验暂不可用"
PAID_MESSAGE = "付费文章不在公开体验范围内"
TIMEOUT_MESSAGE = "知识库 MCP 响应超时，请稍后重试"
UPSTREAM_MESSAGE = "知识库 MCP 暂时不可用，请稍后重试"
RPC_ERROR_MESSAGE = "知识库 MCP 调用失败，请稍后重试"
PARSE_MESSAGE = "知识库 MCP 返回了无法解析的内容"

SEARCH_TOOL = "search_fengshu_knowledge"
ARTICLE_TOOL = "get_fengshu_article"
CHUNK_TOOL = "get_chunk_context"
# Present upstream, deliberately not part of the public demo.
_HIDDEN_TOOLS = frozenset({"search_fengshu_knowledge_multi"})

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_TRUE_VALUES = frozenset({"1", "true"})

_SNIPPET_MAX = 600
_QUERY_MIN = 2
_QUERY_MAX = 200
_TOP_K_MAX = 5
_ARTICLE_CHARS_DEFAULT = 1500
_CHARS_MIN = 500
_CHARS_MAX = 3000
_OFFSET_MAX = 10_000_000
_NEIGHBOR_MAX = 2
_TOOLS_CACHE_TTL_S = 600.0

_ACCEPT = "application/json, text/event-stream"

# Upstream contracts, used when tools/list cannot be reached. The proxy still
# clamps calls more tightly than these schemas (see _sanitize_*).
_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 2, "maxLength": 500},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
        "mode": {
            "type": "string",
            "enum": ["balanced", "semantic", "exact"],
            "default": "balanced",
        },
        "source_scope": {"type": "string", "enum": ["all", "free", "paid"]},
        "date_from": {"type": "string", "description": "YYYY-MM-DD"},
        "date_to": {"type": "string", "description": "YYYY-MM-DD"},
    },
    "required": ["query"],
}
_ARTICLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "document_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "offset": {"type": "integer", "minimum": 0, "default": 0},
        "max_chars": {
            "type": "integer",
            "minimum": 500,
            "maximum": 20000,
            "default": 8000,
        },
    },
    "required": ["document_id"],
}
_CHUNK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "document_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "chunk_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "before": {"type": "integer", "minimum": 0, "maximum": 3},
        "after": {"type": "integer", "minimum": 0, "maximum": 3},
        "max_chars": {"type": "integer", "minimum": 500, "maximum": 12000},
    },
    "required": ["document_id", "chunk_id"],
}
_TOOL_META: dict[str, dict[str, Any]] = {
    SEARCH_TOOL: {
        "title": "搜索风叔知识库",
        "description": (
            "在风叔文章知识库里混合检索，返回片段以及 document_id / chunk_id。"
            "mode 可选 balanced、semantic、exact。"
        ),
        "inputSchema": _SEARCH_SCHEMA,
    },
    ARTICLE_TOOL: {
        "title": "分页读取文章",
        "description": (
            "按 document_id 分页读取文章正文。请使用返回的 next_offset 继续读取，"
            "直到 next_offset 为 null。"
        ),
        "inputSchema": _ARTICLE_SCHEMA,
    },
    CHUNK_TOOL: {
        "title": "读取相邻片段",
        "description": "按 document_id 与 chunk_id 读取目标片段及其前后相邻片段。",
        "inputSchema": _CHUNK_SCHEMA,
    },
}

_MODES = frozenset({"balanced", "semantic", "exact"})
_SCOPES = frozenset({"all", "free", "paid"})
_SEARCH_KEYS = frozenset(
    {"query", "top_k", "mode", "source_scope", "date_from", "date_to"}
)
_ARTICLE_KEYS = frozenset({"document_id", "offset", "max_chars"})
_CHUNK_KEYS = frozenset({"document_id", "chunk_id", "before", "after", "max_chars"})


class McpError(Exception):
    """Base class for proxy failures that map to an HTTP response."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class McpUnavailable(McpError):
    """MCP_URL is unset and mock mode is off."""

    def __init__(self, message: str = UNAVAILABLE_MESSAGE) -> None:
        super().__init__(message)


class McpBadRequest(McpError):
    """Caller input the proxy will not forward. ``status`` is 400, 403, or 422."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class McpUpstreamError(McpError):
    """Timeout, transport failure, or a JSON-RPC error from the MCP server."""


@dataclass(frozen=True)
class McpSettings:
    """Env snapshot. Read on each call so tests can monkeypatch os.environ."""

    url: str
    token: str
    chunk_context: bool
    allow_paid: bool
    mock: bool

    @property
    def available(self) -> bool:
        return self.mock or bool(self.url)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_settings() -> McpSettings:
    return McpSettings(
        url=os.getenv("MCP_URL", "").strip(),
        token=os.getenv("MCP_TOKEN", "").strip(),
        chunk_context=_flag("MCP_ENABLE_CHUNK_CONTEXT"),
        allow_paid=_flag("MCP_ALLOW_PAID"),
        mock=_flag("MCP_MOCK"),
    )


def redact(text: str) -> str:
    """Drop bearer tokens and URL paths/queries before anything is logged."""
    text = text[:2000]
    token = os.getenv("MCP_TOKEN", "").strip()
    if len(token) >= 4:
        text = text.replace(token, "***")
    url = os.getenv("MCP_URL", "").strip()
    if len(url) >= 8:
        text = text.replace(url, "***")
    text = _BEARER_RE.sub("Bearer ***", text)

    def _host_only(match: re.Match[str]) -> str:
        raw = match.group(0).rstrip(".,);]")
        try:
            parts = urllib.parse.urlsplit(raw)
        except ValueError:
            return "http://***/"
        host = parts.hostname or "***"
        return f"{parts.scheme}://{host}/"

    return _URL_RE.sub(_host_only, text)


def _log_upstream(exc: BaseException) -> None:
    # Type and message only. A traceback can capture the Authorization header.
    api_logger.warning(
        "MCP upstream %s: %s", type(exc).__name__, redact(str(exc))[:400]
    )


def _allowed_names(settings: McpSettings) -> tuple[str, ...]:
    names = [SEARCH_TOOL, ARTICLE_TOOL]
    if settings.chunk_context:
        names.append(CHUNK_TOOL)
    return tuple(names)


def _public_tool(name: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = _TOOL_META[name]
    title = raw.get("title") if raw else None
    description = raw.get("description") if raw else None
    schema = raw.get("inputSchema") if raw else None
    return {
        "name": name,
        "title": title if isinstance(title, str) and title.strip() else meta["title"],
        "description": (
            description if isinstance(description, str) else meta["description"]
        ),
        "inputSchema": (
            copy.deepcopy(schema)
            if isinstance(schema, dict)
            else copy.deepcopy(meta["inputSchema"])
        ),
    }


def fallback_tools(settings: McpSettings | None = None) -> list[dict[str, Any]]:
    """Static whitelist built from the known upstream schemas."""
    settings = settings if settings is not None else get_settings()
    return [_public_tool(name) for name in _allowed_names(settings)]


def _filter_listed_tools(
    raw_tools: list[Any], settings: McpSettings
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    allowed = set(_allowed_names(settings))
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or name not in allowed or name in _HIDDEN_TOOLS:
            continue
        found[name] = _public_tool(name, item)
    return [found[name] for name in _allowed_names(settings) if name in found]


# Keep-alive client. trust_env is off so HTTP(S)_PROXY cannot see MCP_TOKEN.
# Redirects are off so the bearer token is not forwarded to another host.
_client = httpx.Client(
    timeout=httpx.Timeout(25.0, connect=5.0),
    follow_redirects=False,
    trust_env=False,
)

_id_lock = threading.Lock()
_id_counter = 0
_cache_lock = threading.Lock()
_tools_cache: tuple[float, tuple[Any, ...], list[dict[str, Any]]] | None = None


def _next_id() -> int:
    global _id_counter
    with _id_lock:
        _id_counter += 1
        return _id_counter


def _cache_key(settings: McpSettings) -> tuple[Any, ...]:
    token_tag = ""
    if settings.token:
        token_tag = hashlib.sha256(settings.token.encode()).hexdigest()[:16]
    # Host only would be wrong (two paths can differ); the URL stays in memory
    # because we must call it, but it is never logged.
    return (settings.url, settings.chunk_context, token_tag)


def _get_cached(settings: McpSettings) -> list[dict[str, Any]] | None:
    with _cache_lock:
        entry = _tools_cache
        if entry is None:
            return None
        stored_at, key, tools = entry
        if key != _cache_key(settings):
            return None
        if time.monotonic() - stored_at >= _TOOLS_CACHE_TTL_S:
            return None
        return copy.deepcopy(tools)


def _store_cache(settings: McpSettings, tools: list[dict[str, Any]]) -> None:
    global _tools_cache
    with _cache_lock:
        _tools_cache = (time.monotonic(), _cache_key(settings), copy.deepcopy(tools))


def _parse_sse(body: str) -> list[dict[str, Any]]:
    """Collect JSON objects from SSE ``data:`` lines. Ignores non-JSON events."""
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal data_lines
        if not data_lines:
            return
        raw = "\n".join(data_lines).strip()
        data_lines = []
        if not raw or raw == "[DONE]":
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return
        if isinstance(parsed, dict):
            messages.append(parsed)

    for line in body.splitlines():
        if line == "":
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].removeprefix(" "))
    flush()
    return messages


def _json_object(text: str) -> dict[str, Any] | None:
    stripped = text.lstrip("\ufeff \t\r\n")
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _match_id(messages: list[dict[str, Any]], req_id: int) -> dict[str, Any] | None:
    matched = [
        msg for msg in messages if "id" in msg and str(msg.get("id")) == str(req_id)
    ]
    if not matched:
        return None
    return matched[-1]


def _parse_response(response: httpx.Response, req_id: int) -> dict[str, Any]:
    if response.status_code < 200 or response.status_code >= 300:
        api_logger.warning("MCP HTTP status %s", response.status_code)
        raise McpUpstreamError(UPSTREAM_MESSAGE)
    text = response.text
    ctype = response.headers.get("content-type", "").lower()
    messages: list[dict[str, Any]] = []
    sse_type = "text/event-stream" in ctype
    if sse_type or (
        "application/json" not in ctype and not text.lstrip().startswith("{")
    ):
        messages = _parse_sse(text)
    if not messages:
        obj = _json_object(text)
        if obj is not None:
            messages = [obj]
    chosen = _match_id(messages, req_id)
    if chosen is None:
        api_logger.warning("MCP response had no JSON-RPC object for this request")
        raise McpUpstreamError(PARSE_MESSAGE)
    error = chosen.get("error")
    if error:
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message", "")
        else:
            code = None
            message = str(error)
        api_logger.warning(
            "MCP JSON-RPC error code=%s message=%s", code, redact(str(message))[:300]
        )
        raise McpUpstreamError(RPC_ERROR_MESSAGE)
    if "result" not in chosen:
        api_logger.warning("MCP JSON-RPC response missing result")
        raise McpUpstreamError(PARSE_MESSAGE)
    return chosen


def _rpc(settings: McpSettings, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """One stateless JSON-RPC POST. No initialize, no session header."""
    req_id = _next_id()
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    headers = {"Content-Type": "application/json", "Accept": _ACCEPT}
    if settings.token:
        headers["Authorization"] = f"Bearer {settings.token}"
    try:
        response = _client.post(settings.url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        _log_upstream(exc)
        raise McpUpstreamError(TIMEOUT_MESSAGE) from None
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        _log_upstream(exc)
        raise McpUpstreamError(UPSTREAM_MESSAGE) from None
    return _parse_response(response, req_id)


def list_tools() -> tuple[list[dict[str, Any]], bool]:
    """Return ``(tools, degraded)``. Raises McpUnavailable when unconfigured.

    A failed tools/list falls back to the known schemas and reports degraded.
    Successful lists are cached for ten minutes.
    """
    settings = get_settings()
    if settings.mock:
        return fallback_tools(settings), False
    if not settings.url:
        raise McpUnavailable()
    cached = _get_cached(settings)
    if cached is not None:
        return cached, False
    try:
        rpc = _rpc(settings, "tools/list", {})
    except McpUpstreamError:
        return fallback_tools(settings), True
    result = rpc.get("result")
    raw_tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(raw_tools, list):
        api_logger.warning("MCP tools/list result had no tools array")
        return fallback_tools(settings), True
    tools = _filter_listed_tools(raw_tools, settings)
    _store_cache(settings, tools)
    return copy.deepcopy(tools), False


def tools_status() -> dict[str, Any]:
    """Payload for GET /api/mcp/tools. Never raises."""
    settings = get_settings()
    if not settings.available:
        return {
            "available": False,
            "mock": False,
            "server": SERVER_NAME,
            "chunk_context_enabled": settings.chunk_context,
            "tools": [],
            "degraded": False,
            "message": UNAVAILABLE_MESSAGE,
        }
    try:
        tools, degraded = list_tools()
    except McpUnavailable:
        return {
            "available": False,
            "mock": False,
            "server": SERVER_NAME,
            "chunk_context_enabled": settings.chunk_context,
            "tools": [],
            "degraded": False,
            "message": UNAVAILABLE_MESSAGE,
        }
    except McpUpstreamError:
        tools, degraded = fallback_tools(settings), True
    return {
        "available": True,
        "mock": settings.mock,
        "server": SERVER_NAME,
        "chunk_context_enabled": settings.chunk_context,
        "tools": tools,
        "degraded": degraded,
    }


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # NaN and inf are not integers; bool is already excluded above.
        if not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _clamp_int(
    value: Any,
    *,
    default: int,
    lo: int,
    hi: int,
    label: str,
    notes: list[str],
) -> int:
    parsed = _parse_int(value)
    if parsed is None:
        notes.append(f"{label} → {default}")
        return default
    clamped = min(hi, max(lo, parsed))
    if clamped != parsed:
        if abs(parsed) <= 10**12:
            notes.append(f"{label} {parsed} → {clamped}")
        else:
            notes.append(f"{label} → {clamped}")
    return clamped


def _optional_int(
    raw: dict[str, Any],
    key: str,
    *,
    default: int,
    lo: int,
    hi: int,
    notes: list[str],
) -> int:
    if key not in raw or raw[key] is None:
        return default
    return _clamp_int(raw[key], default=default, lo=lo, hi=hi, label=key, notes=notes)


def _note_unknown(raw: dict[str, Any], known: frozenset[str], notes: list[str]) -> None:
    for key in sorted(raw):
        if key not in known:
            notes.append(f"忽略未知参数 {key}")


def _clean_id(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise McpBadRequest(422, f"{field} 不合法。")
    text = value.strip()
    if not text or len(text) > 128 or _ID_RE.fullmatch(text) is None:
        raise McpBadRequest(422, f"{field} 不合法。")
    return text


def _require_id(raw: dict[str, Any], field: str) -> str:
    if field not in raw or raw[field] in (None, ""):
        raise McpBadRequest(422, f"请提供 {field}。")
    return _clean_id(raw[field], field)


def _sanitize_search(
    raw: dict[str, Any], settings: McpSettings
) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    query = raw.get("query")
    if not isinstance(query, str):
        raise McpBadRequest(422, "检索词至少需要 2 个字。")
    query = query.strip()
    if len(query) < _QUERY_MIN:
        raise McpBadRequest(422, "检索词至少需要 2 个字。")
    if len(query) > _QUERY_MAX:
        raise McpBadRequest(422, "检索词请控制在 200 个字以内。")

    clean: dict[str, Any] = {
        "query": query,
        "top_k": _optional_int(
            raw, "top_k", default=5, lo=1, hi=_TOP_K_MAX, notes=notes
        ),
    }
    mode = raw.get("mode", "balanced")
    if isinstance(mode, str):
        mode = mode.strip()
    if mode in _MODES:
        clean["mode"] = mode
    else:
        clean["mode"] = "balanced"
        shown = mode if isinstance(mode, str) and mode else ""
        notes.append(f"mode {shown} → balanced" if shown else "mode → balanced")

    if settings.allow_paid:
        scope = raw.get("source_scope", "all")
        if isinstance(scope, str):
            scope = scope.strip()
        if scope not in _SCOPES:
            notes.append("source_scope → all")
            scope = "all"
        clean["source_scope"] = scope
    else:
        sent = raw.get("source_scope")
        if isinstance(sent, str):
            sent = sent.strip()
        if "source_scope" in raw and sent != "free":
            notes.append("source_scope → free")
        clean["source_scope"] = "free"

    for key in ("date_from", "date_to"):
        if key not in raw or raw[key] in (None, ""):
            continue
        value = raw[key]
        if isinstance(value, str) and _DATE_RE.fullmatch(value):
            clean[key] = value
        else:
            notes.append(f"忽略无效日期 {key}")
    _note_unknown(raw, _SEARCH_KEYS, notes)
    return clean, notes


def _sanitize_article(
    raw: dict[str, Any], settings: McpSettings
) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    document_id = _require_id(raw, "document_id")
    if not settings.allow_paid and document_id.startswith("paid-"):
        raise McpBadRequest(403, PAID_MESSAGE)
    clean = {
        "document_id": document_id,
        "offset": _optional_int(
            raw, "offset", default=0, lo=0, hi=_OFFSET_MAX, notes=notes
        ),
        "max_chars": _optional_int(
            raw,
            "max_chars",
            default=_ARTICLE_CHARS_DEFAULT,
            lo=_CHARS_MIN,
            hi=_CHARS_MAX,
            notes=notes,
        ),
    }
    _note_unknown(raw, _ARTICLE_KEYS, notes)
    return clean, notes


def _sanitize_chunk(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    clean = {
        "document_id": _require_id(raw, "document_id"),
        "chunk_id": _require_id(raw, "chunk_id"),
        "before": _optional_int(
            raw, "before", default=0, lo=0, hi=_NEIGHBOR_MAX, notes=notes
        ),
        "after": _optional_int(
            raw, "after", default=0, lo=0, hi=_NEIGHBOR_MAX, notes=notes
        ),
        "max_chars": _optional_int(
            raw,
            "max_chars",
            default=_ARTICLE_CHARS_DEFAULT,
            lo=_CHARS_MIN,
            hi=_CHARS_MAX,
            notes=notes,
        ),
    }
    _note_unknown(raw, _CHUNK_KEYS, notes)
    return clean, notes


def _ensure_allowed(name: str, settings: McpSettings) -> None:
    if name not in _TOOL_META or name in _HIDDEN_TOOLS:
        raise McpBadRequest(400, "不支持该工具。")
    if name == CHUNK_TOOL and not settings.chunk_context:
        raise McpBadRequest(400, "get_chunk_context 暂未开放。")


def _sanitize(
    name: str, raw: dict[str, Any], settings: McpSettings
) -> tuple[dict[str, Any], list[str]]:
    if name == SEARCH_TOOL:
        return _sanitize_search(raw, settings)
    if name == ARTICLE_TOOL:
        return _sanitize_article(raw, settings)
    return _sanitize_chunk(raw)


def _filter_search(content: dict[str, Any], settings: McpSettings) -> dict[str, Any]:
    results = content.get("results")
    if not isinstance(results, list):
        return content
    filtered: list[Any] = []
    for item in results:
        if not isinstance(item, dict):
            filtered.append(item)
            continue
        if not settings.allow_paid and item.get("access") == "paid":
            continue
        row = dict(item)
        snippet = row.get("snippet")
        if isinstance(snippet, str) and len(snippet) > _SNIPPET_MAX:
            row["snippet"] = snippet[:_SNIPPET_MAX]
            row["snippet_truncated"] = True
        filtered.append(row)
    updated = dict(content)
    updated["results"] = filtered
    updated["count"] = len(filtered)
    return updated


def _first_text(result: dict[str, Any]) -> str | None:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if isinstance(first, dict) and isinstance(first.get("text"), str):
        return first["text"]
    return None


def _interpret(
    name: str, rpc: dict[str, Any], settings: McpSettings
) -> tuple[Any, bool, str | None]:
    result = rpc.get("result")
    if not isinstance(result, dict):
        raise McpUpstreamError(PARSE_MESSAGE)
    is_error = result.get("isError") is True
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raw_text = _first_text(result)
        structured = None
        if isinstance(raw_text, str):
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                structured = parsed
    if name == SEARCH_TOOL and isinstance(structured, dict):
        structured = _filter_search(structured, settings)
    if (
        name == ARTICLE_TOOL
        and isinstance(structured, dict)
        and not settings.allow_paid
        and structured.get("access") == "paid"
    ):
        # Drop the body. Paid text must not reach the response.
        raise McpBadRequest(403, PAID_MESSAGE)
    error_text: str | None = None
    if is_error:
        raw_text = _first_text(result)
        if isinstance(raw_text, str) and raw_text.strip():
            error_text = redact(raw_text.strip())[:500]
        else:
            error_text = "工具调用失败"
    return structured, is_error, error_text


def _build_sample_article() -> str:
    intro = (
        "【示例文章】这是一段本地演示用的虚构正文，用来展示分页读取，"
        "并不是风叔知识库里的原文。"
    )
    sentence = "增长要分开看获客、激活和留存，先处理当前阶段真正的瓶颈。"
    parts = [intro]
    size = len(intro)
    index = 1
    while size < 4000:
        piece = f"（{index}）{sentence}"
        parts.append(piece)
        size += len(piece)
        index += 1
    return "".join(parts)


_SAMPLE_ARTICLE = _build_sample_article()

_SAMPLE_RESULTS: list[dict[str, Any]] = [
    {
        "document_id": "sample-doc-growth",
        "title": "示例：用户增长要先找瓶颈",
        "raw_title": "示例：用户增长要先找瓶颈",
        "author": "风叔",
        "date": "2024-03-18",
        "source_type": "toutiao",
        "url": "https://example.com/fengshu/sample-growth",
        "access": "free",
        "chunk_id": "sample-chunk-growth-2",
        "chunk_index": 2,
        "snippet": "【示例】获客、激活、留存要分开看，先找到当前阶段的瓶颈指标。",
        "exact_match": False,
    },
    {
        "document_id": "sample-doc-content",
        "title": "示例：内容选题来自读者问题",
        "raw_title": "示例：内容选题来自读者问题",
        "author": "风叔",
        "date": "2023-11-02",
        "source_type": "archive",
        "url": None,
        "access": "free",
        "chunk_id": "sample-chunk-content-0",
        "chunk_index": 0,
        "snippet": "【示例】选题来自读者真正问过的问题，复盘只看完读和转发。",
        "exact_match": False,
    },
    {
        "document_id": "sample-doc-pricing",
        "title": "示例：免费内容与付费内容的边界",
        "raw_title": "示例：免费内容与付费内容的边界",
        "author": "风叔",
        "date": "2024-08-09",
        "source_type": "toutiao",
        "url": "https://example.com/fengshu/sample-pricing",
        "access": "free",
        "chunk_id": "sample-chunk-pricing-4",
        "chunk_index": 4,
        "snippet": "【示例】公开演示只展示免费段落，付费正文不会出现在这里。",
        "exact_match": False,
    },
]
_SAMPLE_DOCS: dict[str, dict[str, Any]] = {
    "sample-doc-growth": {
        "title": "示例：用户增长要先找瓶颈",
        "raw_title": "示例：用户增长要先找瓶颈",
        "date": "2024-03-18",
        "source_type": "toutiao",
        "url": "https://example.com/fengshu/sample-growth",
    },
    "sample-doc-content": {
        "title": "示例：内容选题来自读者问题",
        "raw_title": "示例：内容选题来自读者问题",
        "date": "2023-11-02",
        "source_type": "archive",
        "url": None,
    },
    "sample-doc-pricing": {
        "title": "示例：免费内容与付费内容的边界",
        "raw_title": "示例：免费内容与付费内容的边界",
        "date": "2024-08-09",
        "source_type": "toutiao",
        "url": "https://example.com/fengshu/sample-pricing",
    },
}


def _mock_search(clean: dict[str, Any], settings: McpSettings) -> dict[str, Any]:
    exact = clean["mode"] == "exact"
    rows: list[dict[str, Any]] = []
    for item in _SAMPLE_RESULTS:
        if clean["source_scope"] == "paid" and item["access"] != "paid":
            continue
        if clean["source_scope"] == "free" and item["access"] != "free":
            continue
        if clean.get("date_from") and item["date"] < clean["date_from"]:
            continue
        if clean.get("date_to") and item["date"] > clean["date_to"]:
            continue
        row = dict(item)
        haystack = f"{row['title']}{row['snippet']}"
        row["exact_match"] = bool(exact and clean["query"] in haystack)
        rows.append(row)
    rows = rows[: clean["top_k"]]
    return _filter_search(
        {"query": clean["query"], "count": len(rows), "results": rows},
        settings,
    )


def _mock_article(clean: dict[str, Any]) -> dict[str, Any]:
    meta = _SAMPLE_DOCS.get(clean["document_id"])
    title = meta["title"] if meta else "示例：演示文章"
    raw_title = meta["raw_title"] if meta else "示例：演示文章"
    date = meta["date"] if meta else "2024-01-01"
    source_type = meta["source_type"] if meta else "archive"
    url = meta["url"] if meta else None
    total = len(_SAMPLE_ARTICLE)
    offset = clean["offset"]
    if offset >= total:
        content = ""
        next_offset = None
    else:
        content = _SAMPLE_ARTICLE[offset : offset + clean["max_chars"]]
        end = offset + len(content)
        next_offset = end if end < total else None
    access = "paid" if clean["document_id"].startswith("paid-") else "free"
    return {
        "document_id": clean["document_id"],
        "title": title,
        "raw_title": raw_title,
        "author": "风叔",
        "date": date,
        "source_type": source_type,
        "url": url,
        "access": access,
        "content": content,
        "offset": offset,
        "next_offset": next_offset,
        "total_chars": total,
    }


def _mock_chunk(clean: dict[str, Any]) -> dict[str, Any]:
    target_index = 3
    chunks: list[dict[str, Any]] = []
    for step in range(clean["before"], 0, -1):
        index = target_index - step
        chunks.append(
            {
                "chunk_id": f"sample-before-{index}",
                "chunk_index": index,
                "relation": "before",
                "text": f"【示例上下文·前文 {step}】这是紧挨目标片段之前的演示文字。",
            }
        )
    chunks.append(
        {
            "chunk_id": clean["chunk_id"],
            "chunk_index": target_index,
            "relation": "target",
            "text": "【示例上下文·目标】这里是被命中的演示片段，只用于本地体验。",
        }
    )
    for step in range(1, clean["after"] + 1):
        index = target_index + step
        chunks.append(
            {
                "chunk_id": f"sample-after-{index}",
                "chunk_index": index,
                "relation": "after",
                "text": f"【示例上下文·后文 {step}】这是紧挨目标片段之后的演示文字。",
            }
        )
    remaining = clean["max_chars"]
    fitted: list[dict[str, Any]] = []
    truncated = False
    for chunk in chunks:
        text = str(chunk["text"])
        if len(text) <= remaining:
            fitted.append(chunk)
            remaining -= len(text)
            continue
        truncated = True
        if remaining > 0:
            fitted.append({**chunk, "text": text[:remaining]})
        break
    if len(fitted) < len(chunks):
        truncated = True
    return {
        "document_id": clean["document_id"],
        "title": "示例：相邻片段上下文",
        "target_chunk_id": clean["chunk_id"],
        "chunks": fitted,
        "truncated": truncated,
    }


def _mock_call(
    name: str, clean: dict[str, Any], settings: McpSettings
) -> dict[str, Any]:
    if name == SEARCH_TOOL:
        return _mock_search(clean, settings)
    if name == ARTICLE_TOOL:
        return _mock_article(clean)
    return _mock_chunk(clean)


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Run one whitelisted tool. Raises McpUnavailable / McpBadRequest / McpUpstreamError."""
    settings = get_settings()
    if not settings.available:
        raise McpUnavailable()
    if not isinstance(name, str) or not name.strip():
        raise McpBadRequest(400, "不支持该工具。")
    tool = name.strip()
    _ensure_allowed(tool, settings)
    raw = arguments if arguments is not None else {}
    if not isinstance(raw, dict):
        raise McpBadRequest(422, "参数格式不正确。")
    # JSON object keys are strings; reject anything else rather than forwarding it.
    if any(not isinstance(key, str) for key in raw):
        raise McpBadRequest(422, "参数格式不正确。")
    clean, notes = _sanitize(tool, raw, settings)
    started = time.perf_counter()
    if settings.mock:
        structured: Any = _mock_call(tool, clean, settings)
        is_error = False
        error_text = None
        mocked = True
    else:
        rpc = _rpc(settings, "tools/call", {"name": tool, "arguments": clean})
        structured, is_error, error_text = _interpret(tool, rpc, settings)
        mocked = False
    if (
        tool == ARTICLE_TOOL
        and settings.mock
        and isinstance(structured, dict)
        and not settings.allow_paid
        and structured.get("access") == "paid"
    ):
        raise McpBadRequest(403, PAID_MESSAGE)
    return {
        "tool": tool,
        "arguments": clean,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "result": structured,
        "is_error": is_error,
        "error_text": error_text,
        "mock": mocked,
        "clamped": notes,
    }


def _rate_min_interval_ms() -> int:
    return _env_int("MCP_RATE_MIN_INTERVAL_MS", 1000)


def _rate_per_minute() -> int:
    return _env_int("MCP_RATE_PER_MINUTE", 20)


mcp_limiter = RetrievalRateLimiter(_rate_min_interval_ms(), _rate_per_minute())


def refresh_rate_limits() -> None:
    """Re-read MCP_RATE_* so a process can pick up env changes (and tests can)."""
    mcp_limiter.min_interval = max(0, _rate_min_interval_ms()) / 1000.0
    mcp_limiter.per_minute = max(1, _rate_per_minute())


def check_rate(client_key: str) -> float:
    """Return seconds to wait, or 0 when the call is allowed."""
    refresh_rate_limits()
    return mcp_limiter.check(client_key)
