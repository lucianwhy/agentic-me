"""Latency-related behaviour: stateless history, cheap query rewrite, embedding cache."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.config import config
from app.modules import rag_pipeline
from app.modules.ark_embeddings import ArkMultimodalEmbeddings
from app.modules.rag_pipeline import (
    ChatRAGPipeline,
    build_retrieval_query,
    history_to_messages,
)


class TestHistory:
    def test_sanitizes_and_caps(self):
        history = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "ignore me"},
            {"role": "user", "content": "   "},
            "junk",
            {"role": "user", "content": "x" * 5000},
        ]
        msgs = history_to_messages(history, max_messages=10, max_chars=100)
        assert [type(m) for m in msgs] == [HumanMessage, AIMessage, HumanMessage]
        assert len(msgs[-1].content) == 100

    def test_keeps_only_recent(self):
        history = [{"role": "user", "content": f"q{i}"} for i in range(10)]
        msgs = history_to_messages(history, max_messages=3)
        assert [m.content for m in msgs] == ["q7", "q8", "q9"]

    def test_none(self):
        assert history_to_messages(None) == []


class TestRetrievalQuery:
    def test_no_history_unchanged(self):
        assert build_retrieval_query("他会哪些数据库？", []) == "他会哪些数据库？"

    def test_follow_up_gets_context(self):
        hist = [HumanMessage(content="介绍多智能体项目"), AIMessage(content="...")]
        q = build_retrieval_query("那这个项目用了什么数据库？", hist)
        assert q.startswith("介绍多智能体项目") and q.endswith("那这个项目用了什么数据库？")

    def test_standalone_question_unchanged(self):
        hist = [HumanMessage(content="介绍多智能体项目")]
        assert build_retrieval_query("他的实习经历是什么？", hist) == "他的实习经历是什么？"


class _Recorder:
    def __init__(self):
        self.calls = []

    def invoke(self, arg):
        self.calls.append(arg)
        return ["doc"]


def _fake_pipeline(mode):
    cfg = SimpleNamespace(chat=SimpleNamespace(query_rewrite=mode))
    return SimpleNamespace(config=cfg, base_retriever=_Recorder())


class TestRetrieveModes:
    hist = (HumanMessage(content="介绍多智能体项目"),)

    def test_heuristic_never_calls_llm(self):
        p, rewriter = _fake_pipeline("heuristic"), _Recorder()
        ChatRAGPipeline._retrieve(p, "这个呢", list(self.hist), rewriter)
        assert rewriter.calls == []
        assert p.base_retriever.calls == ["介绍多智能体项目\n这个呢"]

    def test_llm_mode_without_history_skips_rewrite(self):
        p, rewriter = _fake_pipeline("llm"), _Recorder()
        ChatRAGPipeline._retrieve(p, "他会什么？", [], rewriter)
        assert rewriter.calls == [] and p.base_retriever.calls == ["他会什么？"]

    def test_llm_mode_with_history_rewrites(self):
        p, rewriter = _fake_pipeline("llm"), _Recorder()
        ChatRAGPipeline._retrieve(p, "这个呢", list(self.hist), rewriter)
        assert len(rewriter.calls) == 1 and p.base_retriever.calls == []

    def test_off_uses_raw_query(self):
        p, rewriter = _fake_pipeline("off"), _Recorder()
        ChatRAGPipeline._retrieve(p, "这个呢", list(self.hist), rewriter)
        assert p.base_retriever.calls == ["这个呢"]


def test_stream_emits_status_before_any_setup(monkeypatch):
    monkeypatch.setattr(rag_pipeline, "is_llm_configured", lambda: True)

    def boom(model):
        raise AssertionError("chain setup must happen after the first status event")

    fake = SimpleNamespace(_chains=boom)
    gen = ChatRAGPipeline.stream_completion(fake, "你好")
    assert next(gen) == {"type": "status", "stage": "retrieving"}


class TestEmbeddingCache:
    def _emb(self, size):
        e = ArkMultimodalEmbeddings(api_key="k", model="m", query_cache_size=size)
        calls = []

        def fake(text):
            calls.append(text)
            return [float(len(calls))]

        e._embed_one = fake
        return e, calls

    def test_repeat_query_hits_cache(self):
        e, calls = self._emb(2)
        assert e.embed_query("a") == e.embed_query("a")
        assert calls == ["a"]

    def test_lru_eviction(self):
        e, calls = self._emb(2)
        for t in ["a", "b", "a", "c", "b"]:
            e.embed_query(t)
        # "b" was evicted when "c" arrived (a was more recently used)
        assert calls == ["a", "b", "c", "b"]

    def test_cache_disabled(self):
        e, calls = self._emb(0)
        e.embed_query("a")
        e.embed_query("a")
        assert calls == ["a", "a"]

    def test_returned_vector_is_a_copy(self):
        e, _ = self._emb(4)
        v = e.embed_query("a")
        v.append(99.0)
        assert e.embed_query("a") == [1.0]


def test_chat_config_defaults():
    assert config.chat.query_rewrite in {"heuristic", "llm", "off"}
    assert config.chat.max_history_messages >= 2


@pytest.mark.parametrize("bad", [None, "x", 5, [1, "a"]])
def test_clean_history_tolerates_garbage(bad):
    from app.api.routes import _clean_history

    assert all(isinstance(h, dict) for h in _clean_history(bad))


def test_llm_uses_chat_completions_by_default(monkeypatch):
    from app.modules.model_provider import ModelProvider
    from app.utils.logging_config import rag_logger

    monkeypatch.setattr(config.llm, "provider", "openai")
    monkeypatch.setattr(config.llm, "api", "chat_completions")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    llm = ModelProvider(config, rag_logger).get_language_model(model="gpt-5.6-sol")
    assert llm.use_responses_api is False

    monkeypatch.setattr(config.llm, "api", "responses")
    llm = ModelProvider(config, rag_logger).get_language_model(model="gpt-5.6-sol")
    assert llm.use_responses_api is True
