import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """Configuration for the Large Language Model (LLM) settings."""

    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    timeout: int = 60
    reasoning_effort: str | None = "medium"
    base_url: str | None = None


class OllamaConfig(BaseModel):
    """Configuration for the Ollama model endpoint and parameters."""

    endpoint: str = "http://localhost:11434"
    models: str = "llama3.2"
    timeout: int = 120


class EmbeddingConfig(BaseModel):
    """Configuration for embedding model parameters."""

    provider: str = "openai"
    model: str = "text-embedding-3-small"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    base_url: str | None = None


class VectorStoreConfig(BaseModel):
    """Configuration for vector store settings."""

    provider: str = "chroma"
    persist_directory: str = "data/vector_db"
    collection_name: str = "chatcv"
    retrieval_k: int = 8


class RateLimitConfig(BaseModel):
    """Configuration for rate limiting API requests."""

    enabled: bool = True
    requests_per_minute: int = 20
    burst_limit: int = 5
    rate_limit_ms: int = 3000


class SecurityConfig(BaseModel):
    """Configuration for security-related settings."""

    session_timeout_hours: int = 24
    max_query_length: int = 1000
    max_job_text_length: int = 5000
    min_job_text_length: int = 50
    allowed_origins: list[str] = ["*"]
    secure_cookies: bool = True


class LoggingConfig(BaseModel):
    """Configuration for logging behavior and file management."""

    level: str = "INFO"
    file_path: str = "logs/chatcv.log"
    max_file_size_mb: int = 100
    backup_count: int = 5
    analytics_enabled: bool = True


class DataPaths(BaseModel):
    """Configuration for various data file paths used by the application."""

    cv_path: str = "data/CV_Demo.pdf"
    about_me_path: str = "data/about_me.md"
    vector_db_path: str = "data/vector_db"
    analytics_log_path: str = "data/analytics.log"


class CandidateConfig(BaseModel):
    """Configuration for candidate information displayed in the application."""

    name: str = "你的姓名"
    headline: str = "求职方向 / 一句话介绍"
    email: str = "your.email@example.com"
    phone: str = ""
    linkedin: str = "https://linkedin.com/in/your-profile"
    github: str = "https://github.com/your-username"
    scholar: str = ""


