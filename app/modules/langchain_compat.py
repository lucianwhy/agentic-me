"""Import shims for LangChain 0.3 (langchain.chains) and 1.x (langchain_classic)."""

from __future__ import annotations

try:
    from langchain.chains import create_retrieval_chain
    from langchain.chains.combine_documents import create_stuff_documents_chain
    from langchain.chains.history_aware_retriever import create_history_aware_retriever
except ImportError:  # LangChain 1.x moved these to langchain-classic
    from langchain_classic.chains.combine_documents import (  # type: ignore
        create_stuff_documents_chain,
    )
    from langchain_classic.chains.history_aware_retriever import (  # type: ignore
        create_history_aware_retriever,
    )
    from langchain_classic.chains.retrieval import (
        create_retrieval_chain,  # type: ignore
    )

__all__ = [
    "create_history_aware_retriever",
    "create_retrieval_chain",
    "create_stuff_documents_chain",
]
