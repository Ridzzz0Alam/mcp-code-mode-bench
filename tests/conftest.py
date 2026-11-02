from pathlib import Path

import pytest

from data.generate import generate
from servers.state import new_run_state


@pytest.fixture(scope="session")
def base_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("base")
    generate(path)
    return path


@pytest.fixture(autouse=True)
def run_state(base_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = new_run_state(tmp_path / "state", base_dir)
    monkeypatch.setenv("MCP_DATA_DIR", str(base_dir))
    monkeypatch.setenv("MCP_STATE_DIR", str(state))
    return state
