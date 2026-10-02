"""Public, read-only candidate profile for the frontend (GET /api/profile).

Only fields that the old Jinja chat page already rendered publicly are exposed:
name, headline, contact links, CV download URL, avatar, intro copy and the
suggested questions. No keys, passwords, invite codes or model settings.
"""

from typing import Any

from app.config import config

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
        "limits": {
            "max_query_length": config.security.max_query_length,
            "max_job_text_length": config.security.max_job_text_length,
            "min_job_text_length": config.security.min_job_text_length,
            "rate_limit_ms": config.rate_limit.rate_limit_ms,
        },
    }
