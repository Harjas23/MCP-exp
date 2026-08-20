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
    search_description = next(tool["description"] for tool in paid_tools if tool["name"] == "search_business")
    assert "the count is the permission signal" in next(tool["description"] for tool in paid_tools if tool["name"] == "purchase_business")
    assert "never calls enrichment" in search_description
    assert "Do not ask a separate yes/no confirmation" in search_description

    prompts = rpc(paid_token, 30, "prompts/list")["result"]["prompts"]
    prompt_names = {prompt["name"] for prompt in prompts}
    assert {"business_search", "contact_search", "consumer_search", "business_enrichment", "consumer_enrichment", "contact_enrichment", "partial_credit_test"} == prompt_names
    prompt = rpc(paid_token, 31, "prompts/get", {"name": "business_search"})
    assert "Show all 10 masked samples" in prompt["result"]["messages"][0]["content"]["text"]

    resources = rpc(paid_token, 3, "resources/list")["result"]["resources"]
    assert resources[0]["uri"] == "mcp://hsb/unified-auth-enrichment-workflow"
    resource = rpc(paid_token, 4, "resources/read", {"uri": resources[0]["uri"]})
    assert "There is no standalone match tool" in resource["result"]["contents"][0]["text"]

    search = payload(rpc(paid_token, 5, "tools/call", {"name": "search_business", "arguments": {"business_name": "Starbucks", "state": "Ohio"}}))
    assert len(search["masked_samples"]) == 10
    assert search["insights"]["total_verified_emails"] >= 0
    assert search["insights"]["total_verified_phone_numbers"] >= 0
    purchase_error = rpc(paid_token, 6, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search["search_id"], "count": 16, "confirm": True}})
    assert purchase_error["result"]["isError"] is True
    purchase_partial = payload(purchase_error)
    assert purchase_partial["status"] == "insufficient_credits"
    assert purchase_partial["records_returned"] == 15
    assert purchase_partial["credits_deducted"] == 15 and purchase_partial["credits_remaining"] == 0

    enrichment_records = [
        {"record_id": "B1", "business_name": "Acme", "full_address": "1 Main Street, Columbus, OH", "email": "a@example.com"},
        {"record_id": "B2", "business_name": "Incomplete", "email": "b@example.com"},
    ]
    enrichment = payload(rpc(free_token, 8, "tools/call", {"name": "enrich_business", "arguments": {"records": enrichment_records}}))
    assert enrichment["status"] == "permission_required"
    assert "matched_count" not in enrichment and "non_matched_count" not in enrichment
    assert "Do you want me to proceed?" in enrichment["permission_message"]
    upgrade = rpc(free_token, 9, "tools/call", {"name": "enrich_business", "arguments": {"enrichment_id": enrichment["enrichment_id"], "count": 1, "confirm": True}})
    assert upgrade["result"]["isError"] is True
    assert payload(upgrade)["status"] == "upgrade_required"

    paid_enrichment_token = _issue_token("paid@example.com")
    many_business_rows = [
        {"record_id": f"B{i}", "business_name": f"Acme {i}", "full_address": f"{i} Main Street, Columbus, OH", "email": f"acme{i}@example.com"}
        for i in range(20)
    ]
    enrichment_start = payload(rpc(paid_enrichment_token, 10, "tools/call", {"name": "enrich_business", "arguments": {"records": many_business_rows}}))
    assert enrichment_start["status"] == "permission_required"
    assert "matched_count" not in enrichment_start and "non_matched_count" not in enrichment_start
    enrichment_partial_response = rpc(paid_enrichment_token, 11, "tools/call", {"name": "enrich_business", "arguments": {"enrichment_id": enrichment_start["enrichment_id"], "count": 20, "confirm": True}})
    assert enrichment_partial_response["result"]["isError"] is True
    enrichment_partial = payload(enrichment_partial_response)
    assert enrichment_partial["status"] == "insufficient_credits"
    assert enrichment_partial["records_returned"] == 15
    assert enrichment_partial["credits_deducted"] == 15 and enrichment_partial["credits_remaining"] == 0

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
            assert "paid@example.com" in page and "freemium@example.com" in page and "Using HSB" in page
            assert "HSB" in page and "Copy prompt" in page and "function copyPrompt" in page
            assert "Using HSB MCP" in page
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
