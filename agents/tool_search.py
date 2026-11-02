"""Condition B: direct calling, but the model starts with search_tools and loads schemas on demand."""

import re
from typing import Any

from rank_bm25 import BM25Okapi

from agents.common import Exposure
from agents.direct import openai_schema
from servers.client import ToolClient

TOP_K = 5

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_tools",
        "description": "Search for tools by describing what you need. Matching tools become callable on your next turn.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Words describing what you need to do."}}, "required": ["query"]},
    },
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class ToolSearchExposure(Exposure):
    def __init__(self, client: ToolClient) -> None:
        super().__init__()
        self.client = client
        self.loaded: list[Any] = []
        self._index = BM25Okapi([_tokens(f"{tool.name} {tool.description}") for tool in client.tools])

    def system_block(self) -> str:
        return "You start with only search_tools. Tools it finds become callable on your next turn and stay available for the rest of this conversation."

    def tools(self) -> list[dict[str, Any]]:
        return [_SEARCH_TOOL, *(openai_schema(tool) for tool in self.loaded)]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "search_tools":
            return self._search(arguments.get("query"))
        if not any(tool.name == name for tool in self.loaded):
            return f"Error: tool '{name}' is not loaded. Use search_tools to find it first."
        return (await self.client.call(name, arguments)).text

    def _search(self, query: Any) -> str:
        if not isinstance(query, str) or not _tokens(query):
            return "Error: query must be non-empty text"
        scores = self._index.get_scores(_tokens(query))
        ranked = sorted(zip(scores, self.client.tools), key=lambda pair: (-pair[0], pair[1].name))
        matches = [tool for score, tool in ranked[:TOP_K] if score > 0]
        if not matches:
            return "No matching tools."
        for tool in matches:
            if tool not in self.loaded:
                self.loaded.append(tool)
        lines = [f"- {tool.name}: {(tool.description or '').strip().splitlines()[0]}" for tool in matches]
        return "These tools are now available:\n" + "\n".join(lines)
