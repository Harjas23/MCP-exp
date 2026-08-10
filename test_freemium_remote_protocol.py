"""Smoke-test the freemium remote MCP HTTP wrapper."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from test_remote_protocol import post, tool_payload


ROOT = Path(__file__).parent


def main() -> None:
    port = 8766
    process = subprocess.Popen([sys.executable, str(ROOT / "freemium_remote_server.py")], env={**os.environ, "PORT": str(port)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
            raise AssertionError("Freemium remote server did not start")

        initialize, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert initialize["result"]["serverInfo"]["name"] == "freemium-data-demo"
        resources, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 10, "method": "resources/list", "params": {}}, session)
        resource_uri = resources["result"]["resources"][0]["uri"]
        skill, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 11, "method": "resources/read", "params": {"uri": resource_uri}}, session)
        assert "Display the search result to the user" in skill["result"]["contents"][0]["text"]
        search, session = post(base + "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_business", "arguments": {"business_name": "Starbucks", "city": "Ohio"}}}, session)
        search_data = tool_payload(search)
        assert len(search_data["masked_samples"]) == 10
        assert "total_verified_emails" in search_data["insights"]
        assert "total_verified_phone_numbers" in search_data["insights"]
        assert "plan" not in search_data
        purchase, _ = post(base + "/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "purchase_business", "arguments": {"search_id": search_data["search_id"], "count": 1}}}, session)
        assert purchase["result"]["isError"] is True
        assert tool_payload(purchase)["status"] == "upgrade_required"
    finally:
        process.terminate()
        process.wait(timeout=5)

    print("PASS: freemium remote HTTP wrapper")


if __name__ == "__main__":
    main()
