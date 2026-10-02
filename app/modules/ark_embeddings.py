"""Volcengine Ark multimodal embeddings (doubao-embedding-vision).

Uses POST /embeddings/multimodal — the standard /embeddings endpoint returns
400 for this model family. Each call embeds one text into a single vector.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_TIMEOUT = 60.0


class ArkEmbeddingsError(RuntimeError):
    """Raised when the Ark multimodal embedding API fails."""


class ArkMultimodalEmbeddings(Embeddings):
    """LangChain Embeddings adapter for Volcengine Ark multimodal API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        encoding_format: str = "float",
        query_cache_size: int = 256,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise ArkEmbeddingsError("ARK_API_KEY / EMBEDDING_API_KEY is required.")
        model_id = (model or "").strip()
        if not model_id:
            raise ArkEmbeddingsError("EMBEDDING_MODEL (Ark endpoint id) is required.")

        self.api_key = key
        self.model = model_id
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.encoding_format = encoding_format
        self._endpoint = f"{self.base_url}/embeddings/multimodal"
        # One pooled keep-alive client per instance (thread-safe), so each call does not
        # pay a new TCP + TLS handshake to Ark.
        self._client = httpx.Client(
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=120),
        )
        # LRU of query embeddings: repeated questions (suggested chips, retries) skip the API.
        self._cache_size = max(0, int(query_cache_size))
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = threading.Lock()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        key = text if text is not None else ""
        if self._cache_size:
            with self._cache_lock:
                hit = self._cache.get(key)
                if hit is not None:
                    self._cache.move_to_end(key)
                    return list(hit)
        vector = self._embed_one(key)
        if self._cache_size:
            with self._cache_lock:
                self._cache[key] = vector
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        return list(vector)

    def warmup(self) -> None:
        """Open the pooled connection (one tiny embedding call)."""
        self.embed_query("warmup")

    def _embed_one(self, text: str) -> list[float]:
        payload: dict[str, Any] = {
            "model": self.model,
            "encoding_format": self.encoding_format,
            "input": [{"type": "text", "text": text if text is not None else ""}],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._client.post(self._endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ArkEmbeddingsError(
                f"Ark multimodal embedding timed out after {self.timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise ArkEmbeddingsError(
                f"Ark multimodal embedding request failed: {exc}"
            ) from exc

        if response.status_code >= 400:
            detail = _safe_error_body(response)
            raise ArkEmbeddingsError(
                f"Ark multimodal embedding HTTP {response.status_code}: {detail}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise ArkEmbeddingsError(
                "Ark multimodal embedding returned non-JSON response"
            ) from exc

        embedding = _extract_embedding(body)
        if embedding is None:
            raise ArkEmbeddingsError(
                "Ark multimodal embedding response missing data.embedding "
                f"(keys={list(body.keys()) if isinstance(body, dict) else type(body).__name__})"
            )
        return embedding


def _safe_error_body(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            err = data.get("error") or data.get("message") or data
            return str(err)[:500]
    except Exception:
        pass
    return (response.text or "")[:500]


def _extract_embedding(body: Any) -> list[float] | None:
    """Handle Ark multimodal response shapes.

    Primary: {"data": {"embedding": [...]}}
    Also tolerate OpenAI-style: {"data": [{"embedding": [...]}]}
    and top-level {"embedding": [...]}
    """
    if not isinstance(body, dict):
        return None

    data = body.get("data")
    if isinstance(data, dict):
        emb = data.get("embedding")
        if _is_float_list(emb):
            return list(emb)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            emb = first.get("embedding")
            if _is_float_list(emb):
                return list(emb)
        if _is_float_list(first):
            return list(first)

    emb = body.get("embedding")
    if _is_float_list(emb):
        return list(emb)

    return None


def _is_float_list(value: Any) -> bool:
    return isinstance(value, list) and (not value or isinstance(value[0], (int, float)))
