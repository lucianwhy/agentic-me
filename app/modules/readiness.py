"""Runtime readiness checks so the app can start without API keys."""

from __future__ import annotations

import os
from typing import Any

from app.config import config


class LLMNotConfigured(RuntimeError):
    """Raised when an OpenAI-compatible API key is required but missing."""


class VectorStoreNotReady(RuntimeError):
    """Raised when the vector store has not been built yet."""


def is_llm_configured() -> bool:
    """True when the configured LLM provider can be used."""
    provider = str(config.llm.provider).lower()
    if "ollama" in provider:
        return True
    return bool(config.resolved_api_key())


def is_vectorstore_ready() -> bool:
    """True when a persisted Chroma directory looks populated.

    Avoids opening Chroma / calling embeddings so /health stays cheap.
    """
    path = config.data.vector_db_path
    if not path or not os.path.isdir(path):
        return False
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    if not entries:
        return False
    return os.path.exists(os.path.join(path, "chroma.sqlite3")) or any(
        name == "index" or name.endswith(".sqlite3") for name in entries
    )


def get_readiness() -> dict[str, Any]:
    """Snapshot used by /health and chat error payloads."""
    return {
        "llm_configured": is_llm_configured(),
        "vectorstore_ready": is_vectorstore_ready(),
        "auth_enabled": bool(config.invite_codes),
        "llm_provider": config.llm.provider,
        "llm_model": config.llm.model,
    }


def chinese_not_ready_error() -> dict[str, Any]:
    """Clear Chinese JSON error when chat cannot run yet."""
    if not is_llm_configured():
        return {
            "error": True,
            "code": "llm_not_configured",
            "message": (
                "尚未配置大模型 API。请在 .env 中设置 OPENAI_API_KEY；"
                "如使用 DeepSeek 等 OpenAI 兼容接口，请同时设置 OPENAI_BASE_URL 或 LLM_BASE_URL。"
            ),
        }
    if not is_vectorstore_ready():
        return {
            "error": True,
            "code": "vectorstore_not_ready",
            "message": (
                "向量库尚未就绪。请先将简历 PDF 放到 data/ 目录并完善 data/about_me.md，"
                "然后运行：python -m app.modules.rag_pipeline --ingest"
            ),
        }
    return {
        "error": True,
        "code": "not_ready",
        "message": "服务尚未就绪，请稍后重试。",
    }
