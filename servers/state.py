"""Paths, per-run CRM state and output encoding shared by the mock servers."""

import json
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from mcp import StdioServerParameters

ROOT = Path(__file__).resolve().parent.parent
# Tools never read the wall clock, so replayed runs produce identical messages.
FAKE_TODAY = "2026-03-15"


def data_dir() -> Path:
    return Path(os.environ.get("MCP_DATA_DIR", ROOT / "data"))


def dumps(payload: Any) -> str:
    """Encode a tool result as one compact JSON string."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@lru_cache(maxsize=16)
def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_base(relative: str) -> Any:
    """Read a read-only base file. Callers must not mutate the result."""
    return _read_json(data_dir() / relative)


def new_run_state(dest: Path, source: Path | None = None) -> Path:
    """Give one run its own copy of the mutable CRM state."""
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile((source or data_dir()) / "crm.json", dest / "crm.json")
    return dest


def _crm_path() -> Path:
    state_dir = os.environ.get("MCP_STATE_DIR")
    if not state_dir:
        raise RuntimeError("MCP_STATE_DIR is not set")
    return Path(state_dir) / "crm.json"


def load_crm() -> dict[str, Any]:
    return json.loads(_crm_path().read_text(encoding="utf-8"))


def save_crm(crm: dict[str, Any]) -> None:
    path = _crm_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(crm, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def server_params(name: str, state_dir: Path, base_dir: Path | None = None) -> StdioServerParameters:
    """Stdio launch parameters. The SDK passes only a safe default environment plus env below,
    so OPENCODE_API_KEY never reaches a server."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", f"servers.{name}"],
        env={"MCP_STATE_DIR": str(state_dir), "MCP_DATA_DIR": str(base_dir or data_dir())},
        cwd=str(ROOT),
    )
