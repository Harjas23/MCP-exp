"""Smoke-test the MCP protocol and the paid/freemium demo flows."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent


def call(proc: subprocess.Popen[str], request_id: int, method: str, params: dict | None = None) -> dict:
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


def start(script: str) -> subprocess.Popen[str]:
    proc = subprocess.Popen([sys.executable, str(ROOT / script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert proc.stdin and proc.stdout
    call(proc, 1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "smoke-test", "version": "1"}})
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()
    return proc


def main() -> None:
    paid = start("paid_server.py")
    try:
        search_ids = []
        for request_id, tool_name, args in [
            (2, "search_business", {"business_name": "Starbucks", "city": "Ohio"}),
            (3, "search_contact", {"job_title": "manager"}),
            (4, "search_consumer", {"income": "more than 20000"}),
        ]:
            result = payload(call(paid, request_id, "tools/call", {"name": tool_name, "arguments": args}))
            assert len(result["masked_samples"]) == 10
            assert result["credits_available"] == 60
            search_ids.append(result["search_id"])

        # Permission gate, then three 20-record purchases exhaust 60 credits.
        confirmation = payload(call(paid, 5, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search_ids[0], "count": 20, "confirm": False}}))
        assert confirmation["status"] == "confirmation_required"
        for request_id, tool_name, search_id in [(6, "purchase_business", search_ids[0]), (7, "purchase_contact", search_ids[1]), (8, "purchase_consumer", search_ids[2])]:
            result = payload(call(paid, request_id, "tools/call", {"name": tool_name, "arguments": {"search_id": search_id, "count": 20, "confirm": True}}))
            assert result["records_returned"] == 20
        exhausted = call(paid, 9, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search_ids[0], "count": 1, "confirm": True}})
        assert exhausted["result"]["isError"] is True
        assert payload(exhausted)["status"] == "no_credits"
    finally:
        paid.terminate()
        paid.wait(timeout=5)

    freemium = start("freemium_server.py")
    try:
        result = payload(call(freemium, 2, "tools/call", {"name": "search_business", "arguments": {"business_name": "Starbucks", "city": "Ohio"}}))
        assert len(result["masked_samples"]) == 10
        upgrade = call(freemium, 3, "tools/call", {"name": "purchase_business", "arguments": {"search_id": result["search_id"], "count": 20}})
        assert upgrade["result"]["isError"] is True
        assert payload(upgrade)["status"] == "upgrade_required"
    finally:
        freemium.terminate()
        freemium.wait(timeout=5)

    print("PASS: paid and freemium MCP flows")


if __name__ == "__main__":
    main()
