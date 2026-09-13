import logging
import os
import re

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import AppConfig
from app.modules.guardrails import InputValidator
from app.modules.model_provider import ModelProvider
from app.modules.readiness import (
    LLMNotConfigured,
    VectorStoreNotReady,
    is_vectorstore_ready,
)


class VectorStoreManager:
    """Manages vector database setup and retrieval."""

    def __init__(
        self,
        config: AppConfig,
        model_provider: ModelProvider | None,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.model_provider = model_provider or ModelProvider(config, logger)
        self.logger = logger

    def setup_vectorstore(self) -> Chroma:
        """
        Initialize and populate the vector database with resume documents.

        Loads CV and About Me documents, splits them into chunks, and creates a vector database.
        """
        self.logger.info("Setting up vectorstore with document ingestion")

        try:
            cv_loader = PyPDFLoader(self.config.data.cv_path)
            cv_documents = cv_loader.load()
            self.logger.info(f"Loaded {len(cv_documents)} CV documents")
            for doc in cv_documents:
                doc.metadata["source"] = "cv"
        except Exception as e:
            self.logger.error(f"Failed to load CV documents: {e}")
            cv_documents = []

        try:
            about_loader = TextLoader(self.config.data.about_me_path, encoding="utf-8")
            about_documents = about_loader.load()
            self.logger.info(f"Loaded {len(about_documents)} About Me documents")
            for doc in about_documents:
                doc.metadata["source"] = "about_me"
        except Exception as e:
            self.logger.error(f"Failed to load About Me documents: {e}")
            about_documents = []

        all_documents = cv_documents + about_documents
        self.logger.info(f"Total documents before splitting: {len(all_documents)}")

        if not all_documents:
            raise VectorStoreNotReady(
                "没有可入库的文档。请将简历 PDF 放到 data/ 并完善 data/about_me.md。"
            )

        chunk_size = self.config.embedding.chunk_size or 1000
        chunk_overlap = self.config.embedding.chunk_overlap or 200
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        document_chunks = text_splitter.split_documents(all_documents)
        self.logger.info(
            f"Total document chunks after splitting: {len(document_chunks)}"
        )
        if not document_chunks:
            raise VectorStoreNotReady(
                "文档已加载但无法切分，请检查简历与 about_me.md 内容。"
            )

        embedding_function = self.model_provider.get_embedding_model()
        persist_dir = self.config.data.vector_db_path
        os.makedirs(persist_dir, exist_ok=True)
        vector_database = Chroma.from_documents(
            document_chunks,
            embedding_function,
            persist_directory=persist_dir,
            collection_name=self.config.vectorstore.collection_name,
        )

        self.logger.info(
            f"Vectorstore initialized with {len(document_chunks)} document chunks"
        )
        return vector_database

    def get_vectorstore(self) -> Chroma:
        """Retrieve existing vector database or create a new one if possible."""
        vector_db_path = self.config.data.vector_db_path

        if is_vectorstore_ready():
            self.logger.info(f"Loading existing vector database from {vector_db_path}")
            embedding_function = self.model_provider.get_embedding_model()
            return Chroma(
                persist_directory=vector_db_path,
                embedding_function=embedding_function,
                collection_name=self.config.vectorstore.collection_name,
            )

        self.logger.warning(f"Vector database not found or empty at {vector_db_path}.")
        try:
            return self.setup_vectorstore()
        except LLMNotConfigured:
            raise VectorStoreNotReady(
                "向量库尚未就绪，且未配置 Embedding API，无法自动构建。"
            )

    def _is_vectorstore_populated(self, vector_db_path: str) -> bool:
        """Compatibility helper used by older call sites / tests."""
        return is_vectorstore_ready()


class DocumentHandler:
    """Handles document content extraction and text processing."""

    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.validator = InputValidator(config, logger)

    def get_cv_content(self) -> str:
        """Extract complete CV content as a single concatenated string."""
        try:
            cv_loader = PyPDFLoader(self.config.data.cv_path)
            cv_documents = cv_loader.load()
            self.logger.info(f"Loaded {len(cv_documents)} CV document pages")
        except Exception as e:
            self.logger.error(f"Failed to load CV document: {e}")
            return ""

        cv_content = [doc.page_content for doc in cv_documents if doc.page_content]

        if not cv_content:
            self.logger.warning("CV document appears to be empty or unreadable.")

        return " ".join(cv_content)

    def process_text(self, text: str) -> Document:
        """Process plain text job description into a Document object."""
        min_length = self.config.security.min_job_text_length

        if not text or len(text.strip()) < min_length:
            error_msg = f"Job description text must be at least {min_length} characters"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        self.validator.validate_job_text(text)

        cleaned_text = re.sub(r"\s+", " ", text.strip())

        self.logger.info(f"Processed job description text, length: {len(cleaned_text)}")
        self.logger.debug("Job description metadata source: text_input")

        return Document(
            page_content=cleaned_text,
            metadata={"source": "text_input", "type": "job_description"},
        )

    def load_documents(self) -> list[Document]:
        """Load and prepare CV and About Me documents for summarization."""
        self.logger.info("Loading documents for summary generation")

        try:
            cv_loader = PyPDFLoader(self.config.data.cv_path)
            docs_cv = cv_loader.load()
            self.logger.info(f"Loaded {len(docs_cv)} CV documents")
            for doc in docs_cv:
                doc.metadata["source"] = "cv"
        except Exception as e:
            self.logger.error(f"Failed to load CV documents: {e}")
            docs_cv = []

        docs_about = []
        about_me_path = self.config.data.about_me_path
        if os.path.exists(about_me_path):
            try:
                about_loader = TextLoader(about_me_path, encoding="utf-8")
                docs_about = about_loader.load()
                self.logger.info(f"Loaded {len(docs_about)} About Me documents")
                for doc in docs_about:
                    doc.metadata["source"] = "about_me"
            except Exception as e:
                self.logger.error(f"Failed to load About Me documents: {e}")
                docs_about = []
        else:
            self.logger.warning(f"About Me document not found at path: {about_me_path}")

        total_docs = len(docs_cv) + len(docs_about)
        self.logger.info(
            f"Loaded {total_docs} documents ({len(docs_cv)} CV, {len(docs_about)} about)"
        )

        return docs_cv + docs_about
