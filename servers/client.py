"""The one MCP client layer every condition and the oracle use to reach the tools."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import Client, Tool

from servers.state import server_params

SERVER_NAMES = ["sheets", "docs", "crm"]


@dataclass
class ToolResult:
    text: str
    is_error: bool


@dataclass
class ToolClient:
    clients: dict[str, Client]
    tools: list[Tool]
    calls: list[str] = field(default_factory=list)

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        for tool_name, server_name in self._routes.items():
            if tool_name == name:
                self.calls.append(name)
                result = await self.clients[server_name].call_tool(name, arguments)
                return ToolResult("".join(block.text for block in result.content), bool(result.is_error))
        return ToolResult(f"Unknown tool '{name}'", True)

    _routes: dict[str, str] = field(default_factory=dict)


@asynccontextmanager
async def open_tools(state_dir: Path, base_dir: Path | None = None) -> AsyncIterator[ToolClient]:
    """Start the three servers over stdio for one run. They all use that run's state directory."""
    async with (
        Client(server_params("sheets", state_dir, base_dir)) as sheets,
        Client(server_params("docs", state_dir, base_dir)) as docs,
        Client(server_params("crm", state_dir, base_dir)) as crm,
    ):
        clients = {"sheets": sheets, "docs": docs, "crm": crm}
        tools: list[Tool] = []
        routes: dict[str, str] = {}
        for name in SERVER_NAMES:
            listed = (await clients[name].list_tools()).tools
            tools += listed
            routes.update({tool.name: name for tool in listed})
        yield ToolClient(clients, tools, _routes=routes)