class AppConfig(BaseSettings):
    """
    Main application configuration class that aggregates all sub-configurations.

    This includes environment settings, API keys, model configurations,
    rate limiting, security, logging, data paths, and invite codes.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        populate_by_name=True,
    )

    environment: str = Field(default="development")
    debug: bool = False
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_model_env: str | None = Field(default=None, alias="LLM_MODEL")
    llm_provider_env: str | None = Field(default=None, alias="LLM_PROVIDER")
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")
    embedding_model_env: str | None = Field(default=None, alias="EMBEDDING_MODEL")
    reasoning_effort_env: str | None = Field(default=None, alias="REASONING_EFFORT")
    embedding_provider_env: str | None = Field(default=None, alias="EMBEDDING_PROVIDER")
    embedding_base_url: str | None = Field(default=None, alias="EMBEDDING_BASE_URL")
    ark_api_key: str | None = Field(default=None, alias="ARK_API_KEY")
    embedding_api_key: str | None = Field(default=None, alias="EMBEDDING_API_KEY")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")

    llm: LLMConfig = LLMConfig()
    ollama: OllamaConfig = OllamaConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    vectorstore: VectorStoreConfig = VectorStoreConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    security: SecurityConfig = SecurityConfig()
    logging: LoggingConfig = LoggingConfig()
    data: DataPaths = DataPaths()
    candidate: CandidateConfig = CandidateConfig()
    invite_codes: dict[str, Any] = {}

    invite_codes_env: str | None = Field(default=None, alias="INVITE_CODES")

    chat_system_prompt: str = (
        "你是{candidate_name}的智能简历助手，请严格依据提供的资料用中文回答。"
        "Retrieved context: {{context}}"
    )
    chat_fallback_response: str = (
        "抱歉，暂时无法回答这个问题。请换一种问法，或询问{candidate_name}的经历、项目或技能。"
    )
    conversation_history_prompt: str = (
        "结合对话上下文，生成一条用于检索{candidate_name}背景资料的搜索查询。"
    )
    summary_prompt_template: str = (
        "请用中文为{candidate_name}撰写一份简洁的专业摘要。\n\nContext: {{context}}"
    )
    job_matching_system_prompt: str = (
        "你是资深技术招聘顾问，请用中文评估候选人与岗位的匹配度。"
    )
    job_matching_analysis_prompt: str = (
        "请分析{candidate_name}与岗位的匹配情况。\n\n**资料：**\n{{context}}"
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._apply_runtime_overrides()
        self._load_invite_codes_from_env()

    def _apply_runtime_overrides(self) -> None:
        """Overlay env vars that YAML nested models would otherwise ignore."""
        api_key = (self.openai_api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        self.openai_api_key = api_key or None

        base_url = (
            (self.openai_base_url or "").strip()
            or (self.llm_base_url or "").strip()
            or (os.getenv("OPENAI_BASE_URL") or "").strip()
            or (os.getenv("LLM_BASE_URL") or "").strip()
        )
        self.openai_base_url = base_url or None
        self.llm_base_url = self.openai_base_url
        if base_url:
            self.llm.base_url = base_url

        embedding_base = (
            (self.embedding_base_url or "").strip()
            or (os.getenv("EMBEDDING_BASE_URL") or "").strip()
            or base_url
        )
        self.embedding_base_url = embedding_base or None
        if embedding_base:
            self.embedding.base_url = embedding_base

        llm_model = (self.llm_model_env or os.getenv("LLM_MODEL") or "").strip()
        if llm_model:
            self.llm.model = llm_model

        llm_provider = (
            self.llm_provider_env or os.getenv("LLM_PROVIDER") or ""
        ).strip()
        if llm_provider:
            self.llm.provider = llm_provider

        reasoning_effort = (
            self.reasoning_effort_env or os.getenv("REASONING_EFFORT") or ""
        ).strip()
        if reasoning_effort:
            self.llm.reasoning_effort = reasoning_effort

        embedding_model = (
            self.embedding_model_env or os.getenv("EMBEDDING_MODEL") or ""
        ).strip()
        if embedding_model:
            self.embedding.model = embedding_model

        embedding_provider = (
            self.embedding_provider_env or os.getenv("EMBEDDING_PROVIDER") or ""
        ).strip()
        if embedding_provider:
            self.embedding.provider = embedding_provider

        ark_key = (
            (self.ark_api_key or "").strip()
            or (os.getenv("ARK_API_KEY") or "").strip()
        )
        self.ark_api_key = ark_key or None

        emb_key = (
            (self.embedding_api_key or "").strip()
            or (os.getenv("EMBEDDING_API_KEY") or "").strip()
        )
        self.embedding_api_key = emb_key or None

        ollama_endpoint = (os.getenv("OLLAMA_ENDPOINT") or "").strip()
        if ollama_endpoint:
            self.ollama.endpoint = ollama_endpoint

    def _load_invite_codes_from_env(self) -> None:
        """Load invite codes from environment variables. Empty means public mode."""
        if not self.invite_codes_env:
            return

        raw = self.invite_codes_env.strip()
        if raw in ("", "{}", "[]", "null", "None"):
            return

        try:
            env_codes = json.loads(raw)
            if isinstance(env_codes, dict):
                self.invite_codes.update(env_codes)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in INVITE_CODES environment variable: {e}")

    def resolved_api_key(self) -> str | None:
        """Return a non-empty API key if configured."""
        key = (self.openai_api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        return key or None

    def resolved_embedding_api_key(self) -> str | None:
        """Return Ark / embedding-specific API key (independent of chat LLM)."""
        key = (
            (self.ark_api_key or "").strip()
            or (self.embedding_api_key or "").strip()
            or (os.getenv("ARK_API_KEY") or "").strip()
            or (os.getenv("EMBEDDING_API_KEY") or "").strip()
        )
        return key or None

    def resolved_base_url(self) -> str | None:
        """Return OpenAI-compatible base URL if configured."""
        url = (
            (self.llm.base_url or "")
            or (self.openai_base_url or "")
            or (self.llm_base_url or "")
        ).strip()
        return url or None

    def is_openai_compatible(self) -> bool:
        provider = str(self.llm.provider).lower()
        return "ollama" not in provider

    def resolved_admin_password(self) -> str:
        """Return the local admin password, with a user-requested default."""
        value = (self.admin_password or os.getenv("ADMIN_PASSWORD") or "admin123").strip()
        return value or "admin123"

    def cv_public_url(self) -> str:
        """URL path for downloading the CV via the /data static mount."""
        path = (self.data.cv_path or "").replace("\\", "/")
        if path.startswith("/data/"):
            return path
        if path.startswith("data/"):
            return "/" + path
        return "/data/" + os.path.basename(path)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two dictionaries.

    Values from the override dictionary take precedence over those in the base dictionary.
    Nested dictionaries are merged recursively.
    """
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> AppConfig:
    """
    Load and merge configuration from YAML files and environment variables.

    Loads the base configuration from 'config/base.yml' and environment-specific overrides
    from 'config/{ENVIRONMENT}.yml'. Then overlays these settings with environment variables
    and returns a fully constructed AppConfig instance.
    """
    env = os.getenv("ENVIRONMENT", "development")
    base = Path("config/base.yml")
    override = Path(f"config/{env}.yml")

    merged_data: dict[str, Any] = {}

    if base.exists():
        with open(base, "r", encoding="utf-8") as f:
            merged_data = yaml.safe_load(f) or {}

    if override.exists():
        with open(override, "r", encoding="utf-8") as f:
            override_data = yaml.safe_load(f) or {}
            merged_data = deep_merge(merged_data, override_data)

    return AppConfig(**merged_data)


config = load_config()
