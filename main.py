"""
ChatCV - Interactive Resume Assistant

A FastAPI application that transforms static resumes into intelligent,
conversational experiences using RAG (Retrieval-Augmented Generation).
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as chat_router
from app.config import config
from app.modules.readiness import get_readiness
from app.utils.logging_config import main_logger

logger = main_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start without requiring API keys."""
    ready = get_readiness()
    logger.info(
        "ChatCV startup: llm_configured=%s vectorstore_ready=%s auth_enabled=%s",
        ready["llm_configured"],
        ready["vectorstore_ready"],
        ready["auth_enabled"],
    )
    yield
    logger.info("ChatCV application shutting down")


app = FastAPI(
    title="ChatCV",
    description="Interactive Resume Assistant powered by AI",
    version="1.0.0",
    docs_url="/docs" if config.environment == "development" else None,
    redoc_url="/redoc" if config.environment == "development" else None,
    lifespan=lifespan,
)

logger.info("ChatCV application starting up")

app.include_router(chat_router)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory="data"), name="data")
templates = Jinja2Templates(directory="templates")


def render_template(
    request: Request, name: str, context: dict[str, Any]
) -> HTMLResponse:
    """Starlette 0.x used (name, context); 1.x uses (request, name, context)."""
    payload = {"request": request, **context}
    try:
        return templates.TemplateResponse(request, name, payload)
    except TypeError:
        return templates.TemplateResponse(name, payload)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve the main chat interface."""
    logger.debug("Serving main chat interface")
    return render_template(
        request,
        "chat.html",
        {
            "candidate_name": config.candidate.name,
            "candidate_headline": getattr(config.candidate, "headline", ""),
            "candidate_email": config.candidate.email,
            "candidate_linkedin": config.candidate.linkedin,
            "candidate_github": config.candidate.github,
            "candidate_scholar": getattr(config.candidate, "scholar", "") or "",
            "cv_path": config.cv_public_url(),
        },
    )


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint for monitoring and load balancers.

    Always returns healthy if the process is up, even without API keys.
    Extra fields report LLM / vectorstore readiness.
    """
    payload: dict[str, Any] = {"status": "healthy", "service": "ChatCV-OSS"}
    payload.update(get_readiness())
    return payload
