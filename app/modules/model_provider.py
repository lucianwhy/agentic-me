import logging
import os
import threading
from typing import Any

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import AppConfig
from app.modules.readiness import LLMNotConfigured
from app.utils.env import env_get

# Shared across requests: one keep-alive HTTP client for the chat API and one embeddings
# instance per (provider, model, base_url, key) so connections and the query-embedding
# LRU survive between requests (chat pipeline, /api/retrieve, warm-up).
_LLM_HTTP_CLIENT: httpx.Client | None = None
_EMBEDDINGS: dict[tuple, Any] = {}
_SHARED_LOCK = threading.Lock()


def shared_llm_http_client() -> httpx.Client:
    global _LLM_HTTP_CLIENT
    with _SHARED_LOCK:
        if _LLM_HTTP_CLIENT is None:
            _LLM_HTTP_CLIENT = httpx.Client(
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=8, keepalive_expiry=120),
                timeout=None,  # per-request timeout comes from ChatOpenAI(timeout=...)
            )
        return _LLM_HTTP_CLIENT


class ModelProvider:
    """
    Initialize language and embedding models from application configuration.

    Supports OpenAI and any OpenAI-compatible endpoint (DeepSeek, etc.) via
    OPENAI_API_KEY + OPENAI_BASE_URL / LLM_BASE_URL. Ollama is an optional
    extra and is imported only when selected. Ark / Volcengine multimodal
    embeddings use ARK_API_KEY (or EMBEDDING_API_KEY) independently of chat.
    """

    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def _openai_kwargs(self, *, for_embedding: bool = False) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        api_key = self.config.resolved_api_key()
        if api_key:
            kwargs["api_key"] = api_key

        if for_embedding:
            base_url = (self.config.embedding.base_url or "").strip() or (
                self.config.resolved_base_url() or ""
            )
        else:
            base_url = self.config.resolved_base_url() or ""
        if base_url:
            kwargs["base_url"] = base_url
        return kwargs

    def _registry_entry(self, model_name: str) -> dict[str, Any]:
        from app.model_registry import get_model_registry

        return get_model_registry().get(model_name) or {}

    def get_language_model(
        self,
        model: str | None = None,
        reasoning_effort: str | None = None,
        *,
        base_url: str | None = None,
        api_key_env: str | None = None,
        thinking: str | None = None,
    ) -> Any:
        """Return the configured chat model. Does not call the network.

        Optional ``model`` overrides ``config.llm.model`` for this instance only (used by
        the per-request model switcher); ``reasoning_effort`` overrides the global
        REASONING_EFFORT (per-model setting from the admin model list).

        ``base_url`` / ``api_key_env`` / ``thinking`` come from the admin model entry.
        When omitted they are filled from the registry for ``model``. A model with its
        own ``base_url`` always uses the Chat Completions API and never inherits the
        global REASONING_EFFORT (that value is tuned for nuoapi). ``api_key_env`` is
        the name of an environment variable — never a key value.
        """
        provider = str(self.config.llm.provider).lower()
        model_name = (model or "").strip() or self.config.llm.model
        entry = self._registry_entry(model_name)

        def _resolve(explicit: str | None, key: str) -> str | None:
            raw = explicit if explicit is not None else entry.get(key)
            text = str(raw or "").strip()
            return text or None

        resolved_base_url = _resolve(base_url, "base_url")
        resolved_key_env = _resolve(api_key_env, "api_key_env")
        resolved_thinking = _resolve(thinking, "thinking")
        resolved_effort = (
            reasoning_effort if reasoning_effort is not None else entry.get("reasoning_effort")
        )
        per_model_endpoint = bool(resolved_base_url)

        self.logger.info(
            f"Starting initialization of language model '{model_name}'."
        )
        if "ollama" in provider and not per_model_endpoint and not resolved_key_env:
            self.logger.info("Using optional Ollama language model provider.")
            try:
                from langchain_ollama import ChatOllama
            except ImportError as exc:
                raise LLMNotConfigured(
                    "已选择 Ollama，但未安装 langchain-ollama。"
                    "请执行：pip install langchain-ollama"
                ) from exc
            return ChatOllama(
                model=model_name,
                temperature=self.config.llm.temperature,
                base_url=self.config.ollama.endpoint,
            )

        openai_kwargs: dict[str, Any]
        if resolved_key_env:
            api_key = env_get(resolved_key_env).strip()
            if not api_key:
                raise LLMNotConfigured(
                    f"尚未配置环境变量 {resolved_key_env}，无法初始化对话模型。"
                )
            openai_kwargs = {"api_key": api_key}
            if resolved_base_url:
                openai_kwargs["base_url"] = resolved_base_url
            elif self.config.resolved_base_url():
                openai_kwargs["base_url"] = self.config.resolved_base_url()
        else:
            if not self.config.resolved_api_key() and not os.getenv("OPENAI_API_KEY"):
                raise LLMNotConfigured("尚未配置 OPENAI_API_KEY，无法初始化对话模型。")
            openai_kwargs = self._openai_kwargs(for_embedding=False)
            if resolved_base_url:
                openai_kwargs["base_url"] = resolved_base_url

        endpoint = openai_kwargs.get("base_url") or self.config.resolved_base_url()
        self.logger.info(
            "Using OpenAI-compatible language model"
            + (f" at {endpoint}" if endpoint else "")
        )
        llm_kwargs: dict[str, Any] = {
            "model": model_name,
            "temperature": self.config.llm.temperature,
            "timeout": self.config.llm.timeout,
            "http_client": shared_llm_http_client(),
            # Per-model endpoints are always Chat Completions (Zhipu etc. have no
            # Responses API). Global LLM_API still applies to the default nuoapi path.
            "use_responses_api": (
                False
                if per_model_endpoint
                else getattr(self.config.llm, "api", "chat_completions") == "responses"
            ),
            **openai_kwargs,
        }
        if per_model_endpoint:
            effort = str(resolved_effort or "").strip()
        else:
            effort = (
                resolved_effort
                or getattr(self.config.llm, "reasoning_effort", None)
                or ""
            )
            effort = str(effort).strip()
        if effort:
            # OpenAI / nuoapi Chat Completions: reasoning_effort
            llm_kwargs["reasoning_effort"] = effort
            self.logger.info(f"Using reasoning_effort={effort}")
        if resolved_thinking:
            extra_body = dict(llm_kwargs.get("extra_body") or {})
            extra_body["thinking"] = {"type": resolved_thinking}
            llm_kwargs["extra_body"] = extra_body
        return ChatOpenAI(**llm_kwargs)

    def get_embedding_model(self) -> Any:
        """Return the configured embedding model. Does not call the network."""
        provider = str(self.config.embedding.provider).lower()
        model_name = str(self.config.embedding.model)
        self.logger.info(f"Starting initialization of embedding model '{model_name}'.")
        if "ollama" in provider or "ollama" in model_name.lower():
            self.logger.info("Using optional Ollama embedding provider.")
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError as exc:
                raise LLMNotConfigured(
                    "已选择 Ollama Embedding，但未安装 langchain-ollama。"
                    "请执行：pip install langchain-ollama"
                ) from exc
            return OllamaEmbeddings(
                model=self.config.embedding.model,
                base_url=self.config.ollama.endpoint,
            )

        if provider in ("fastembed", "local"):
            self.logger.info("Using local FastEmbed embedding provider.")
            try:
                from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
            except ImportError as exc:
                raise LLMNotConfigured(
                    "已选择 FastEmbed，但未安装 fastembed。"
                    "请执行：pip install fastembed"
                ) from exc
            return FastEmbedEmbeddings(model_name=model_name)

        if provider in ("ark", "volcengine", "doubao"):
            self.logger.info(
                "Using Volcengine Ark multimodal embedding provider "
                f"(model={model_name}, base={self.config.embedding.base_url or 'default'})."
            )
            api_key = self.config.resolved_embedding_api_key()
            if not api_key:
                raise LLMNotConfigured(
                    "已选择 Ark Embedding，但未配置 ARK_API_KEY 或 EMBEDDING_API_KEY。"
                )
            from app.modules.ark_embeddings import ArkMultimodalEmbeddings

            base_url = self.config.embedding.base_url or "https://ark.cn-beijing.volces.com/api/v3"
            cache_key = ("ark", model_name, base_url, hash(api_key))
            with _SHARED_LOCK:
                cached = _EMBEDDINGS.get(cache_key)
                if cached is None:
                    cached = ArkMultimodalEmbeddings(
                        api_key=api_key,
                        model=model_name,
                        base_url=base_url,
                        timeout=float(getattr(self.config.llm, "timeout", 60) or 60),
                        query_cache_size=self.config.chat.embedding_cache_size,
                    )
                    _EMBEDDINGS[cache_key] = cached
            return cached

        if not self.config.resolved_api_key() and not os.getenv("OPENAI_API_KEY"):
            raise LLMNotConfigured(
                "尚未配置 OPENAI_API_KEY，无法初始化 Embedding 模型。"
            )

        self.logger.info("Using OpenAI-compatible embedding model.")
        return OpenAIEmbeddings(
            model=self.config.embedding.model,
            **self._openai_kwargs(for_embedding=True),
        )
