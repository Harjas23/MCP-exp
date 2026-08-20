"""Tests for the isolated unified authenticated MCP demo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from unified_server import MCP, _issue_token  # noqa: E402


def payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


def rpc(token: str, request_id: int, method: str, params: dict | None = None) -> dict:
    response = MCP.call(token, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
    assert response is not None
    return response


def main() -> None:
    paid_token = _issue_token("paid@example.com")
    free_token = _issue_token("freemium@example.com")

    paid_tools = rpc(paid_token, 1, "tools/list")["result"]["tools"]
    free_tools = rpc(free_token, 2, "tools/list")["result"]["tools"]
    paid_names = {tool["name"] for tool in paid_tools}
    assert paid_names == {tool["name"] for tool in free_tools}
    assert {"search_business", "search_consumer", "search_contact", "purchase_business", "purchase_consumer", "purchase_contact", "enrich_business", "enrich_consumer", "enrich_contact"} == paid_names
    enrich_description = next(tool["description"] for tool in paid_tools if tool["name"] == "enrich_business")
    assert "user brings their own uploaded records" in enrich_description
    assert "no separate match tool" in enrich_description

    resources = rpc(paid_token, 3, "resources/list")["result"]["resources"]
    assert resources[0]["uri"] == "mcp://sales-genie/unified-auth-enrichment-workflow"
    resource = rpc(paid_token, 4, "resources/read", {"uri": resources[0]["uri"]})
    assert "There is no standalone match tool" in resource["result"]["contents"][0]["text"]

    search = payload(rpc(paid_token, 5, "tools/call", {"name": "search_business", "arguments": {"business_name": "Starbucks", "state": "Ohio"}}))
    assert len(search["masked_samples"]) == 10
    assert search["insights"]["total_verified_emails"] >= 0
    assert search["insights"]["total_verified_phone_numbers"] >= 0
    purchase_error = rpc(paid_token, 6, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search["search_id"], "count": 16, "confirm": True}})
    assert purchase_error["result"]["isError"] is True
    assert payload(purchase_error)["status"] == "insufficient_credits"
    purchase = payload(rpc(paid_token, 7, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search["search_id"], "count": 15, "confirm": True}}))
    assert purchase["records_returned"] == 15 and purchase["credits_remaining"] == 0

    enrichment_records = [
        {"record_id": "B1", "business_name": "Acme", "full_address": "1 Main Street, Columbus, OH", "email": "a@example.com"},
        {"record_id": "B2", "business_name": "Incomplete", "email": "b@example.com"},
    ]
    enrichment = payload(rpc(free_token, 8, "tools/call", {"name": "enrich_business", "arguments": {"records": enrichment_records}}))
    assert enrichment["status"] == "permission_required"
    assert enrichment["matched_count"] == 1 and enrichment["non_matched_count"] == 1
    upgrade = rpc(free_token, 9, "tools/call", {"name": "enrich_business", "arguments": {"enrichment_id": enrichment["enrichment_id"], "count": 1, "confirm": True}})
    assert upgrade["result"]["isError"] is True
    assert payload(upgrade)["status"] == "upgrade_required"

    process = subprocess.Popen([sys.executable, str(ROOT / "unified_server.py")], env={**os.environ, "PORT": "8777"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    base = "http://127.0.0.1:8777"
    try:
        for _ in range(30):
            try:
                with urlopen(base + "/health", timeout=1) as response:
                    assert response.status == 200
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise AssertionError("Unified server did not start")
        with urlopen(base + "/login", timeout=2) as response:
            page = response.read().decode()
            assert "paid@example.com" in page and "freemium@example.com" in page and "Find me Starbucks" in page
            assert "HSB" in page and "Copy prompt" in page and "function copyPrompt" in page
        with urlopen(Request(base + "/mcp", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")) as response:
            raise AssertionError(f"Expected auth failure, got {response.status}")
    except Exception as exc:
        if getattr(exc, "code", None) != 401:
            raise
    finally:
        process.terminate()
        process.wait(timeout=5)

    print("PASS: unified authenticated MCP demo")


if __name__ == "__main__":
    main()
