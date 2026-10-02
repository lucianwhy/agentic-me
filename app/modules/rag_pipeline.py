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
from langchain_core.runnables import RunnableLambda

from app.config import config
from app.modules.guardrails import QueryValidator
from app.modules.langchain_compat import (
    create_history_aware_retriever,
    create_retrieval_chain,
    create_stuff_documents_chain,
)
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

# Whitelist for per-request model override (Sol / Luna / Terra).
ALLOWED_CHAT_MODELS = (
    "gpt-5.6-sol",
    "gpt-5.6-luna",
    "gpt-5.6-terra",
)


def normalize_chat_model(model: str | None) -> str | None:
    """Return a whitelisted model id, or None to use the env default."""
    if model is None:
        return None
    name = str(model).strip()
    if not name:
        return None
    if name not in ALLOWED_CHAT_MODELS:
        raise ValueError(
            f"不支持的模型：{name}。可选：{', '.join(ALLOWED_CHAT_MODELS)}"
        )
    return name


# Words that mark a question as a follow-up to the previous turn (for the cheap rewrite).
# "他/她" are deliberately absent: they usually mean the candidate, not the last answer.
FOLLOW_UP_MARKERS = (
    "这个", "那个", "这些", "那些", "这段", "这里", "该项目", "上面", "刚才", "前面",
    "上一个", "具体", "详细", "展开", "还有", "其他", "其它", "另外", "呢", "为什么",
    "怎么实现", "然后",
)


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


