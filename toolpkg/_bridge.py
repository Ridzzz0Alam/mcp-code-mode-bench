"""Sends tool calls from the sandbox to the host over a Unix socket."""

import json
import socket
from typing import Any

SOCKET_PATH = "/sock/gateway.sock"


class ToolError(Exception):
    """The tool rejected the call."""


def call(tool: str, arguments: dict[str, Any]) -> Any:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(SOCKET_PATH)
        connection.sendall(json.dumps({"tool": tool, "arguments": arguments}).encode() + b"\n")
        with connection.makefile("rb") as stream:
            reply = json.loads(stream.readline())
    if reply["is_error"]:
        raise ToolError(reply["text"])
    try:
        return json.loads(reply["text"])
    except json.JSONDecodeError:
        return reply["text"]
