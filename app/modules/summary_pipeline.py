"""
Summary Generation Pipeline for ChatCV

LangSmith is optional. The LLM is created on first use so importing this
module never requires an API key.
"""

import threading
from typing import Any

from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate

from app.config import config
from app.modules.langchain_compat import create_stuff_documents_chain
from app.modules.model_provider import ModelProvider
from app.modules.readiness import LLMNotConfigured, is_llm_configured
from app.modules.vectorstore_provider import DocumentHandler
from app.utils.logging_config import summary_logger

try:
    from langsmith import get_current_run_tree
    from langsmith import traceable as langsmith_traceable
except ImportError:

    def langsmith_traceable(*args: Any, **kwargs: Any):  # type: ignore[misc]
        def decorator(func):
            return func

        return decorator

    def get_current_run_tree():  # type: ignore[misc]
        return None


load_dotenv()


class SummaryGenerator:
    """Generates professional summaries using LLM with thread-safe singleton pattern"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        summary_logger.info("Initializing SummaryGenerator singleton instance")
        self.model_provider = ModelProvider(config, summary_logger)
        self.llm = None
        self.summary_chain = None
        self._chain_lock = threading.Lock()
        self._initialized = True
        summary_logger.info("SummaryGenerator initialization completed")

    def _get_llm(self):
        if self.llm is None:
            self.llm = self.model_provider.get_language_model()
        return self.llm

    def _initialize_summary_chain(self):
        if self.summary_chain is not None:
            summary_logger.info(
                "Summary chain initialization skipped: already initialized"
            )
            return

        with self._chain_lock:
            if self.summary_chain is not None:
                summary_logger.info(
                    "Summary chain initialization skipped inside lock: already initialized"
                )
                return

            summary_logger.info("Initializing summary generation chain")
            prompt_template = config.summary_prompt_template.format(
                candidate_name=config.candidate.name
            )
            prompt = PromptTemplate.from_template(prompt_template)
            self.summary_chain = create_stuff_documents_chain(
                llm=self._get_llm(), prompt=prompt
            )
            summary_logger.info("Summary chain initialization completed")

    @langsmith_traceable(
        run_type="llm",
        name="Summary Generation",
        tags=["summary", "generation"],
        metadata={},
    )
    def generate_summary(
        self, style: str = "bullet", user_metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        summary_logger.info(f"Starting summary generation with style: {style}")
        if not is_llm_configured():
            raise LLMNotConfigured("尚未配置大模型 API Key")

        self._initialize_summary_chain()

        current_run = get_current_run_tree()
        if current_run and user_metadata:
            current_run.metadata["user_metadata"] = user_metadata
            current_run.metadata["summary_style"] = style

        try:
            handler = DocumentHandler(config, summary_logger)
            documents = handler.load_documents()
            if not documents:
                return {
                    "summary_md": "暂无可摘要的资料。请先放入简历 PDF 或完善 data/about_me.md。",
                    "skills": [],
                    "style": style,
                }

            result = self.summary_chain.invoke({"context": documents})
            summary_logger.info(
                f"Summary generated successfully, length: {len(result)} characters, documents used: {len(documents)}"
            )

            return {
                "summary_md": result,
                "skills": [],
                "style": style,
                "timestamp": str(current_run.start_time) if current_run else None,
            }

        except LLMNotConfigured:
            raise
        except Exception as e:
            summary_logger.error(
                f"Summary generation failed ({e.__class__.__name__}): {e!s}"
            )
            return {
                "summary_md": "暂时无法生成摘要，请稍后重试。",
                "skills": [],
                "error": str(e),
            }


def get_summary_generator() -> SummaryGenerator:
    return SummaryGenerator()


def get_auto_summary(
    style: str = "bullet", user_metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    generator = get_summary_generator()
    return generator.generate_summary(style, user_metadata)


def get_llm_model() -> Any:
    generator = get_summary_generator()
    return generator.model_provider.get_language_model()


def get_embedding_model() -> Any:
    generator = get_summary_generator()
    return generator.model_provider.get_embedding_model()


def init_summary_chain(user_metadata: dict[str, Any] | None = None) -> None:
    generator = get_summary_generator()
    generator._initialize_summary_chain()
