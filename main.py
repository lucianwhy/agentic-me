"""
ChatCV - Interactive Resume Assistant

A FastAPI application that transforms static resumes into intelligent,
conversational experiences using RAG (Retrieval-Augmented Generation).
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
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


# Only the CV PDF is public under /data (its URL is config.cv_public_url()). The rest of
# data/ (analytics.log, vector_db/, about_me.md, ...) must never be served.
DATA_DIR = Path(__file__).resolve().parent / "data"


@app.api_route("/data/{file_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def public_data_file(file_path: str) -> Response:
    public_name = config.cv_public_url().removeprefix("/data/")
    cv_file = (Path(__file__).resolve().parent / config.data.cv_path).resolve()
    if file_path != public_name or not cv_file.is_file() or DATA_DIR not in cv_file.parents:
        return Response(status_code=404)
    return FileResponse(cv_file, media_type="application/pdf")
templates = Jinja2Templates(directory="templates")

# React build output (`cd frontend && npm run build`). Committed to git so the
# server needs no Node. Checked per request, so a fresh build is picked up
# without a restart; if it is missing, "/" falls back to templates/chat.html.
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False),
    name="frontend-assets",
)


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
async def index(request: Request) -> Response:
    """Serve the React chat app, or the legacy Jinja page if no build exists."""
    react_index = FRONTEND_DIST / "index.html"
    if react_index.is_file():
        logger.debug("Serving React chat interface")
        return FileResponse(
            react_index,
            media_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )
    logger.debug("React build missing; serving legacy chat template")
    return render_template(
        request,
        "chat.html",
        {
            "candidate_name": config.candidate.name,
            "candidate_headline": getattr(config.candidate, "headline", ""),
            "candidate_email": config.candidate.email,
            "candidate_phone": getattr(config.candidate, "phone", "") or "",
            "candidate_linkedin": config.candidate.linkedin,
            "candidate_github": config.candidate.github,
            "candidate_scholar": getattr(config.candidate, "scholar", "") or "",
            "cv_path": config.cv_public_url(),
        },
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    """Serve the unlinked, password-protected runtime settings page."""
    return render_template(request, "admin.html", {})


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
