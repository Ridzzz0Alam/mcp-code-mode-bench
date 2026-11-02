"""Host-side bridge: forwards tool calls from the no-network container to the run's MCP client."""

import asyncio
import json
from pathlib import Path

from servers.client import ToolClient

STREAM_LIMIT = 64 * 1024 * 1024


class Gateway:
    def __init__(self, client: ToolClient, socket_path: Path) -> None:
        self.client = client
        self.socket_path = socket_path
        self._server: asyncio.Server | None = None
        self._handlers: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self._server = await asyncio.start_unix_server(self._handle, path=str(self.socket_path), limit=STREAM_LIMIT)

    async def close(self) -> None:
        if self._server:
            self._server.close()
        for task in list(self._handlers):
            task.cancel()
        await asyncio.gather(*self._handlers, return_exceptions=True)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._handlers.add(task)
        try:
            line = await reader.readline()
            if line:
                writer.write(json.dumps(await self._reply(line)).encode() + b"\n")
                await writer.drain()
        except (ConnectionError, BrokenPipeError):
            pass
        finally:
            self._handlers.discard(task)
            writer.close()

    async def _reply(self, line: bytes) -> dict[str, object]:
        try:
            request = json.loads(line)
            tool, arguments = request["tool"], request["arguments"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return {"text": "Malformed tool request", "is_error": True}
        result = await self.client.call(tool, arguments)
        return {"text": result.text, "is_error": result.is_error}
