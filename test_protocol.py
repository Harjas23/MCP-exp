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
        listed = call(paid, 10, "tools/list")
        tools_by_name = {item["name"]: item for item in listed["result"]["tools"]}
        business_schema = tools_by_name["search_business"]["inputSchema"]
        assert business_schema["required"] == []
        assert "use this only when the user names a city" in business_schema["properties"]["city"]["description"].lower()
        assert "use this when the user names a state" in business_schema["properties"]["state"]["description"].lower()
        assert "map a named state such as ohio to state" in tools_by_name["search_business"]["description"].lower()
        assert "display all 10 masked samples" in tools_by_name["search_business"]["description"].lower()
        assert "do not call purchase_business" in tools_by_name["search_business"]["description"].lower()
        assert "purchase_business" in tools_by_name["search_business"]["description"]
        assert "recommended workflow" in tools_by_name["search_business"]["description"].lower()
        assert "search_business first" in tools_by_name["purchase_business"]["description"]
        assert "do not call this tool unless the user provided a record count" in tools_by_name["purchase_business"]["description"].lower()
        assert "count is the permission signal" in tools_by_name["purchase_business"]["description"].lower()
        assert "never ask the user for it" in tools_by_name["purchase_business"]["description"].lower()
        assert "copy this value exactly" in tools_by_name["purchase_business"]["inputSchema"]["properties"]["search_id"]["description"].lower()
        assert "credits_deducted and credits_remaining" in tools_by_name["purchase_business"]["description"]
        assert "how many records" in tools_by_name["search_business"]["description"].lower()
        assert "each record consumes 1 credit" in tools_by_name["search_business"]["description"].lower()

        search_ids = []
        for request_id, tool_name, args in [
            (2, "search_business", {"business_name": "Starbucks", "state": "Ohio"}),
            (3, "search_contact", {"job_title": "manager"}),
            (4, "search_consumer", {"income": "more than 20000"}),
        ]:
            result = payload(call(paid, request_id, "tools/call", {"name": tool_name, "arguments": args}))
            assert len(result["masked_samples"]) == 10
            assert "credits_available" not in result
            assert "reveal_cost" not in result
            assert result["insights"]["total_count"] == result["total_matches"] == 20
            assert result["insights"]["scope"] == "all matching records, not only the masked previews"
            search_ids.append(result["search_id"])

        # Permission gate, then a 15-record request returns the 5 credit-supported records.
        confirmation = payload(call(paid, 5, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search_ids[0], "count": 15, "confirm": False}}))
        assert confirmation["status"] == "confirmation_required"
        partial = payload(call(paid, 6, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search_ids[0], "count": 15, "confirm": True}}))
        assert partial["status"] == "partial_success"
        assert partial["records_returned"] == 5
        assert partial["credits_deducted"] == 5
        assert partial["credits_remaining"] == 0
        exhausted = call(paid, 7, "tools/call", {"name": "purchase_contact", "arguments": {"search_id": search_ids[1], "count": 1, "confirm": True}})
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
