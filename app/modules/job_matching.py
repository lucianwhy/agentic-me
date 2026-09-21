"""
Job Description Matching Pipeline for ChatCV

LangSmith is optional. The LLM is created on first use so importing this
module never requires an API key.
"""

import threading
from typing import Any

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.config import config
from app.modules.guardrails import InputValidator
from app.modules.langchain_compat import create_stuff_documents_chain
from app.modules.model_provider import ModelProvider
from app.modules.readiness import LLMNotConfigured, is_llm_configured
from app.modules.vectorstore_provider import DocumentHandler, VectorStoreManager
from app.utils.logging_config import job_matching_logger

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


class JobMatchingAnalyzer:
    """Performs job matching analysis using RAG pipeline"""

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

        job_matching_logger.info("Initializing JobMatchingAnalyzer singleton instance")
        self.model_provider = ModelProvider(config, job_matching_logger)
        self.llm = None
        self.validator = InputValidator(config, job_matching_logger)
        self.vectorstore_manager = VectorStoreManager(
            config, self.model_provider, job_matching_logger
        )
        self.matching_chain = None
        self._chain_lock = threading.Lock()
        self._initialized = True
        job_matching_logger.info("JobMatchingAnalyzer initialization completed")

    def _get_llm(self):
        if self.llm is None:
            self.llm = self.model_provider.get_language_model()
        return self.llm

    def reset_model_cache(self) -> None:
        """Discard a chain that may have been built with old runtime settings."""
        with self._chain_lock:
            self.llm = None
            self.matching_chain = None

    def _initialize_matching_chain(self):
        if self.matching_chain is not None:
            job_matching_logger.debug(
                "Matching chain already initialized, skipping initialization"
            )
            return

        with self._chain_lock:
            if self.matching_chain is not None:
                job_matching_logger.debug(
                    "Matching chain already initialized inside lock, skipping initialization"
                )
                return

            job_matching_logger.info("Initializing job matching analysis chain")
            system_prompt = config.job_matching_system_prompt
            analysis_prompt = config.job_matching_analysis_prompt.format(
                candidate_name=config.candidate.name
            )
            full_prompt = f"{system_prompt}\n\n{analysis_prompt}"
            prompt = ChatPromptTemplate.from_template(full_prompt)
            self.matching_chain = create_stuff_documents_chain(self._get_llm(), prompt)
            job_matching_logger.info(
                "Job matching analysis chain initialization completed"
            )

    @langsmith_traceable(
        run_type="llm",
        name="Job Matching Analysis",
        tags=["job_matching", "assessment"],
        metadata={},
    )
    def analyze_job_match(
        self, job_description: Document, user_metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        job_matching_logger.info("Starting job matching analysis")
        if not is_llm_configured():
            raise LLMNotConfigured("尚未配置大模型 API Key")

        self._initialize_matching_chain()

        current_run = get_current_run_tree()
        if current_run and user_metadata:
            current_run.metadata["user_metadata"] = user_metadata
            current_run.metadata["job_source"] = job_description.metadata.get(
                "source", "unknown"
            )

        try:
            vectorstore = self.vectorstore_manager.get_vectorstore()
            retrieval_k = config.vectorstore.retrieval_k
            retriever = vectorstore.as_retriever(search_kwargs={"k": retrieval_k})
            relevant_docs = retriever.invoke(job_description.page_content)
            job_matching_logger.info(
                f"Retrieved {len(relevant_docs)} relevant documents from vectorstore"
            )

            job_doc = Document(
                page_content=f"JOB DESCRIPTION:\n{job_description.page_content}",
                metadata={"source": "job_description", "type": "job_requirements"},
            )

            job_matching_logger.info("Validating job description content")
            self.validator.validate_job_text(job_doc.page_content)
            job_matching_logger.info("Job description validation completed")

            all_docs = [job_doc] + relevant_docs
            job_matching_logger.info(
                f"Analyzing job match with {len(relevant_docs)} relevant CV sections"
            )
            analysis_result = self.matching_chain.invoke({"context": all_docs})
            job_matching_logger.info("Job matching analysis completed successfully")

            return {
                "analysis": analysis_result,
                "job_source": job_description.metadata.get("source", "unknown"),
                "match_timestamp": str(current_run.start_time) if current_run else None,
                "relevant_sections": [
                    doc.metadata.get("source", "unknown") for doc in relevant_docs
                ],
            }

        except LLMNotConfigured:
            raise
        except Exception as e:
            job_matching_logger.error(
                f"Job matching analysis error ({e.__class__.__name__}): {e!s}"
            )
            return {
                "analysis": "暂时无法完成岗位匹配分析，请稍后重试。",
                "error": str(e),
                "job_source": job_description.metadata.get("source", "unknown"),
            }


def get_job_analyzer() -> JobMatchingAnalyzer:
    return JobMatchingAnalyzer()


def process_job_description(text: str) -> Document:
    if not text:
        raise ValueError("Job description text is required")
    handler = DocumentHandler(config, job_matching_logger)
    return handler.process_text(text)


def analyze_job_match(
    job_description: Document, user_metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    analyzer = get_job_analyzer()
    return analyzer.analyze_job_match(job_description, user_metadata)
