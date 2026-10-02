"""
RAG Pipeline Implementation for ChatCV

Production-ready retrieval-augmented generation for interactive resume querying.
LangSmith is optional and never required to import or start the app.
"""

import threading
from collections.abc import Iterator
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import config
from app.model_registry import get_model_registry
from app.modules.guardrails import QueryValidator
from app.modules.langchain_compat import create_stuff_documents_chain
from app.modules.model_provider import ModelProvider
from app.modules.readiness import (
    LLMNotConfigured,
    VectorStoreNotReady,
    is_llm_configured,
)
from app.modules.vectorstore_provider import DocumentHandler, VectorStoreManager
from app.utils.logging_config import rag_logger

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


def history_to_messages(
    history: list[dict[str, Any]] | None, max_messages: int = 6, max_chars: int = 1500
) -> list[HumanMessage | AIMessage]:
    """Sanitize client-sent history ([{role, content}]) into LangChain messages.

    The server keeps no conversation state: each visitor's browser sends its own recent
    turns, so conversations never leak between visitors and prompts stay bounded.
    """
    messages: list[HumanMessage | AIMessage] = []
    for item in (history or [])[-max(0, max_messages):]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        content = content.strip()[:max_chars]
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


class ChatRAGPipeline:
    """Main RAG pipeline for ChatCV with thread-safe singleton pattern."""

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

        rag_logger.info("Initializing ChatRAGPipeline singleton instance")
        self.config = config
        self.model_provider = ModelProvider(self.config, rag_logger)
        self.vectorstore_manager = VectorStoreManager(
            self.config, self.model_provider, rag_logger
        )
        self.document_manager = DocumentHandler(self.config, rag_logger)
        self.query_validator = QueryValidator(self.config, rag_logger)
        # Answer chains per (model, reasoning effort): the switcher never reuses the wrong LLM.
        self._document_chains: dict[str, Any] = {}
        self.base_retriever = None
        self._chain_lock = threading.Lock()
        self._initialized = True
        rag_logger.info("ChatRAGPipeline instance setup complete")

    def _model_settings(self, model: str | None) -> tuple[str, str | None]:
        """(model id, per-model reasoning effort or None for the global setting)."""
        name = (model or "").strip() or get_model_registry().default()
        entry = get_model_registry().get(name)
        return name, (entry or {}).get("reasoning_effort")

    def reset_model_caches(self) -> None:
        """Discard LLM chains after a runtime model configuration update."""
        with self._chain_lock:
            self._document_chains.clear()

    def _initialize_qa_chain(self, model: str | None = None) -> Any:
        """Return the (cached) answer chain for a model. Thread-safe.

        Keyed by model *and* reasoning effort, so an admin change to a model's effort
        takes effect on the next request without a restart.
        """
        name, effort = self._model_settings(model)
        key = f"{name}|{effort or ''}"
        chain = self._document_chains.get(key)
        if chain is not None:
            return chain
        with self._chain_lock:
            chain = self._document_chains.get(key)
            if chain is not None:
                return chain
            rag_logger.info(f"Initializing RAG answer chain for model={name} effort={effort or 'global'}")
            if self.base_retriever is None:
                base_retriever = self.vectorstore_manager.get_vectorstore().as_retriever()
                base_retriever.search_kwargs["k"] = self.config.vectorstore.retrieval_k or 8
                self.base_retriever = base_retriever
            language_model = self.model_provider.get_language_model(
                model=name, reasoning_effort=effort
            )
            system_prompt = self.config.chat_system_prompt.format(
                candidate_name=self.config.candidate.name
            )
            # Recent turns go to the answer model, which resolves follow-ups itself.
            response_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{input}"),
                ]
            )
            chain = create_stuff_documents_chain(language_model, response_prompt)
            self._document_chains[key] = chain
            return chain

    def _history(self, history: list[dict[str, Any]] | None) -> list[HumanMessage | AIMessage]:
        return history_to_messages(
            history,
            max_messages=self.config.chat.max_history_messages,
            max_chars=self.config.chat.max_history_chars,
        )

    def _retrieve(self, query: str) -> list[Any]:
        """Retrieve context with the user's question as-is (no rewriting)."""
        return self.base_retriever.invoke(query)

    def _fallback_text(self) -> str:
        return self.config.chat_fallback_response.format(candidate_name=self.config.candidate.name)

    @langsmith_traceable(
        run_type="llm", name="Chat Completion", tags=["chatcv", "rag"], metadata={}
    )
    def get_completion(
        self,
        query: str,
        user_metadata: dict[str, Any] | None = None,
        model: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Answer one question (non-streaming). `history` is the client's recent turns."""
        rag_logger.info(f"Processing chat query, length: {len(query)}")

        if not is_llm_configured():
            raise LLMNotConfigured("尚未配置大模型 API Key")

        document_chain = self._initialize_qa_chain(model)

        current_run = get_current_run_tree()
        if current_run and user_metadata:
            current_run.metadata["user_metadata"] = user_metadata

        try:
            validated_query = self.query_validator.validate_query_input(query)
            messages = self._history(history)
            docs = self._retrieve(validated_query)
            answer = document_chain.invoke(
                {"input": validated_query, "chat_history": messages, "context": docs}
            )
            text = answer if isinstance(answer, str) else str(answer)
            text = self.query_validator.validate_response_output(text)
            rag_logger.info("Chat completion processed successfully")
            return {"answer": {"answer": text, "context": docs}, "sources": docs}

        except (LLMNotConfigured, VectorStoreNotReady):
            raise
        except ValueError as validation_error:
            rag_logger.warning(f"Query validation failed: {validation_error!s}")
            return {"answer": {"answer": str(validation_error)}, "sources": []}
        except Exception as unexpected_error:
            rag_logger.error(
                f"Unexpected error in chat completion ({type(unexpected_error).__name__}): {unexpected_error!s}"
            )
            return {"answer": {"answer": self._fallback_text()}, "sources": []}

    def stream_completion(
        self,
        query: str,
        user_metadata: dict[str, Any] | None = None,
        model: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """
        Stream final answer tokens over SSE-friendly event dicts.

        Wire protocol (formatted as SSE in the API layer):
          data: {"type":"status","stage":"retrieving"|"generating", ...}
          data: {"type":"token","content":"..."}
          data: {"type":"done","sources":[...]}
          data: {"type":"error","message":"..."}

        1) retrieval (embedding + Chroma) with the raw question; history goes to the answer LLM
        2) stream the answer LLM via .stream()
        """
        rag_logger.info(f"Streaming chat query, length: {len(query)}")

        if not is_llm_configured():
            raise LLMNotConfigured("尚未配置大模型 API Key")

        # Tell the client immediately, before any setup work.
        yield {"type": "status", "stage": "retrieving"}

        document_chain = self._initialize_qa_chain(model)

        current_run = get_current_run_tree()
        if current_run and user_metadata:
            current_run.metadata["user_metadata"] = user_metadata

        try:
            validated_query = self.query_validator.validate_query_input(query)
        except ValueError as validation_error:
            rag_logger.warning(f"Query validation failed: {validation_error!s}")
            yield {"type": "token", "content": str(validation_error)}
            yield {"type": "done", "sources": []}
            return

        try:
            messages = self._history(history)
            docs = self._retrieve(validated_query)
            yield {
                "type": "status",
                "stage": "generating",
                "source_count": len(docs) if isinstance(docs, list) else 0,
            }

            accumulated: list[str] = []
            for chunk in document_chain.stream(
                {"input": validated_query, "chat_history": messages, "context": docs}
            ):
                if chunk is None:
                    continue
                if isinstance(chunk, dict):
                    piece = chunk.get("answer") or chunk.get("content") or ""
                else:
                    piece = chunk
                text = piece if isinstance(piece, str) else str(piece)
                if not text:
                    continue
                accumulated.append(text)
                yield {"type": "token", "content": text}

            # Guardrail check on the full answer (the client already saw the streamed text).
            self.query_validator.validate_response_output("".join(accumulated))
            rag_logger.info("Streaming chat completion finished successfully")
            yield {"type": "done", "sources": docs if isinstance(docs, list) else []}

        except (LLMNotConfigured, VectorStoreNotReady):
            raise
        except Exception as unexpected_error:
            rag_logger.error(
                f"Unexpected error in streaming chat ({type(unexpected_error).__name__}): {unexpected_error!s}"
            )
            yield {"type": "error", "message": self._fallback_text()}

    def warmup(self) -> None:
        """Load the vector store / chains and open API connections (no LLM tokens spent)."""
        import time

        started = time.perf_counter()
        self._initialize_qa_chain()
        embeddings = self.model_provider.get_embedding_model()
        if hasattr(embeddings, "warmup"):
            embeddings.warmup()
        base_url = (self.config.resolved_base_url() or "").rstrip("/")
        api_key = self.config.resolved_api_key()
        if base_url and api_key:
            from app.modules.model_provider import shared_llm_http_client

            try:  # opens the keep-alive TLS connection to the chat API; GET /models is free
                shared_llm_http_client().get(
                    f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10
                )
            except Exception as exc:  # warm-up is best effort
                rag_logger.info(f"LLM connection warm-up skipped: {type(exc).__name__}")
        rag_logger.info(f"Pipeline warm-up finished in {time.perf_counter() - started:.2f}s")


def get_chat_pipeline() -> ChatRAGPipeline:
    rag_logger.info("get_chat_pipeline invoked")
    return ChatRAGPipeline()


def get_chat_completion(
    query: str,
    user_metadata: dict[str, Any] | None = None,
    model: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rag_logger.info("get_chat_completion invoked")
    pipeline = get_chat_pipeline()
    return pipeline.get_completion(query, user_metadata, model=model, history=history)


def get_chat_stream(
    query: str,
    user_metadata: dict[str, Any] | None = None,
    model: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    rag_logger.info("get_chat_stream invoked")
    pipeline = get_chat_pipeline()
    return pipeline.stream_completion(query, user_metadata, model=model, history=history)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="ChatCV RAG Pipeline Management")
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Initialize vector database with document ingestion",
    )
    args = parser.parse_args()

    if args.ingest:
        if not is_llm_configured():
            rag_logger.error("无法构建向量库：尚未配置 OPENAI_API_KEY（或 Ollama）。")
            sys.exit(1)
        rag_logger.info("Initializing vector database...")
        pipeline = get_chat_pipeline()
        pipeline.vectorstore_manager.setup_vectorstore()
        rag_logger.info("Vector database initialization complete.")
    else:
        rag_logger.info(
            "No action specified. Use --ingest to build the vector database."
        )
