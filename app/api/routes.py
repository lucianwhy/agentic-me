import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth.auth import (
    authenticate_with_code,
    get_current_user,
    get_user_info,
    is_auth_enabled,
    logout_user,
    require_auth,
)
from app.modules.job_matching import (
    analyze_job_match,
    process_job_description,
)
from app.modules.rag_pipeline import get_chat_completion, get_chat_stream
from app.modules.readiness import (
    LLMNotConfigured,
    VectorStoreNotReady,
    chinese_not_ready_error,
    is_llm_configured,
    is_vectorstore_ready,
)
from app.modules.summary_pipeline import get_auto_summary
from app.utils.analytics import AdvancedAnalytics, log_login_event
from app.utils.logging_config import api_logger

router = APIRouter()
advanced_analytics = AdvancedAnalytics()


def _extract_answer_text(result: dict) -> str:
    """Normalize LangChain / pipeline answer into a plain string."""
    answer = result.get("answer")
    if isinstance(answer, dict):
        inner = answer.get("answer")
        if isinstance(inner, str):
            return inner
        if inner is not None:
            return str(inner)
        # Full chain result nested under "answer"
        for key in ("output", "text", "content", "result"):
            if isinstance(answer.get(key), str):
                return answer[key]
        return ""
    if isinstance(answer, str):
        return answer
    if answer is None:
        return ""
    return str(answer)


def _serialize_sources(sources) -> list:
    """Make retrieval sources JSON-safe."""
    out: list = []
    for item in sources or []:
        if hasattr(item, "page_content"):
            out.append(
                {
                    "content": (getattr(item, "page_content", None) or "")[:300],
                    "metadata": dict(getattr(item, "metadata", None) or {}),
                }
            )
        elif isinstance(item, dict):
            out.append(item)
        else:
            out.append({"content": str(item)})
    return out



def _not_ready_response() -> JSONResponse:
    return JSONResponse(status_code=503, content=chinese_not_ready_error())


