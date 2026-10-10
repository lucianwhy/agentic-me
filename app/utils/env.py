"""Read process env with a project-root ``.env`` fallback.

pydantic-settings loads ``.env`` into the config object but does not export those
keys into ``os.environ``. Admin-managed per-model ``api_key_env`` names therefore
need the same lookup the MCP proxy uses: process environment first, then the
repo-root ``.env`` via python-dotenv. Never log or return a value unless the
caller asked for it; ``api_key_present`` only exposes a boolean.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from dotenv import dotenv_values

# Repo root, not the process CWD. systemd starts the app with WorkingDirectory
# set, but pydantic-settings reads `.env` without exporting it into os.environ.
_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
# (path, mtime_ns) -> parsed values. Editing the file changes mtime and reloads.
_dotenv_cache: tuple[str, int, dict[str, str]] | None = None
_dotenv_lock = threading.Lock()


def _dotenv_values() -> dict[str, str]:
    """Project-root ``.env``. Missing file is empty. Cached until mtime changes."""
    global _dotenv_cache
    path = _DOTENV_PATH
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return {}
    key = (str(path), mtime_ns)
    with _dotenv_lock:
        cached = _dotenv_cache
        if cached is not None and cached[0] == key[0] and cached[1] == key[1]:
            return cached[2]
        parsed = dotenv_values(path)
        values = {
            str(name): value if isinstance(value, str) else ""
            for name, value in parsed.items()
            if name
        }
        _dotenv_cache = (key[0], key[1], values)
        return values


def env_get(name: str) -> str:
    """Process environment wins; otherwise the same key in the project-root ``.env``."""
    if not name:
        return ""
    if name in os.environ:
        return os.environ[name]
    return _dotenv_values().get(name, "")


def env_is_set(name: str | None) -> bool:
    """True when ``name`` is a non-empty env var (process env or ``.env``). Never returns the value."""
    if not name:
        return False
    return bool(env_get(name).strip())
