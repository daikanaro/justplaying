from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def config_dir() -> Path:
    return REPO_ROOT / "config"
