"""Smoke-test the paid remote MCP HTTP wrapper."""

from __future__ import annotations

import json
from http.client import HTTPConnection
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).parent


def post(url: str, message: dict, session_id: str | None = None) -> tuple[dict, str | None]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = Request(url, data=json.dumps(message).encode(), headers=headers, method="POST")
    with urlopen(request, timeout=5) as response:
        body = response.read()
        return json.loads(body), response.headers.get("Mcp-Session-Id")


def tool_payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


def post_chunked(port: int, message: dict) -> dict:
    """Send one MCP request using the transfer encoding Claude used in the failure."""
    body = json.dumps(message).encode()
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.putrequest("POST", "/mcp")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Accept", "application/json, text/event-stream")
    connection.putheader("Transfer-Encoding", "chunked")
    connection.endheaders()
    connection.send(f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n")
    response = connection.getresponse()
    result = json.loads(response.read())
    connection.close()
    return result


def main() -> None:
    port = "8765"
    process = subprocess.Popen([sys.executable, str(ROOT / "paid_remote_server.py")], env={**__import__("os").environ, "PORT": port}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(30):
            try:
                with urlopen(f"{base}/health", timeout=1) as response:
                    assert response.status == 200
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise AssertionError("Remote server did not start")

        chunked_initialize = post_chunked(int(port), {"jsonrpc": "2.0", "id": 99, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        assert chunked_initialize["result"]["serverInfo"]["name"] == "paid-data-demo"

        initialize, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert initialize["result"]["serverInfo"]["name"] == "paid-data-demo"
        assert session

        resources, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 10, "method": "resources/list", "params": {}}, session)
        resource_uri = resources["result"]["resources"][0]["uri"]
        skill, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 11, "method": "resources/read", "params": {"uri": resource_uri}}, session)
        assert "Display the search result to the user" in skill["result"]["contents"][0]["text"]

        search, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_business", "arguments": {"business_name": "Starbucks", "city": "Ohio"}}}, session)
        search_data = tool_payload(search)
        assert len(search_data["masked_samples"]) == 10
        assert "total_verified_emails" in search_data["insights"]
        assert "total_verified_phone_numbers" in search_data["insights"]

        purchase, _ = post(base + "/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "purchase_business", "arguments": {"search_id": search_data["search_id"], "count": 1, "confirm": True}}}, session)
        purchase_data = tool_payload(purchase)
        assert purchase_data["records_returned"] == 1
        assert purchase_data["credits_remaining"] == 14
    finally:
        process.terminate()
        process.wait(timeout=5)

    print("PASS: remote HTTP MCP wrapper")


if __name__ == "__main__":
    main()