@router.post("/auth/login")
async def login(
    request: Request, response: Response, invite_code: str = Body(..., embed=True)
):
    """
    Authenticate user with an invite code.

    Sets a secure session cookie upon successful authentication.
    Logs login events and starts a chat session for analytics.
    """
    session_token = authenticate_with_code(invite_code)
    user_info = get_user_info(invite_code)

    if not session_token:
        log_login_event(invite_code, user_info.get("company", "Unknown"), False)
        api_logger.warning(f"Login failed for invite code: {invite_code}")
        raise HTTPException(status_code=401, detail="Invalid invite code")

    log_login_event(invite_code, user_info.get("company", "Unknown"), True)
    api_logger.info(
        f"Successful login for company: {user_info.get('company', 'Unknown')}, invite code: {invite_code}"
    )

    advanced_analytics.start_chat_session(
        session_token, invite_code, user_info.get("company", "Unknown")
    )

    from app.config import config

    host = request.headers.get("host", "").lower()
    is_local = "localhost" in host or "127.0.0.1" in host
    secure_cookies = config.security.secure_cookies and not is_local

    api_logger.debug(
        f"Setting session cookie (secure={secure_cookies}, host={host}) for invite code: {invite_code}"
    )

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=secure_cookies,
        samesite="lax",
        max_age=config.security.session_timeout_hours * 60 * 60,
    )

    return {
        "success": True,
        "message": "Authentication successful",
        "user": {"company": user_info.get("company", "Unknown"), "code": invite_code},
    }


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Log out the current user by deleting the session cookie."""
    session_token = request.cookies.get("session_token")
    if session_token:
        advanced_analytics.end_chat_session(session_token)
        logout_user(session_token)
        api_logger.info(f"User logged out with session token: {session_token}")
    else:
        api_logger.info("Logout attempted with no active session token found.")

    response.delete_cookie("session_token")
    return {"success": True, "message": "Logged out successfully"}


@router.get("/auth/status")
async def auth_status(request: Request):
    """
    Check the authentication status of the current user.
    Returns user information if authenticated, or anonymous status if auth is disabled.
    """
    if not is_auth_enabled():
        api_logger.debug("Auth status: authentication disabled")
        return {
            "authenticated": False,
            "auth_enabled": False,
            "user": {"company": "公开访问", "code": "anonymous"},
        }

    user_code = get_current_user(request)
    if user_code:
        user_info = get_user_info(user_code)
        api_logger.debug(
            f"Authentication status checked: user authenticated as {user_code}"
        )
        return {
            "authenticated": True,
            "auth_enabled": True,
            "user": {"company": user_info.get("company", "Unknown"), "code": user_code},
        }
    api_logger.debug("Authentication status checked: user not authenticated")
    return {"authenticated": False, "auth_enabled": True}


@router.post("/chat")
async def chat(
    request: Request,
    query: str = Body(..., embed=True),
    user_code: str = Depends(require_auth),
):
    """Handle chat queries. Returns Chinese JSON when the LLM or vectorstore is not ready."""
    if not is_llm_configured() or (
        not is_vectorstore_ready() and not is_llm_configured()
    ):
        return _not_ready_response()

    user_info = get_user_info(user_code)
    company = user_info.get("company", "Unknown")
    session_token = request.cookies.get("session_token")

    api_logger.info(
        f"Received chat query from {company} (user_code: {user_code}), query length: {len(query)}"
    )

    user_metadata = {"user_code": user_code, "company": company}
    start_time = time.time()

    try:
        result = get_chat_completion(
            query,
            user_metadata=user_metadata,
        )
    except (LLMNotConfigured, VectorStoreNotReady):
        return _not_ready_response()

    response_time = time.time() - start_time

    response_text = _extract_answer_text(result)
    sources = _serialize_sources(result.get("sources", []))

    from app.config import config

    advanced_analytics.log_chat_interaction_advanced(
        user_code=user_code,
        company=company,
        query=query,
        response=response_text,
        response_time=response_time,
        sources=sources,
        session_token=session_token or "",
        metadata={"llm_model": config.llm.model, "pipeline": "RAG"},
    )

    api_logger.info(f"Chat response generated for {company} in {response_time:.2f}s")
    return {"answer": response_text, "sources": sources}


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    query: str = Body(..., embed=True),
    user_code: str = Depends(require_auth),
):
    """
    Stream chat answers as Server-Sent Events (SSE).

    Wire protocol (`text/event-stream`):
      data: {"type":"token","content":"..."}
      data: {"type":"done","sources":[...]}
      data: {"type":"error","message":"..."}

    Keeps POST /chat for non-streaming compatibility.
    Retrieval runs first (non-stream); only the final answer LLM is streamed.
    """
    if not is_llm_configured() or (
        not is_vectorstore_ready() and not is_llm_configured()
    ):
        return _not_ready_response()

    user_info = get_user_info(user_code)
    company = user_info.get("company", "Unknown")
    session_token = request.cookies.get("session_token")

    api_logger.info(
        f"Received streaming chat query from {company} (user_code: {user_code}), "
        f"query length: {len(query)}"
    )

    user_metadata = {"user_code": user_code, "company": company}
    start_time = time.time()

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def event_generator() -> Iterator[str]:
        accumulated: list[str] = []
        try:
            for event in get_chat_stream(query, user_metadata=user_metadata):
                etype = event.get("type")
                if etype == "token":
                    content = event.get("content") or ""
                    accumulated.append(content)
                    yield _sse({"type": "token", "content": content})
                elif etype == "done":
                    sources = _serialize_sources(event.get("sources", []))
                    response_time = time.time() - start_time
                    response_text = "".join(accumulated)
                    try:
                        from app.config import config

                        advanced_analytics.log_chat_interaction_advanced(
                            user_code=user_code,
                            company=company,
                            query=query,
                            response=response_text,
                            response_time=response_time,
                            sources=sources,
                            session_token=session_token or "",
                            metadata={
                                "llm_model": config.llm.model,
                                "pipeline": "RAG-stream",
                            },
                        )
                    except Exception as log_err:  # analytics must not break the stream
                        api_logger.warning(f"Stream analytics logging failed: {log_err!s}")
                    api_logger.info(
                        f"Streaming chat response for {company} finished in {response_time:.2f}s"
                    )
                    yield _sse({"type": "done", "sources": sources})
                elif etype == "error":
                    yield _sse(
                        {
                            "type": "error",
                            "message": event.get("message") or "生成回答失败，请稍后重试",
                        }
                    )
                else:
                    # Forward unknown events for forward compatibility
                    yield _sse(event)
        except (LLMNotConfigured, VectorStoreNotReady):
            err = chinese_not_ready_error()
            yield _sse(
                {
                    "type": "error",
                    "message": err.get("message") or "服务暂未就绪",
                }
            )
        except Exception as exc:
            api_logger.error(
                f"Streaming chat failed for {company}: {type(exc).__name__}: {exc!s}"
            )
            yield _sse({"type": "error", "message": "生成回答失败，请稍后重试"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering for SSE
        },
    )


@router.post("/summary")
async def summary(
    request: Request,
    style: str = Query("bullet"),
    user_code: str = Depends(require_auth),
):
    """Generate a summary. Returns Chinese JSON when the API is not configured."""
    if not is_llm_configured():
        return _not_ready_response()

    user_info = get_user_info(user_code)
    company = user_info.get("company", "Unknown")

    api_logger.info(
        f"Summary request received from {company} (user_code: {user_code}), style: {style}"
    )

    user_metadata = {"user_code": user_code, "company": company}

    try:
        result = get_auto_summary(style, user_metadata=user_metadata)
    except (LLMNotConfigured, VectorStoreNotReady):
        return _not_ready_response()

    summary_text = result.get("summary_md", "")

    from app.config import config

    advanced_analytics.log_summary_request_advanced(
        user_code=user_code,
        company=company,
        style=style,
        summary_text=summary_text,
        metadata={"llm_model": config.llm.model, "pipeline": "Summarization"},
    )

    api_logger.info(
        f"Summary generated for {company}, length: {len(summary_text)} characters"
    )
    return result


@router.post("/job-match")
async def job_match_endpoint(request: Request, user_code: str = Depends(require_auth)):
    """Job matching analysis. Returns Chinese JSON when the API is not configured."""
    if not is_llm_configured():
        return _not_ready_response()

    user_info = get_user_info(user_code)
    company = user_info.get("company", "Unknown")
    session_token = request.cookies.get("session_token")

    api_logger.info(
        f"Job matching request received from {company} (user_code: {user_code})"
    )

    try:
        body = await request.json()
        text_input = body.get("text")
        job_description = process_job_description(text=str(text_input))
        user_metadata = {"user_code": user_code, "company": company}
        start_time = time.time()
        analysis_result = analyze_job_match(job_description, user_metadata)
        response_time = time.time() - start_time

        from app.config import config

        advanced_analytics.log_job_matching_advanced(
            user_code=user_code,
            company=company,
            job_source=analysis_result.get("job_source", "text_input"),
            analysis_text=analysis_result["analysis"],
            response_time=response_time,
            session_token=session_token or "",
            metadata={"llm_model": config.llm.model, "pipeline": "JobMatching"},
        )

        api_logger.info(
            f"Job matching analysis completed for {company} in {response_time:.2f}s"
        )

        return {
            "analysis": analysis_result["analysis"],
            "source": analysis_result.get("job_source", "text_input"),
            "timestamp": analysis_result.get("match_timestamp"),
            "relevant_sections": analysis_result.get("relevant_sections", []),
        }

    except (LLMNotConfigured, VectorStoreNotReady):
        return _not_ready_response()
    except ValueError as e:
        api_logger.error(f"Job matching validation error for {company}: {e!s}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        api_logger.error(f"Job matching processing error for {company}: {e!s}")
        raise HTTPException(status_code=500, detail="岗位匹配分析失败，请稍后重试")
