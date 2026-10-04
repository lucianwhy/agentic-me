"""Inline citations: context chunks are numbered in the same order as the done-event sources."""

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from app.config import config
from app.modules.langchain_compat import create_stuff_documents_chain
from app.modules.rag_pipeline import (
    CITATION_DOCUMENT_PROMPT,
    CITATION_INSTRUCTIONS,
    build_chat_system_prompt,
    number_documents,
)


def _docs():
    return [
        Document(page_content="讯飞聆智实习", metadata={"source": "cv", "page": 0}),
        Document(page_content="7-Agent 编排", metadata={"source": "about_me"}),
    ]


def test_number_documents_is_one_based_and_ordered():
    docs = _docs()
    numbered = number_documents(docs)
    assert [d.metadata["cite"] for d in numbered] == [1, 2]
    assert [d.page_content for d in numbered] == [d.page_content for d in docs]
    assert numbered[0].metadata["source"] == "cv"
    # originals (serialized as sources) are not mutated
    assert all("cite" not in d.metadata for d in docs)


def test_number_documents_empty_and_plain_values():
    assert number_documents([]) == []
    assert number_documents(None) == []  # type: ignore[arg-type]
    assert number_documents(["raw text"])[0].page_content == "raw text"


def test_system_prompt_has_citation_rules_and_context_slot():
    prompt = build_chat_system_prompt(config.chat_system_prompt, "张三")
    assert prompt.endswith(CITATION_INSTRUCTIONS)
    assert "{context}" in prompt
    assert "[n]" not in CITATION_INSTRUCTIONS  # concrete examples, not a placeholder
    # must stay a valid template: only the context variable
    assert ChatPromptTemplate.from_messages([("system", prompt)]).input_variables == ["context"]


def test_chain_renders_numbered_context_in_source_order():
    seen = {}

    def fake_llm(prompt_value):
        seen["text"] = prompt_value.to_string()
        return "ok"

    prompt = ChatPromptTemplate.from_messages(
        [("system", build_chat_system_prompt("资料：{{context}}", "张三")), ("human", "{input}")]
    )
    chain = create_stuff_documents_chain(
        RunnableLambda(fake_llm), prompt, document_prompt=CITATION_DOCUMENT_PROMPT
    )
    chain.invoke({"input": "问", "context": number_documents(_docs())})
    text = seen["text"]
    assert "[1] 讯飞聆智实习" in text
    assert "[2] 7-Agent 编排" in text
    assert text.index("[1] 讯飞聆智实习") < text.index("[2] 7-Agent 编排")


def test_citation_rules_forbid_over_citing():
    """Guard the anti-over-citing rules (missing-info, headings/label lists, summaries, ≤2 sources)."""
    rules = CITATION_INSTRUCTIONS
    for phrase in ("最多 2 个", "没有写到", "标题", "清单", "总结", "问句", "错误：", "正确："):
        assert phrase in rules
    assert "{" not in rules and "}" not in rules  # stays a literal inside the prompt template
