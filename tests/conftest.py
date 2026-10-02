import pytest

from app import admin


@pytest.fixture(autouse=True)
def _isolated_runtime_files(tmp_path, monkeypatch):
    """Never touch the real data/models.json or .env from tests."""
    monkeypatch.setenv("MODELS_FILE", str(tmp_path / "models.json"))
    monkeypatch.setattr(admin, "ENV_FILE", tmp_path / ".env")
