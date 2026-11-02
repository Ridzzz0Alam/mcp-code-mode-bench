"""Generate the condition C package from the live MCP tool list. Usage: uv run python toolpkg_gen.py

Writes one module per tool at toolpkg/<server>/<tool>.py, each with a typed signature and docstring.
"""

import asyncio
import textwrap
from pathlib import Path
from typing import Any

from mcp import Client

from servers import crm, docs, sheets
from servers.state import ROOT

OUTPUT = ROOT / "toolpkg"
SERVERS = {"sheets": sheets.server, "docs": docs.server, "crm": crm.server}
_TYPES = {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "array": "list", "object": "dict"}

BRIDGE = '''"""Sends tool calls from the sandbox to the host over a Unix socket."""

import json
import socket
from typing import Any

SOCKET_PATH = "/sock/gateway.sock"


class ToolError(Exception):
    """The tool rejected the call."""


def call(tool: str, arguments: dict[str, Any]) -> Any:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(SOCKET_PATH)
        connection.sendall(json.dumps({"tool": tool, "arguments": arguments}).encode() + b"\\n")
        with connection.makefile("rb") as stream:
            reply = json.loads(stream.readline())
    if reply["is_error"]:
        raise ToolError(reply["text"])
    try:
        return json.loads(reply["text"])
    except json.JSONDecodeError:
        return reply["text"]
'''


def annotation(schema: dict[str, Any]) -> str:
    if "anyOf" in schema:
        return " | ".join(annotation(option) for option in schema["anyOf"])
    if "enum" in schema:
        return f"Literal[{', '.join(repr(value) for value in schema['enum'])}]"
    if schema.get("type") == "null":
        return "None"
    if schema.get("type") == "array":
        return f"list[{annotation(schema.get('items', {}))}]"
    return _TYPES.get(schema.get("type", ""), "Any")


def render_module(tool: Any) -> str:
    schema = tool.input_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    ordered = [name for name in properties if name in required] + [name for name in properties if name not in required]
    params = []
    docs_lines = []
    for name in ordered:
        spec = properties[name]
        default = "" if name in required else f" = {spec.get('default')!r}"
        params.append(f"{name}: {annotation(spec)}{default}")
        if spec.get("description"):
            docs_lines.append(f"{name}: {spec['description']}")
    description = textwrap.dedent(tool.description or "").strip().replace("\\", "\\\\").replace('"""', "'''")
    body = description
    if docs_lines:
        body += "\n\nArgs:\n" + "\n".join(f"    {line}" for line in docs_lines)
    docstring = textwrap.indent(body, "    ").lstrip()
    arguments = ", ".join(f'"{name}": {name}' for name in ordered)
    return (
        "from typing import Any, Literal\n\n"
        "from toolpkg._bridge import call\n\n\n"
        f"def {tool.name}({', '.join(params)}) -> Any:\n"
        f'    """{docstring}\n    """\n'
        f'    return call("{tool.name}", {{{arguments}}})\n'
    )


async def render_all() -> dict[str, str]:
    files = {"__init__.py": "", "_bridge.py": BRIDGE}
    for server_name, server in SERVERS.items():
        files[f"{server_name}/__init__.py"] = ""
        async with Client(server) as client:
            for tool in (await client.list_tools()).tools:
                files[f"{server_name}/{tool.name}.py"] = render_module(tool)
    return files


def main() -> None:
    for relative, text in asyncio.run(render_all()).items():
        path = OUTPUT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
