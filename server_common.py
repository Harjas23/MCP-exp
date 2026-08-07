"""Small dependency-free MCP-over-stdio helpers for the demo servers."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable


SERVER_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26", "2024-11-05"}


def text_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    """Return an MCP tool result whose human-readable content is JSON."""
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "isError": is_error,
    }


def rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


class StdioMCPServer:
    """Minimal MCP server transport sufficient for Claude Desktop tool demos."""

    def __init__(
        self,
        *,
        name: str,
        version: str,
        tools: list[dict[str, Any]],
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
    ) -> None:
        self.name = name
        self.version = version
        self.tools = tools
        self.handlers = handlers

    def _handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        # Notifications, including initialized, do not receive responses.
        if method == "notifications/initialized":
            return None

        if method == "initialize":
            requested_version = (params.get("protocolVersion") or "").strip()
            negotiated_version = requested_version if requested_version in SUPPORTED_PROTOCOL_VERSIONS else SERVER_PROTOCOL_VERSION
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": negotiated_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.name, "version": self.version},
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tools}}

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            handler = self.handlers.get(tool_name)
            if handler is None:
                return rpc_error(request_id, -32602, f"Unknown tool: {tool_name}")
            try:
                result = handler(arguments)
                if "content" not in result:
                    result = text_result(result)
            except ValueError as exc:
                result = text_result({"status": "invalid_request", "error": str(exc)}, is_error=True)
            except Exception as exc:  # Keep protocol output valid for demo failures.
                print(f"{self.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
                result = text_result(
                    {"status": "server_error", "error": "The demo server could not complete the request."},
                    is_error=True,
                )
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        if request_id is None:
            return None
        return rpc_error(request_id, -32601, f"Method not found: {method}")

    def run(self) -> None:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
                response = self._handle(message)
            except json.JSONDecodeError:
                response = rpc_error(None, -32700, "Invalid JSON")
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": schema(properties, required),
    }
