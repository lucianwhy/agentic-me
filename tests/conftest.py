import pytest

from app import admin
from app.utils import env as env_utils


@pytest.fixture(autouse=True)
def _isolated_runtime_files(tmp_path, monkeypatch):
    """Never touch the real data/models.json or .env from tests."""
    monkeypatch.setenv("MODELS_FILE", str(tmp_path / "models.json"))
    env_file = tmp_path / ".env"
    monkeypatch.setattr(admin, "ENV_FILE", env_file)
    monkeypatch.setattr(env_utils, "_DOTENV_PATH", env_file)
    env_utils._dotenv_cache = None
