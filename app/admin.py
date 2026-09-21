"""Password-protected runtime settings for the local resume site admin page."""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from threading import RLock
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from app.config import config

ADMIN_COOKIE_NAME = "admin_session"
ENV_FILE = Path(".env")
REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")

_admin_sessions: set[str] = set()
_lock = RLock()


def create_admin_session(password: str) -> str | None:
    """Issue an in-memory session token when the configured password matches."""
    if not secrets.compare_digest(password, config.resolved_admin_password()):
        return None
    token = secrets.token_urlsafe(32)
    with _lock:
        _admin_sessions.add(token)
    return token


def revoke_admin_session(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _admin_sessions.discard(token)


def require_admin(request: Request) -> None:
    """FastAPI dependency that protects administration APIs."""
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    with _lock:
        authenticated = bool(token and token in _admin_sessions)
    if not authenticated:
        raise HTTPException(status_code=401, detail="请先输入管理密码。")


def public_settings() -> dict[str, object]:
    """Return editable settings without ever returning the API key itself."""
    return {
        "api_key_configured": bool(config.resolved_api_key()),
        "base_url": config.resolved_base_url() or "",
        "model": config.llm.model,
        "reasoning_effort": config.llm.reasoning_effort or "none",
        "reasoning_efforts": list(REASONING_EFFORTS),
    }


def _validate_base_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("接口地址必须是完整的 http:// 或 https:// 地址。")
    return value.rstrip("/")


def _validate_model(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 128:
        raise ValueError("模型名称不能为空，且不能超过 128 个字符。")
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", value):
        raise ValueError("模型名称只能包含字母、数字、点、下划线、连字符、冒号或斜杠。")
    return value


def _write_env_values(values: dict[str, str]) -> None:
    """Atomically upsert selected keys while preserving unrelated .env entries."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    remaining = set(values)
    out: list[str] = []
    for line in existing.splitlines():
        match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=.*$", line)
        key = match.group(2) if match else None
        if key in values:
            out.append(f"{key}={json.dumps(values[key], ensure_ascii=False)}")
            remaining.discard(key)
        else:
            out.append(line)
    if out and out[-1] != "":
        out.append("")
    out.extend(f"{key}={json.dumps(values[key], ensure_ascii=False)}" for key in sorted(remaining))
    content = "\n".join(out).rstrip() + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=ENV_FILE.parent, delete=False
    ) as temp_file:
        temp_file.write(content)
        temp_name = temp_file.name
    Path(temp_name).replace(ENV_FILE)


def update_settings(
    *,
    api_key: str | None,
    base_url: str,
    model: str,
    reasoning_effort: str,
) -> dict[str, object]:
    """Persist safe settings and update the in-process configuration immediately."""
    normalized_base_url = _validate_base_url(base_url)
    normalized_model = _validate_model(model)
    normalized_effort = reasoning_effort.strip().lower()
    if normalized_effort not in REASONING_EFFORTS:
        raise ValueError("不支持的分析强度。")
    if api_key is not None and not api_key.strip():
        raise ValueError("API Key 不能为空；若不修改，请留空该字段。")

    values = {
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": normalized_model,
        "OPENAI_BASE_URL": normalized_base_url,
        "REASONING_EFFORT": normalized_effort,
    }
    if api_key is not None:
        values["OPENAI_API_KEY"] = api_key.strip()

    with _lock:
        _write_env_values(values)
        for key, value in values.items():
            os.environ[key] = value
        config.llm.provider = "openai"
        config.llm.model = normalized_model
        config.llm.reasoning_effort = normalized_effort
        config.llm.base_url = normalized_base_url or None
        config.openai_base_url = normalized_base_url or None
        config.llm_base_url = normalized_base_url or None
        if api_key is not None:
            config.openai_api_key = api_key.strip()

    _reset_cached_llm_clients()
    return public_settings()


def _reset_cached_llm_clients() -> None:
    """Discard chains built with prior model credentials or settings."""
    from app.modules.job_matching import get_job_analyzer
    from app.modules.rag_pipeline import get_chat_pipeline
    from app.modules.summary_pipeline import get_summary_generator

    get_chat_pipeline().reset_model_caches()
    get_summary_generator().reset_model_cache()
    get_job_analyzer().reset_model_cache()
