"""Retrieval-only demo for the "我的项目" page (POST /api/retrieve).

Embeds the query once and runs the same Chroma top-k search the chat pipeline
uses, but WITHOUT calling the LLM (no history rewrite, no generation). Scores
are exact cosine similarities computed from the stored embeddings, plus Chroma's
raw distance (squared L2), so nothing is estimated or invented.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Any

from app.config import config
from app.modules.model_provider import ModelProvider
from app.modules.vectorstore_provider import VectorStoreManager
from app.utils.logging_config import rag_logger

SOURCE_LABELS = {"cv": "简历 PDF", "about_me": "关于我"}
MAX_CHUNK_CHARS = 1200


class RetrievalRateLimiter:
    """Small in-memory per-client limiter (single process).

    Enforces a minimum gap between requests (`rate_limit_ms`) and a sliding
    one-minute cap (`requests_per_minute`), both from config.rate_limit.
    """

    def __init__(self, min_interval_ms: int, per_minute: int) -> None:
        self.min_interval = max(0, min_interval_ms) / 1000.0
        self.per_minute = max(1, per_minute)
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str, now: float | None = None) -> float:
        """Return 0 if allowed (and record the hit), else seconds to wait."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            while hits and now - hits[0] > 60:
                hits.popleft()
            if hits and now - hits[-1] < self.min_interval:
                return self.min_interval - (now - hits[-1])
            if len(hits) >= self.per_minute:
                return 60 - (now - hits[0])
            hits.append(now)
            if len(self._hits) > 5000:  # bound memory
                for key in [k for k, v in self._hits.items() if not v or now - v[-1] > 60]:
                    self._hits.pop(key, None)
            return 0.0


limiter = RetrievalRateLimiter(
    config.rate_limit.rate_limit_ms, config.rate_limit.requests_per_minute
)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def retrieve_with_scores(query: str) -> dict[str, Any]:
    """Top-k chunks for `query` with exact cosine similarity. No LLM call."""
    k = config.vectorstore.retrieval_k or 8
    t0 = time.perf_counter()
    manager = VectorStoreManager(config, ModelProvider(config, rag_logger), rag_logger)
    vectorstore = manager.get_vectorstore()
    query_vec = vectorstore.embeddings.embed_query(query)
    t_embed = time.perf_counter()
    res = vectorstore._collection.query(  # same collection the chat retriever searches
        query_embeddings=[query_vec],
        n_results=k,
        include=["documents", "metadatas", "embeddings", "distances"],
    )
    t_search = time.perf_counter()

    chunks: list[dict[str, Any]] = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    embs = (res.get("embeddings") if res.get("embeddings") is not None else [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for i, text in enumerate(docs):
        meta = dict(metas[i] or {}) if i < len(metas) else {}
        source = str(meta.get("source", ""))
        page = meta.get("page")
        emb = list(embs[i]) if embs is not None and i < len(embs) else []
        chunks.append(
            {
                "rank": i + 1,
                "source": source,
                "source_label": SOURCE_LABELS.get(source, source or "资料"),
                "page": (int(page) + 1) if isinstance(page, int) else None,
                "content": (text or "")[:MAX_CHUNK_CHARS],
                "chars": len(text or ""),
                "similarity": round(_cosine(query_vec, emb), 4) if emb else None,
                "distance": round(float(dists[i]), 4) if i < len(dists) else None,
            }
        )

    return {
        "query": query,
        "k": k,
        "metric": "cosine",
        "total_chunks": vectorstore._collection.count(),
        "embedding_dims": len(query_vec),
        "embed_ms": round((t_embed - t0) * 1000),
        "search_ms": round((t_search - t_embed) * 1000),
        "took_ms": round((t_search - t0) * 1000),
        "chunks": chunks,
    }
