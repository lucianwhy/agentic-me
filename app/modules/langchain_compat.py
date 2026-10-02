"""Import shim for LangChain 0.3 (langchain.chains) and 1.x (langchain_classic)."""

from __future__ import annotations

try:
    from langchain.chains.combine_documents import create_stuff_documents_chain
except ImportError:  # LangChain 1.x moved this to langchain-classic
    from langchain_classic.chains.combine_documents import (  # type: ignore
        create_stuff_documents_chain,
    )

__all__ = ["create_stuff_documents_chain"]