def build_retrieval_query(query: str, history: list[HumanMessage | AIMessage]) -> str:
    """Cheap, LLM-free retrieval query for follow-ups.

    A short or clearly referential question ("那这个项目呢？") is prefixed with the
    previous user question so retrieval still finds the right chunks.
    """
    last_user = next((m.content for m in reversed(history) if isinstance(m, HumanMessage)), "")
    if not last_user:
        return query
    if len(query) <= 8 or any(marker in query for marker in FOLLOW_UP_MARKERS):
        return f"{str(last_user)[:200]}\n{query}"
    return query


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
        # Per-model caches so Sol/Luna switcher does not reuse the wrong LLM.
        self._qa_chains: dict[str, Any] = {}
        self._history_aware_retrievers: dict[str, Any] = {}
        self._document_chains: dict[str, Any] = {}
        self.qa_chain = None  # legacy alias: last-used default chain
        self.history_aware_retriever = None
        self.document_chain = None
        self.base_retriever = None
        self._chain_lock = threading.Lock()
        self._initialized = True
        rag_logger.info("ChatRAGPipeline instance setup complete")

    def _model_key(self, model: str | None = None) -> str:
        """Stable cache key for a chat model (env default when unset)."""
        return (model or "").strip() or self.config.llm.model

    def reset_model_caches(self) -> None:
        """Discard LLM chains after a runtime model configuration update."""
        with self._chain_lock:
            self._qa_chains.clear()
            self._history_aware_retrievers.clear()
            self._document_chains.clear()
            self.qa_chain = None
            self.history_aware_retriever = None
            self.document_chain = None

    def _initialize_qa_chain(self, model: str | None = None):
        """Thread-safe initialization of the QA chain for a given model."""
        key = self._model_key(model)
        if key in self._qa_chains:
            self.qa_chain = self._qa_chains[key]
            self.history_aware_retriever = self._history_aware_retrievers[key]
            self.document_chain = self._document_chains[key]
            return

        with self._chain_lock:
            if key in self._qa_chains:
                self.qa_chain = self._qa_chains[key]
                self.history_aware_retriever = self._history_aware_retrievers[key]
                self.document_chain = self._document_chains[key]
                return

            rag_logger.info(f"Initializing RAG QA chain for model={key}")

            history_instruction = getattr(
                self.config,
                "conversation_history_prompt",
                "结合以上对话，生成一条用于检索相关背景资料的搜索查询。",
            ).format(candidate_name=self.config.candidate.name)

            retriever_prompt = ChatPromptTemplate.from_messages(
                [
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{input}"),
                    ("human", history_instruction),
                ]
            )
            vector_database = self.vectorstore_manager.get_vectorstore()
            base_retriever = vector_database.as_retriever()
            base_retriever.search_kwargs["k"] = self.config.vectorstore.retrieval_k or 8
            self.base_retriever = base_retriever

            language_model = self.model_provider.get_language_model(model=key)

            history_aware_retriever = create_history_aware_retriever(
                llm=language_model, retriever=base_retriever, prompt=retriever_prompt
            )

            system_prompt = self.config.chat_system_prompt.format(
                candidate_name=self.config.candidate.name
            )

            response_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{input}"),
                ]
            )

            document_chain = create_stuff_documents_chain(
                language_model, response_prompt
            )
            base_qa_chain = create_retrieval_chain(
                history_aware_retriever, document_chain
            )

            input_validator = RunnableLambda(
                lambda x: {
                    **x,
                    "input": self.query_validator.validate_query_input(x["input"]),
                }
            )
            output_validator = RunnableLambda(
                lambda x: {
                    **x,
                    "answer": self.query_validator.validate_response_output(
                        x["answer"]
                    ),
                }
            )

            qa_chain = input_validator | base_qa_chain | output_validator
            self._history_aware_retrievers[key] = history_aware_retriever
            self._document_chains[key] = document_chain
            self._qa_chains[key] = qa_chain
            self.history_aware_retriever = history_aware_retriever
            self.document_chain = document_chain
            self.qa_chain = qa_chain
            rag_logger.info(f"RAG QA chain initialization completed for model={key}")

    def _history(self, history: list[dict[str, Any]] | None) -> list[HumanMessage | AIMessage]:
        return history_to_messages(
            history,
            max_messages=self.config.chat.max_history_messages,
            max_chars=self.config.chat.max_history_chars,
        )

    def _chains(self, model: str | None) -> tuple[Any, Any]:
        """(history_aware_retriever, document_chain) for this request's model.

        Looked up per request instead of via the shared `self.*` aliases, so concurrent
        requests for different models (Sol / Luna switcher) never swap chains.
        """
        self._initialize_qa_chain(model=model)
        key = self._model_key(model)
        return self._history_aware_retrievers[key], self._document_chains[key]

    def _retrieve(
        self, query: str, history: list[HumanMessage | AIMessage], rewriter: Any = None
    ) -> list[Any]:
        """Retrieve context docs; the LLM rewrite runs only in `llm` mode with history."""
        mode = (self.config.chat.query_rewrite or "heuristic").lower()
        if mode == "llm" and history and rewriter is not None:
            return rewriter.invoke(
                {"input": query, "chat_history": [*history, HumanMessage(content=query)]}
            )
        retrieval_query = build_retrieval_query(query, history) if mode == "heuristic" else query
        return self.base_retriever.invoke(retrieval_query)

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

        rewriter, document_chain = self._chains(model)

        current_run = get_current_run_tree()
        if current_run and user_metadata:
            current_run.metadata["user_metadata"] = user_metadata

        try:
            validated_query = self.query_validator.validate_query_input(query)
            messages = self._history(history)
            docs = self._retrieve(validated_query, messages, rewriter)
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

        1) retrieval (embedding + Chroma; LLM rewrite only in `llm` mode with history)
        2) stream the answer LLM via .stream()
        """
        rag_logger.info(f"Streaming chat query, length: {len(query)}")

        if not is_llm_configured():
            raise LLMNotConfigured("尚未配置大模型 API Key")

        # Tell the client immediately, before any setup work.
        yield {"type": "status", "stage": "retrieving"}

        rewriter, document_chain = self._chains(model)

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
            docs = self._retrieve(validated_query, messages, rewriter)
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
