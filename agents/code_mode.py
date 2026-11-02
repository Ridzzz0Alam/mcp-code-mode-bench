"""Condition C: tools as a Python package. The model reads the files and submits code to the sandbox."""

import shutil
import tempfile
from pathlib import Path
from typing import Any

from agents.common import Exposure
from sandbox.executor import TIMEOUT_S, ExecResult, run_code
from sandbox.gateway import Gateway
from servers.client import ToolClient
from servers.state import ROOT

PACKAGE_DIR = ROOT / "toolpkg"
OUTPUT_LIMIT = 4000
TRUNCATION_MARKER = f"\n[output truncated at {OUTPUT_LIMIT} chars]"

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the files and folders at a path inside the toolpkg package. Use an empty path for the package root.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path relative to the package root, such as 'sheets'."}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one file inside the toolpkg package.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path relative to the package root, such as 'sheets/get_row.py'."}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run a Python script in the sandbox and return what it printed.",
            "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "The complete Python script to run."}}, "required": ["code"]},
        },
    },
]


class CodeExposure(Exposure):
    def __init__(self, client: ToolClient) -> None:
        super().__init__()
        # A short path under /tmp, because Unix socket paths are limited to about 108 characters.
        self.run_dir = Path(tempfile.mkdtemp(prefix="bench-", dir="/tmp"))
        (self.run_dir / "sock").mkdir()
        (self.run_dir / "workspace").mkdir()
        self.gateway = Gateway(client, self.run_dir / "sock" / "gateway.sock")

    async def start(self) -> None:
        await self.gateway.start()

    async def close(self) -> None:
        await self.gateway.close()
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def system_block(self) -> str:
        return (
            "Your tools are a Python package named toolpkg, with one module per tool at toolpkg/<server>/<tool>.py. "
            "Each module holds one function with the same name as the module, for example: from toolpkg.sheets.get_row import get_row\n"
            "Use list_files and read_file to explore the package, and run_python to run a script that imports from it. "
            "A failed tool call raises toolpkg._bridge.ToolError.\n"
            f"Scripts run with the Python standard library only and no internet access, and stop after {TIMEOUT_S:.0f} seconds. "
            f"Only what a script prints comes back to you, cut off at {OUTPUT_LIMIT} characters. "
            "Files in /workspace persist between scripts in this conversation, but variables do not."
        )

    def tools(self) -> list[dict[str, Any]]:
        return _TOOLS

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        try:
            if name == "list_files":
                return self._list_files(arguments.get("path", ""))
            if name == "read_file":
                return self._read_file(arguments["path"])
            if name == "run_python":
                return await self._run_python(arguments["code"])
        except KeyError as missing:
            return f"Error: missing argument {missing}"
        return f"Error: unknown tool '{name}'"

    def _resolve(self, relative: Any) -> Path | None:
        if not isinstance(relative, str):
            return None
        path = (PACKAGE_DIR / relative.strip("/")).resolve()
        return path if path.is_relative_to(PACKAGE_DIR) else None

    def _list_files(self, relative: Any) -> str:
        path = self._resolve(relative)
        if path is None or not path.is_dir():
            return f"Error: no such folder '{relative}'"
        names = [f"{p.name}/" if p.is_dir() else p.name for p in sorted(path.iterdir()) if not p.name.startswith((".", "_"))]
        return "\n".join(names)

    def _read_file(self, relative: Any) -> str:
        path = self._resolve(relative)
        if path is None or not path.is_file():
            return f"Error: no such file '{relative}'"
        return path.read_text(encoding="utf-8")

    async def _run_python(self, code: Any) -> str:
        if not isinstance(code, str):
            return "Error: code must be a string"
        self.code_executions += 1
        result = await run_code(code, self.run_dir)
        if result.failed:
            self.sandbox_errors += 1
        return self._format(result)

    def _format(self, result: ExecResult) -> str:
        text = result.stdout
        if result.timed_out:
            text += f"\n[script stopped: exceeded the {TIMEOUT_S:.0f} second limit]"
        elif result.out_of_memory:
            text += "\n[script stopped: out of memory]"
        elif result.failed:
            text += f"\n[script failed with exit code {result.exit_code}]\n{result.stderr}"
        if len(text) > OUTPUT_LIMIT:
            self.truncated_outputs += 1
            return text[:OUTPUT_LIMIT] + TRUNCATION_MARKER
        return text or "(the script printed nothing)"
