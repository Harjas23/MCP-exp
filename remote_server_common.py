"""Dependency-free Streamable HTTP transport shared by both remote demos."""

from __future__ import annotations

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


MCP_PATH = "/mcp"


def run_remote_server(build_server: Callable[[], Any], service_name: str) -> None:
    port = int(os.environ.get("PORT", "8000"))
    mcp = build_server()

    class RemoteMCPHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            super().log_message(format, *args)

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

        def _send_json(self, status: int, payload: dict[str, Any], session_id: str | None = None) -> None:
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            if session_id:
                self.send_header("Mcp-Session-Id", session_id)
            self._cors()
            self.end_headers()
            self.wfile.write(encoded)

        def _send_empty(self, status: int, session_id: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            if session_id:
                self.send_header("Mcp-Session-Id", session_id)
            self._cors()
            self.end_headers()

        def _read_request_body(self) -> bytes:
            """Read both Content-Length and HTTP/1.1 chunked request bodies."""
            transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
            if "chunked" in transfer_encoding:
                chunks: list[bytes] = []
                while True:
                    size_line = self.rfile.readline().strip()
                    if not size_line:
                        raise ValueError("Missing chunk size")
                    size = int(size_line.split(b";", 1)[0], 16)
                    if size == 0:
                        while self.rfile.readline().strip():
                            pass
                        break
                    chunk = self.rfile.read(size)
                    if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                        raise ValueError("Invalid chunk framing")
                    chunks.append(chunk)
                return b"".join(chunks)
            return self.rfile.read(int(self.headers.get("Content-Length", "0")))

        def do_OPTIONS(self) -> None:
            self._send_empty(204)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send_json(200, {"status": "ok", "service": service_name})
                return
            if self.path == MCP_PATH:
                self.send_response(405)
                self.send_header("Allow", "POST, OPTIONS")
                self.send_header("Content-Length", "0")
                self._cors()
                self.end_headers()
                return
            self._send_json(404, {"error": "Not found"})

        def do_DELETE(self) -> None:
            if self.path == MCP_PATH:
                self._send_empty(202, self.headers.get("Mcp-Session-Id"))
                return
            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:
            if self.path != MCP_PATH:
                self._send_json(404, {"error": "Not found"})
                return
            try:
                message = json.loads(self._read_request_body())
            except (ValueError, json.JSONDecodeError):
                self._send_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON"}})
                return
            session_id = self.headers.get("Mcp-Session-Id") or str(uuid.uuid4())
            response = mcp._handle(message)
            if response is None:
                self._send_empty(202, session_id)
                return
            self._send_json(200, response, session_id)

    server = ThreadingHTTPServer(("0.0.0.0", port), RemoteMCPHandler)
    print(f"{service_name} listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
