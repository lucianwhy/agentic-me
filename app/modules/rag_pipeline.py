"""
RAG Pipeline Implementation for ChatCV

Production-ready retrieval-augmented generation for interactive resume querying.
LangSmith is optional and never required to import or start the app.
"""

import threading
from collections.abc import Iterator
from typing import Any

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

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


# Inline citations: context chunks are numbered [1]..[n] in the order they are retrieved,
# which is also the order of `sources` in the /chat done event, so the frontend can map
# a marker [n] to sources[n-1]. Kept free of braces (it is part of a prompt template).
CITATION_INSTRUCTIONS = """

引用规则（资料已按 [1]、[2]… 编号）：
- 只给具体的事实陈述标注来源：经历、职责、做法、数据与成果。编号写在句末标点之前，例如：设计了 7-Agent 编排体系[2]。
- 用能直接支撑该句的最少资料：通常只标 1 个编号，最多 2 个；拿不准是否支撑就不标。
- 以下内容一律不标编号：说明资料缺失或不确定的句子（如「简历里没有写到…」「未说明…」「资料不足」）；标题、小标题、只有标签的行；只是罗列名词的清单行（如「技术栈：A、B、C」）；开场、过渡、总结和评价性的句子；问句。
- 一句话里既有事实又有「没有写到」时，拆成两句，只给事实那句标注。
- 正确：负责模拟直播评分链路，覆盖 4 类分析维度[1]。简历里没有写到评分准确率。
- 错误：简历里没有写到团队人数[2]。／技术栈：FastAPI、LangGraph[1][2][4]。／总体来看，他工程能力扎实[1]。
- 不要在文末另列参考文献，也不要提及「资料编号」或「检索」，保持回答自然。"""

CITATION_DOCUMENT_PROMPT = PromptTemplate.from_template("[{cite}] {page_content}")

# langchain-openai 1.6+ drops third-party `reasoning_content` on Chat Completions
# deltas, but glm-5.3-flash (and similar) may still surface thinking as list
# blocks or additional_kwargs. Answer tokens are `content` text only.
_NON_ANSWER_BLOCK_TYPES = frozenset(
    {"reasoning", "thinking", "reasoning_content", "thought", "reasoning_details"}
)


def answer_text_from_chunk(chunk: Any) -> str:
    """Visible answer text from a stream/invoke chunk. Never reasoning/thinking."""
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        if "answer" in chunk:
            return answer_text_from_chunk(chunk.get("answer"))
        if "content" in chunk:
            return _text_from_content(chunk.get("content"))
        return ""
    content = getattr(chunk, "content", None)
    if content is None and not hasattr(chunk, "content"):
        return ""
    return _text_from_content(content)


def _text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "").lower()
        if btype in _NON_ANSWER_BLOCK_TYPES:
            continue
        if btype in ("text", "output_text", "") or "text" in block:
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
            elif isinstance(text, dict) and isinstance(text.get("value"), str):
                parts.append(text["value"])
    return "".join(parts)


def number_documents(docs: list[Any]) -> list[Document]:
    """Copies of the retrieved docs tagged with their 1-based citation number (metadata 'cite').

    The originals are left untouched; they are what the done event serializes as sources.
    """
    numbered: list[Document] = []
    for i, doc in enumerate(docs or [], start=1):
        content = getattr(doc, "page_content", None)
        if content is None:
            content = str(doc)
        metadata = dict(getattr(doc, "metadata", None) or {})
        metadata["cite"] = i
        numbered.append(Document(page_content=content, metadata=metadata))
    return numbered


def build_chat_system_prompt(template: str, candidate_name: str) -> str:
    """The configured chat system prompt plus the inline-citation rules."""
    return template.format(candidate_name=candidate_name).rstrip() + CITATION_INSTRUCTIONS


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

    def _model_settings(self, model: str | None) -> dict[str, Any]:
        """Registry entry for the requested model (id + per-model endpoint fields)."""
        name = (model or "").strip() or get_model_registry().default()
        entry = get_model_registry().get(name)
        if entry:
            return entry
        return {
            "id": name,
            "reasoning_effort": None,
            "base_url": None,
            "api_key_env": None,
            "thinking": None,
        }

    def reset_model_caches(self) -> None:
        """Discard LLM chains after a runtime model configuration update."""
        with self._chain_lock:
            self._document_chains.clear()

    def _initialize_qa_chain(self, model: str | None = None) -> Any:
        """Return the (cached) answer chain for a model. Thread-safe.

        Keyed by model, reasoning effort, and per-model endpoint fields, so an admin
        change takes effect on the next request without a restart.
        """
        entry = self._model_settings(model)
        name = entry.get("id") or ""
        effort = entry.get("reasoning_effort")
        key = "|".join(
            [
                str(name),
                str(effort or ""),
                str(entry.get("base_url") or ""),
                str(entry.get("api_key_env") or ""),
                str(entry.get("thinking") or ""),
            ]
        )
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
                model=name,
                reasoning_effort=effort,
                base_url=entry.get("base_url"),
                api_key_env=entry.get("api_key_env"),
                thinking=entry.get("thinking"),
            )
            system_prompt = build_chat_system_prompt(
                self.config.chat_system_prompt, self.config.candidate.name
            )
            # Recent turns go to the answer model, which resolves follow-ups itself.
            response_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{input}"),
                ]
            )
            chain = create_stuff_documents_chain(
                language_model,
                response_prompt,
                document_prompt=CITATION_DOCUMENT_PROMPT,
            )
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
                {"input": validated_query, "chat_history": messages, "context": number_documents(docs)}
            )
            text = answer_text_from_chunk(answer)
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
                {"input": validated_query, "chat_history": messages, "context": number_documents(docs)}
            ):
                text = answer_text_from_chunk(chunk)
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
        try:  # parse CV / about_me once so mapping sources to resume cards is instant
            from app.modules.resume_links import source_documents

            source_documents()
        except Exception as exc:  # best effort
            rag_logger.info(f"Resume link warm-up skipped: {type(exc).__name__}")
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
