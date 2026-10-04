"""Public, read-only candidate profile for the frontend (GET /api/profile).

Only fields that the old Jinja chat page already rendered publicly are exposed:
name, headline, contact links, CV download URL, avatar, intro copy and the
suggested questions, plus the structured resume sections (education /
internships / projects / skills) copied from the CV. No keys, passwords,
invite codes or model settings.
"""

from typing import Any

from app.config import config
from app.modules.resume_links import entry_id

AVATAR_URL = "/static/default-avatar.png?v=2"


def _contacts() -> list[dict[str, str]]:
    c = config.candidate
    items: list[dict[str, str]] = []
    email = (c.email or "").strip()
    phone = (getattr(c, "phone", "") or "").strip()
    github = (c.github or "").strip()
    linkedin = (c.linkedin or "").strip()
    scholar = (getattr(c, "scholar", "") or "").strip()
    if email:
        items.append({"type": "email", "label": "邮箱", "value": email, "href": f"mailto:{email}"})
    if phone:
        items.append({"type": "phone", "label": "电话", "value": phone, "href": f"tel:{phone}"})
    if github:
        items.append({"type": "github", "label": "GitHub", "value": github, "href": github})
    if linkedin:
        items.append({"type": "linkedin", "label": "LinkedIn", "value": linkedin, "href": linkedin})
    if scholar:
        items.append({"type": "scholar", "label": "学术", "value": "学术主页", "href": scholar})
    return items


def _suggested_questions(name: str) -> list[dict[str, str]]:
    return [
        {"label": "一句话介绍背景", "question": f"用 5 句话介绍一下 {name} 的背景和求职方向。"},
        {"label": "最近的代表性成果", "question": f"{name} 最近一段经历里最能拿出手的成果是什么？"},
        {"label": "项目与技术栈", "question": f"{name} 做过哪些项目？分别用了什么技术、结果如何？"},
        {"label": "核心技能", "question": f"{name} 的核心技能有哪些？哪些是深入用过的？"},
        {"label": "给招聘方的追问", "question": f"如果我是招聘方，最该追问 {name} 哪三个问题？"},
    ]


# Preset "问 AI" questions per entry kind. Clicking an entry prefills the chat input
# with one of these (the visitor still presses send).
ASK_INTERNSHIP = "讲讲你在{org}实习中具体负责什么、遇到的最难的问题和怎么解决的？"
ASK_PROJECT = "介绍一下「{title}」项目的架构、你的角色和量化成果。"
ASK_EDUCATION = "介绍一下你在{org}的专业学习，以及和 AI 应用开发相关的积累。"
ASK_SKILL = "你在哪些项目里实际用过 {skill}？具体解决了什么问题？"


def _entries(kind: str, items: list[Any], template: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        entry = item.model_dump()
        entry["id"] = entry_id(kind, i)  # same id as /chat sources' resume_entry_ids
        entry["ask"] = template.format(org=item.organization, title=item.title)
        out.append(entry)
    return out


def _resume() -> dict[str, Any]:
    r = config.resume
    return {
        "education": _entries("education", r.education, ASK_EDUCATION),
        "internships": _entries("internships", r.internships, ASK_INTERNSHIP),
        "projects": _entries("projects", r.projects, ASK_PROJECT),
        "skills": [
            {
                "name": g.name,
                "items": [{"name": s, "ask": ASK_SKILL.format(skill=s)} for s in g.items if s.strip()],
            }
            for g in r.skills
        ],
    }


def _question_groups(name: str) -> list[dict[str, Any]]:
    """Empty-chat suggestions, grouped into category tabs. Only reference facts in the CV."""
    return [
        {
            "id": "internship",
            "label": "实习",
            "questions": [
                {"label": "讯飞聆智实习负责什么", "question": ASK_INTERNSHIP.format(org="讯飞聆智")},
                {"label": "直播分析与评分链路", "question": "模拟直播智能分析与评分链路是怎么设计的？4 类分析维度和自动评分规则如何落地？"},
                {"label": "BERT 分层文本审核", "question": "直播文本审核的分层识别链路（规则召回 + BERT + 大模型兜底）是怎么设计的？"},
                {"label": "WebSocket 实时交互", "question": "直播实训的实时交互链路是怎么用 WebSocket 实现的？承载了哪些消息？"},
            ],
        },
        {
            "id": "projects",
            "label": "项目",
            "questions": [
                {"label": "多智能体系统架构", "question": ASK_PROJECT.format(title="个性化学习多智能体系统")},
                {"label": "7-Agent 如何协作", "question": "7-Agent 编排体系是如何划分职责、输入输出与协作边界的？"},
                {"label": "成绩雷达小程序", "question": ASK_PROJECT.format(title="成绩雷达 - AI 学习分析助手")},
                {"label": "项目与技术栈总览", "question": f"{name} 做过哪些项目？分别用了什么技术、结果如何？"},
            ],
        },
        {
            "id": "depth",
            "label": "技术深度",
            "questions": [
                {"label": "RAG 知识增强", "question": "LLM Wiki + 向量语义检索的混合知识增强机制是怎么工作的？"},
                {"label": "Spring AI 接入本地模型", "question": "你是怎么用 Spring AI 接入本地部署大模型，并构建智能体任务执行与业务回写链路的？"},
                {"label": "面部识别迁到服务端", "question": "为什么把面部识别从浏览器端迁移到服务端？带来了什么改善？"},
                {"label": "部署与工程化", "question": "你用 Docker Compose / CloudBase 部署过哪些服务？是怎么编排的？"},
            ],
        },
        {
            "id": "why",
            "label": "为什么选我",
            "questions": [
                {"label": "最能拿出手的成果", "question": f"{name} 最近一段经历里最能拿出手的成果是什么？"},
                {"label": "端到端交付能力", "question": "有没有独立负责从需求设计到上线交付的完整项目？结果如何？"},
                {"label": "求职方向与到岗", "question": "你在看什么样的机会？最快什么时候能到岗？"},
                {"label": "给招聘方的追问", "question": f"如果我是招聘方，最该追问 {name} 哪三个问题？"},
            ],
        },
    ]


def build_public_profile() -> dict[str, Any]:
    """Return the public profile payload consumed by the React frontend."""
    name = config.candidate.name
    return {
        "name": name,
        "headline": (getattr(config.candidate, "headline", "") or "").strip(),
        "avatar_url": AVATAR_URL,
        "cv_url": config.cv_public_url(),
        "cv_download_name": f"{name}_简历.pdf",
        "contacts": _contacts(),
        "skills": [str(x).strip() for x in (getattr(config.candidate, "skills", None) or []) if str(x).strip()][:12],
        "intro_title": "和简历对话",
        "intro": (
            f"这是 {name} 的智能简历卡片。你可以直接用中文提问经历、项目、技能或岗位匹配，"
            "回答只依据简历 PDF 与「关于我」文档，不会编造。"
        ),
        "disclaimer": "模型回答仅供参考。关键事实请对照下载的 PDF 或直接联系本人确认。",
        "welcome": f"你好，我是 {name} 的简历助手。点下面的问题，或直接输入你的问题。",
        "input_placeholder": "例如：TA 有没有带团队或独立负责过完整项目？",
        "suggested_questions": _suggested_questions(name),
        "suggested_question_groups": _question_groups(name),
        "resume": _resume(),
        "limits": {
            "max_query_length": config.security.max_query_length,
            "max_job_text_length": config.security.max_job_text_length,
            "min_job_text_length": config.security.min_job_text_length,
            "rate_limit_ms": config.rate_limit.rate_limit_ms,
        },
    }
