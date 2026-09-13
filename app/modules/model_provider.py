import logging
import os
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import AppConfig
from app.modules.readiness import LLMNotConfigured


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

    def get_language_model(self) -> Any:
        """Return the configured chat model. Does not call the network."""
        provider = str(self.config.llm.provider).lower()
        self.logger.info(
            f"Starting initialization of language model '{self.config.llm.model}'."
        )
        if "ollama" in provider:
            self.logger.info("Using optional Ollama language model provider.")
            try:
                from langchain_ollama import ChatOllama
            except ImportError as exc:
                raise LLMNotConfigured(
                    "已选择 Ollama，但未安装 langchain-ollama。"
                    "请执行：pip install langchain-ollama"
                ) from exc
            return ChatOllama(
                model=self.config.llm.model,
                temperature=self.config.llm.temperature,
                base_url=self.config.ollama.endpoint,
            )

        if not self.config.resolved_api_key() and not os.getenv("OPENAI_API_KEY"):
            raise LLMNotConfigured("尚未配置 OPENAI_API_KEY，无法初始化对话模型。")

        self.logger.info(
            "Using OpenAI-compatible language model"
            + (
                f" at {self.config.resolved_base_url()}"
                if self.config.resolved_base_url()
                else ""
            )
        )
        llm_kwargs = {
            "model": self.config.llm.model,
            "temperature": self.config.llm.temperature,
            "timeout": self.config.llm.timeout,
            **self._openai_kwargs(for_embedding=False),
        }
        effort = (getattr(self.config.llm, "reasoning_effort", None) or "").strip()
        if effort:
            # OpenAI / nuoapi Chat Completions: reasoning_effort
            llm_kwargs["reasoning_effort"] = effort
            self.logger.info(f"Using reasoning_effort={effort}")
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

            return ArkMultimodalEmbeddings(
                api_key=api_key,
                model=model_name,
                base_url=self.config.embedding.base_url
                or "https://ark.cn-beijing.volces.com/api/v3",
                timeout=float(getattr(self.config.llm, "timeout", 60) or 60),
            )

        if not self.config.resolved_api_key() and not os.getenv("OPENAI_API_KEY"):
            raise LLMNotConfigured(
                "尚未配置 OPENAI_API_KEY，无法初始化 Embedding 模型。"
            )

        self.logger.info("Using OpenAI-compatible embedding model.")
        return OpenAIEmbeddings(
            model=self.config.embedding.model,
            **self._openai_kwargs(for_embedding=True),
        )
