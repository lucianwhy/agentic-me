"""
RAG Pipeline Implementation for ChatCV

Production-ready retrieval-augmented generation for interactive resume querying.
LangSmith is optional and never required to import or start the app.
"""

import threading
from typing import Any, Iterator

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
    is_vectorstore_ready,
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
        self.qa_chain = None
        self.history_aware_retriever = None
        self.document_chain = None
        self.chat_history = None
        self._chain_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._initialized = True
        rag_logger.info("ChatRAGPipeline instance setup complete")

    def _initialize_qa_chain(self):
        """Thread-safe initialization of the QA chain."""
        if self.qa_chain is not None:
            return

        with self._chain_lock:
            if self.qa_chain is not None:
                return

            rag_logger.info("Initializing RAG QA chain")

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

            language_model = self.model_provider.get_language_model()

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

            self.history_aware_retriever = history_aware_retriever
            self.document_chain = document_chain
            self.qa_chain = input_validator | base_qa_chain | output_validator
            rag_logger.info("RAG QA chain initialization completed")

    @langsmith_traceable(
        run_type="llm", name="Chat Completion", tags=["chatcv", "rag"], metadata={}
    )
    def get_completion(
        self, query: str, user_metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Process chat query and return response with conversation history."""
        rag_logger.info(f"Processing chat query, length: {len(query)}")

        if not is_llm_configured():
            raise LLMNotConfigured("尚未配置大模型 API Key")
        if not is_vectorstore_ready():
            # Allow a single auto-ingest attempt when a key is present.
            rag_logger.info("Vectorstore missing; attempting one-time ingest")

        self._initialize_qa_chain()

        current_run = get_current_run_tree()
        if current_run and user_metadata:
            current_run.metadata["user_metadata"] = user_metadata

        try:
            with self._history_lock:
                if self.chat_history is None:
                    self.chat_history = []
                self.chat_history.append(HumanMessage(content=query))
                current_history = self.chat_history.copy()

            result = self.qa_chain.invoke(
                {"input": query, "chat_history": current_history}
            )

            with self._history_lock:
                self.chat_history.append(AIMessage(content=result["answer"]))

            rag_logger.info("Chat completion processed successfully")
            return {"answer": result, "sources": result.get("context", [])}

        except (LLMNotConfigured, VectorStoreNotReady):
            raise
        except ValueError as validation_error:
            rag_logger.warning(f"Query validation failed: {validation_error!s}")
            return {"answer": {"answer": str(validation_error)}, "sources": []}
        except Exception as unexpected_error:
            rag_logger.error(
                f"Unexpected error in chat completion ({type(unexpected_error).__name__}): {unexpected_error!s}"
            )
            formatted_fallback = self.config.chat_fallback_response.format(
                candidate_name=self.config.candidate.name
            )
            return {
                "answer": {"answer": formatted_fallback},
                "sources": [],
            }


    def stream_completion(
        self, query: str, user_metadata: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        """
        Stream final answer tokens over SSE-friendly event dicts.

        Wire protocol (formatted as SSE in the API layer):
          data: {"type":"token","content":"..."}
          data: {"type":"done"}
          data: {"type":"error","message":"..."}

        Practical RAG streaming path:
          1) Validate input + history-aware retrieval (non-stream)
          2) Stream only the stuff-documents / answer LLM via .stream()
        """
        rag_logger.info(f"Streaming chat query, length: {len(query)}")

        if not is_llm_configured():
            raise LLMNotConfigured("尚未配置大模型 API Key")
        if not is_vectorstore_ready():
            rag_logger.info("Vectorstore missing; attempting one-time ingest")

        self._initialize_qa_chain()

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

        human_appended = False
        try:
            with self._history_lock:
                if self.chat_history is None:
                    self.chat_history = []
                self.chat_history.append(HumanMessage(content=validated_query))
                human_appended = True
                current_history = self.chat_history.copy()

            # Step 1: retrieval (+ optional history rewrite) — blocking
            docs = self.history_aware_retriever.invoke(
                {"input": validated_query, "chat_history": current_history}
            )

            # Step 2: stream answer LLM only
            accumulated: list[str] = []
            for chunk in self.document_chain.stream(
                {
                    "input": validated_query,
                    "chat_history": current_history,
                    "context": docs,
                }
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

            full_answer = "".join(accumulated)
            validated_answer = self.query_validator.validate_response_output(
                full_answer
            )
            # Guardrails may rewrite the stored answer; client already saw streamed text.
            with self._history_lock:
                self.chat_history.append(AIMessage(content=validated_answer))

            rag_logger.info("Streaming chat completion finished successfully")
            yield {"type": "done", "sources": docs if isinstance(docs, list) else []}

        except (LLMNotConfigured, VectorStoreNotReady):
            if human_appended:
                with self._history_lock:
                    if (
                        self.chat_history
                        and isinstance(self.chat_history[-1], HumanMessage)
                        and self.chat_history[-1].content == validated_query
                    ):
                        self.chat_history.pop()
            raise
        except Exception as unexpected_error:
            rag_logger.error(
                f"Unexpected error in streaming chat ({type(unexpected_error).__name__}): {unexpected_error!s}"
            )
            if human_appended:
                with self._history_lock:
                    if (
                        self.chat_history
                        and isinstance(self.chat_history[-1], HumanMessage)
                        and self.chat_history[-1].content == validated_query
                    ):
                        self.chat_history.pop()
            formatted_fallback = self.config.chat_fallback_response.format(
                candidate_name=self.config.candidate.name
            )
            yield {"type": "error", "message": formatted_fallback}


def get_chat_pipeline() -> ChatRAGPipeline:
    rag_logger.info("get_chat_pipeline invoked")
    return ChatRAGPipeline()


def get_chat_completion(
    query: str, user_metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    rag_logger.info("get_chat_completion invoked")
    pipeline = get_chat_pipeline()
    return pipeline.get_completion(query, user_metadata)


def get_chat_stream(
    query: str, user_metadata: dict[str, Any] | None = None
) -> Iterator[dict[str, Any]]:
    rag_logger.info("get_chat_stream invoked")
    pipeline = get_chat_pipeline()
    return pipeline.stream_completion(query, user_metadata)


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
