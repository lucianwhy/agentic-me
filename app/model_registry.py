"""Chat models offered in the front-end switcher, managed from /admin.

Stored server-side as JSON outside version control (``data/models.json`` by default,
gitignored and never served: the /data route only exposes the CV PDF). Override the
path with ``MODELS_FILE``. The file is re-read whenever its mtime/size changes, so admin
edits (or a manual edit on the server) apply to the next request without a restart.

Schema::

    {"default": "gpt-5.6-sol",
     "models": [{"id": "gpt-5.6-sol", "label": "Sol（质量）", "reasoning_effort": null}, ...]}

``reasoning_effort`` is optional per model; null means "use the global REASONING_EFFORT".
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from app.utils.logging_config import main_logger as logger

REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")  # same as admin settings
MAX_MODELS = 20
MAX_LABEL_CHARS = 40
_MODEL_ID_RE = re.compile(r"[A-Za-z0-9._:/-]{1,128}")

SEED: dict[str, Any] = {
    "default": "gpt-5.6-sol",
    "models": [
        {"id": "gpt-5.6-sol", "label": "Sol（质量）", "reasoning_effort": None},
        {"id": "gpt-5.6-luna", "label": "Luna（更快）", "reasoning_effort": None},
        {"id": "gpt-5.6-terra", "label": "Terra", "reasoning_effort": None},
    ],
}


class ModelRegistryError(ValueError):
    """Invalid admin input (maps to HTTP 4xx)."""


def _default_path() -> Path:
    return Path(os.getenv("MODELS_FILE") or "data/models.json")


def validate_model_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _MODEL_ID_RE.fullmatch(text):
        raise ModelRegistryError(
            "模型 ID 不能为空，最长 128 个字符，只能包含字母、数字、点、下划线、连字符、冒号或斜杠。"
        )
    return text


def _validate_label(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return fallback
    if len(text) > MAX_LABEL_CHARS:
        raise ModelRegistryError(f"显示名称不能超过 {MAX_LABEL_CHARS} 个字符。")
    return text


def _validate_effort(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text not in REASONING_EFFORTS:
        raise ModelRegistryError(f"不支持的分析强度：{text}")
    return text


def _normalize(data: Any) -> dict[str, Any]:
    """Validate a whole document; raises ModelRegistryError."""
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ModelRegistryError("模型列表格式错误。")
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data["models"]:
        if not isinstance(item, dict):
            raise ModelRegistryError("模型列表格式错误。")
        model_id = validate_model_id(item.get("id"))
        if model_id in seen:
            raise ModelRegistryError(f"模型重复：{model_id}")
        seen.add(model_id)
        models.append(
            {
                "id": model_id,
                "label": _validate_label(item.get("label"), model_id),
                "reasoning_effort": _validate_effort(item.get("reasoning_effort")),
            }
        )
    if not models:
        raise ModelRegistryError("至少需要保留一个模型。")
    if len(models) > MAX_MODELS:
        raise ModelRegistryError(f"最多 {MAX_MODELS} 个模型。")
    default = str(data.get("default") or "").strip()
    if default not in seen:
        default = models[0]["id"]
    return {"default": default, "models": models}


class ModelRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self._explicit_path = path
        self._lock = RLock()
        self._data: dict[str, Any] | None = None
        self._stamp: tuple[str, int, int] | None = None

    @property
    def path(self) -> Path:
        return self._explicit_path or _default_path()

    # ---- persistence -------------------------------------------------------------
    def _file_stamp(self, path: Path) -> tuple[str, int, int] | None:
        try:
            st = path.stat()
        except FileNotFoundError:
            return None
        return (str(path), st.st_mtime_ns, st.st_size)

    def _write(self, data: dict[str, Any]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            tmp = fh.name
        Path(tmp).replace(path)
        self._data = copy.deepcopy(data)
        self._stamp = self._file_stamp(path)

    def _load(self) -> dict[str, Any]:
        """Return the current document, re-reading the file when it changed."""
        path = self.path
        stamp = self._file_stamp(path)
        if stamp is None:
            # First run: seed from the built-in list.
            self._write(_normalize(SEED))
            logger.info("Seeded chat model list at %s", path)
            return self._data  # type: ignore[return-value]
        if self._data is not None and stamp == self._stamp:
            return self._data
        try:
            data = _normalize(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            # A broken manual edit must not take chat down: keep the last good list.
            logger.error("Ignoring invalid model list %s: %s", path, exc)
            if self._data is None:
                self._data = _normalize(SEED)
            self._stamp = stamp
            return self._data
        self._data, self._stamp = data, stamp
        return data

    # ---- reads -------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._load())

    def ids(self) -> list[str]:
        return [m["id"] for m in self.snapshot()["models"]]

    def default(self) -> str:
        return self.snapshot()["default"]

    def get(self, model_id: str | None) -> dict[str, Any] | None:
        if not model_id:
            return None
        return next((m for m in self.snapshot()["models"] if m["id"] == model_id), None)

    def resolve(self, requested: str | None) -> tuple[str, bool]:
        """(model to use, whether the request was honoured). Unknown -> default."""
        with self._lock:
            data = self._load()
            name = str(requested or "").strip()
            if name and any(m["id"] == name for m in data["models"]):
                return name, True
            return data["default"], not name

    def public(self) -> dict[str, Any]:
        """Shape for GET /models (no per-model reasoning settings)."""
        data = self.snapshot()
        return {
            "default": data["default"],
            "models": [m["id"] for m in data["models"]],
            "labels": {m["id"]: m["label"] for m in data["models"]},
            "items": [{"id": m["id"], "label": m["label"]} for m in data["models"]],
        }

    # ---- admin mutations -----------------------------------------------------------
    def _mutate(self, fn) -> dict[str, Any]:
        with self._lock:
            data = copy.deepcopy(self._load())
            fn(data)
            normalized = _normalize(data)
            self._write(normalized)
            return copy.deepcopy(normalized)

    def add(self, model_id: Any, label: Any = None, reasoning_effort: Any = None) -> dict[str, Any]:
        mid = validate_model_id(model_id)
        entry = {
            "id": mid,
            "label": _validate_label(label, mid),
            "reasoning_effort": _validate_effort(reasoning_effort),
        }

        def fn(data: dict[str, Any]) -> None:
            if any(m["id"] == mid for m in data["models"]):
                raise ModelRegistryError(f"模型已存在：{mid}")
            if len(data["models"]) >= MAX_MODELS:
                raise ModelRegistryError(f"最多 {MAX_MODELS} 个模型。")
            data["models"].append(entry)

        return self._mutate(fn)

    def update(self, model_id: str, label: Any = None, reasoning_effort: Any = None) -> dict[str, Any]:
        def fn(data: dict[str, Any]) -> None:
            entry = next((m for m in data["models"] if m["id"] == model_id), None)
            if entry is None:
                raise ModelRegistryError(f"模型不存在：{model_id}")
            entry["label"] = _validate_label(label, model_id)
            entry["reasoning_effort"] = _validate_effort(reasoning_effort)

        return self._mutate(fn)

    def delete(self, model_id: str) -> dict[str, Any]:
        def fn(data: dict[str, Any]) -> None:
            if not any(m["id"] == model_id for m in data["models"]):
                raise ModelRegistryError(f"模型不存在：{model_id}")
            if data["default"] == model_id:
                raise ModelRegistryError("不能删除默认模型，请先把其他模型设为默认。")
            if len(data["models"]) <= 1:
                raise ModelRegistryError("至少需要保留一个模型。")
            data["models"] = [m for m in data["models"] if m["id"] != model_id]

        return self._mutate(fn)

    def set_default(self, model_id: str) -> dict[str, Any]:
        def fn(data: dict[str, Any]) -> None:
            if not any(m["id"] == model_id for m in data["models"]):
                raise ModelRegistryError(f"模型不存在：{model_id}")
            data["default"] = model_id

        return self._mutate(fn)

    def reorder(self, ids: Any) -> dict[str, Any]:
        def fn(data: dict[str, Any]) -> None:
            current = [m["id"] for m in data["models"]]
            if not isinstance(ids, list) or sorted(map(str, ids)) != sorted(current):
                raise ModelRegistryError("排序列表必须恰好包含现有的全部模型。")
            by_id = {m["id"]: m for m in data["models"]}
            data["models"] = [by_id[str(i)] for i in ids]

        return self._mutate(fn)


_registry = ModelRegistry()


def get_model_registry() -> ModelRegistry:
    return _registry
