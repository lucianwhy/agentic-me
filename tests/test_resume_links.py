"""Chunk → sidebar resume entry mapping (resume_entry_ids on /chat sources)."""

from langchain_core.documents import Document

from app.api.routes import _serialize_sources
from app.config import ResumeConfig, ResumeEntry, config
from app.modules import resume_links
from app.modules.resume_links import entry_keys, map_chunk, resume_entry_ids, source_documents

DOC = (
    "教育经历\n甲大学 计算机 · 本科\n证书：CET-6\n专业技能\nPython\n"
    "实习经历\n乙科技有限公司 实习生 | 后端开发\n负责订单服务重构，接口延迟下降一半，并维护支付对账任务和监控告警。\n"
    "项目经历\n星图搜索 - 检索系统 开发\n基于向量检索构建问答系统，支持多路召回和重排，服务三个业务团队。\n"
    "后续部分：完成部署与压测，整理运维文档，并沉淀可复用的检索评测脚本与数据集，同时为离线评测补充了标注规范。\n"
    "海鸥小程序 独立开发\n面向学生的记账工具，上线后累计数百用户使用。\n"
    "个人评价\n热爱技术。"
)
ENTRIES = [
    ("internships-0", entry_keys(ResumeEntry(title="后端开发", organization="乙科技有限公司"))),
    ("projects-0", entry_keys(ResumeEntry(title="星图搜索 - 检索系统"))),
    ("projects-1", entry_keys(ResumeEntry(title="海鸥小程序"))),
    ("education-0", entry_keys(ResumeEntry(title="计算机 · 本科", organization="甲大学"))),
]


def test_entry_keys_include_short_forms():
    keys = entry_keys(ResumeEntry(title="成绩雷达 - AI 学习分析助手", organization="讯飞聆智科技有限公司"))
    assert "成绩雷达-ai学习分析助手" in keys and "成绩雷达" in keys
    assert "讯飞聆智科技有限公司" in keys and "讯飞聆智" in keys


def test_continuation_chunk_maps_by_position_without_title():
    # Starts in the middle of 星图搜索 (no title) and runs into 海鸥小程序.
    chunk = "后续部分：完成部署与压测，整理运维文档，并沉淀可复用的检索评测脚本与数据集，同时为离线评测补充了标注规范。\n海鸥小程序 独立开发\n面向学生的记账工具，上线后累计数百用户使用。"
    ids = map_chunk(chunk, [DOC], ENTRIES)
    assert set(ids) == {"projects-0", "projects-1"}


def test_section_heading_ends_span():
    assert map_chunk("个人评价\n热爱技术。", [DOC], ENTRIES) == []
    assert map_chunk("专业技能\nPython\n", [DOC], ENTRIES) == []


def test_mentions_add_entries_and_unknown_chunk_falls_back_to_names():
    assert map_chunk("推荐先看星图搜索和乙科技有限公司的经历", [DOC], ENTRIES) == ["internships-0", "projects-0"]
    assert map_chunk("完全无关的内容", [DOC], ENTRIES) == []
    assert map_chunk("", [DOC], ENTRIES) == []


def test_whitespace_differences_are_ignored():
    chunk = "负责订单服务重构，  接口延迟下降一半，\n并维护支付对账任务和监控告警。"
    assert map_chunk(chunk, [DOC], ENTRIES) == ["internships-0"]


def test_real_cv_page2_chunk_maps_to_the_continued_project():
    cv = source_documents().get("cv", "")
    start = cv.find("负责多智能体架构设计")
    assert start >= 0
    chunk = cv[start : start + 900]  # PDF page 2: continues 个性化学习多智能体系统, then 成绩雷达
    ids = resume_entry_ids(chunk, {"source": "cv", "page": 1})
    assert "projects-0" in ids and "projects-1" in ids
    assert "internships-0" not in ids


def test_real_about_me_internship_section():
    text = source_documents().get("about_me", "")
    start = text.find("负责模拟直播智能分析与评分链路")
    ids = resume_entry_ids(text[start : start + 120], {"source": "about_me"})
    assert ids == ["internships-0"]


def test_no_resume_config_means_no_ids(monkeypatch):
    monkeypatch.setattr(config, "resume", ResumeConfig())
    assert resume_entry_ids("讯飞聆智科技有限公司", {"source": "cv"}) == []


def test_mapping_errors_are_swallowed(monkeypatch):
    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(resume_links, "source_documents", boom)
    assert resume_entry_ids("讯飞聆智", {"source": "cv"}) == []


def test_serialized_sources_are_backward_compatible():
    long_text = "讯飞聆智科技有限公司 实习生 | 全栈智能体开发 " + "x" * 400
    out = _serialize_sources([Document(page_content=long_text, metadata={"source": "cv"}), {"content": "raw"}])
    assert len(out[0]["content"]) == 300  # wire content still truncated
    assert out[0]["metadata"] == {"source": "cv"}
    assert out[0]["resume_entry_ids"] == ["internships-0"]
    assert out[1] == {"content": "raw"}  # plain dict sources pass through untouched
