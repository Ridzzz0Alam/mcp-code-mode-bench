"""Condition A: every tool schema on every request, and results returned verbatim."""

from typing import Any

from agents.common import Exposure
from servers.client import ToolClient


def openai_schema(tool: Any) -> dict[str, Any]:
    return {"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}}


class DirectExposure(Exposure):
    def __init__(self, client: ToolClient) -> None:
        super().__init__()
        self.client = client

    def system_block(self) -> str:
        return "Every tool is available for you to call directly."

    def tools(self) -> list[dict[str, Any]]:
        return [openai_schema(tool) for tool in self.client.tools]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        return (await self.client.call(name, arguments)).text
