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

        # Permission gate, then a 15-record request returns an error with no records.
        confirmation = payload(call(paid, 5, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search_ids[0], "count": 15, "confirm": False}}))
        assert confirmation["status"] == "confirmation_required"
        insufficient = call(paid, 6, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search_ids[0], "count": 15, "confirm": True}})
        insufficient_data = payload(insufficient)
        assert insufficient["result"]["isError"] is True
        assert insufficient_data["status"] == "insufficient_credits"
        assert insufficient_data["records"] == []
        assert insufficient_data["available_records"] == 5
        assert insufficient_data["credits_available"] == 5
        approved = payload(call(paid, 7, "tools/call", {"name": "purchase_business", "arguments": {"search_id": search_ids[0], "count": 5, "confirm": True}}))
        assert approved["status"] == "success"
        assert approved["records_returned"] == 5
        assert approved["credits_deducted"] == 5
        assert approved["credits_remaining"] == 0
        exhausted = call(paid, 8, "tools/call", {"name": "purchase_contact", "arguments": {"search_id": search_ids[1], "count": 1, "confirm": True}})
        assert exhausted["result"]["isError"] is True
        assert payload(exhausted)["status"] == "no_credits"
    finally:
        paid.terminate()
        paid.wait(timeout=5)

    match_paid = start("paid_server.py")
    try:
        listed = call(match_paid, 20, "tools/list")
        tools_by_name = {item["name"]: item for item in listed["result"]["tools"]}
        for name in [
            "match_business", "match_consumer", "match_contact",
            "enrich_business", "enrich_consumer", "enrich_contact",
        ]:
            assert name in tools_by_name
        assert tools_by_name["match_business"]["inputSchema"]["properties"]["records"]["maxItems"] == 100
        assert "file uploaded in claude" in tools_by_name["match_business"]["description"].lower()
        assert "copy its exact match_id" in tools_by_name["enrich_business"]["description"]

        business_rows = [
            {"record_id": "B001", "business_name": "Starbucks", "street": "1 Main Street", "city": "Columbus", "state": "OH", "zip": "43004", "email": "b1@example.com"},
            {"record_id": "B002", "business_name": "Incomplete Business", "street": "2 Main Street", "email": "b2@example.com"},
        ]
        business_match = payload(call(match_paid, 21, "tools/call", {"name": "match_business", "arguments": {"records": business_rows}}))
        assert business_match["matched_count"] == 1
        assert business_match["dropped_count"] == 1
        assert business_match["permission_message"] == "1 credit per record will be deducted, do you want me to proceed?"
        business_enriched = payload(call(match_paid, 22, "tools/call", {"name": "enrich_business", "arguments": {"match_id": business_match["match_id"], "count": 1, "confirm": True}}))
        assert business_enriched["records_returned"] == 1
        assert business_enriched["credits_deducted"] == 1
        assert business_enriched["credits_remaining"] == 4
        assert set(["name", "sic", "emp_size", "estimated_revenue", "address", "email"]).issubset(business_enriched["records"][0])

        consumer_rows = [
            {"record_id": "C001", "full_name": "Jordan One", "full_address": "1 Broad Street, Columbus, OH"},
            {"record_id": "C002", "full_name": "Jordan Two"},
        ]
        consumer_match = payload(call(match_paid, 23, "tools/call", {"name": "match_consumer", "arguments": {"records": consumer_rows}}))
        assert consumer_match["matched_count"] == 1 and consumer_match["dropped_count"] == 1

        contact_rows = [
            {"record_id": "T001", "contact_first_name": "Alex", "contact_last_name": "One", "job_title": "Manager", "business_name": "Acme", "business_full_address": "1 Main Street, Columbus, OH", "contact_type": "primary"},
            {"record_id": "T002", "contact_first_name": "Sam", "contact_last_name": "Two", "job_title": "Director", "business_name": "Acme", "business_full_address": "1 Main Street, Columbus, OH", "contact_type": "secondary"},
        ]
        contact_match = payload(call(match_paid, 24, "tools/call", {"name": "match_contact", "arguments": {"records": contact_rows}}))
        assert contact_match["matched_count"] == 2
        contact_enriched = payload(call(match_paid, 25, "tools/call", {"name": "enrich_contact", "arguments": {"match_id": contact_match["match_id"], "count": 2, "confirm": True}}))
        assert contact_enriched["records_returned"] == 2
        assert contact_enriched["credits_deducted"] == 2

        partial_rows = [{"record_id": f"C{i}", "full_name": f"Consumer {i}", "full_address": f"{i} Main Street, Columbus, OH"} for i in range(1, 4)]
        partial_match = payload(call(match_paid, 26, "tools/call", {"name": "match_consumer", "arguments": {"records": partial_rows}}))
        insufficient = call(match_paid, 27, "tools/call", {"name": "enrich_consumer", "arguments": {"match_id": partial_match["match_id"], "count": 3, "confirm": True}})
        assert insufficient["result"]["isError"] is True
        insufficient_data = payload(insufficient)
        assert insufficient_data["status"] == "insufficient_credits"
        assert insufficient_data["records"] == []
        assert insufficient_data["available_records"] == 2
        approved = payload(call(match_paid, 28, "tools/call", {"name": "enrich_consumer", "arguments": {"match_id": partial_match["match_id"], "count": 2, "confirm": True}}))
        assert approved["records_returned"] == 2
        assert approved["credits_deducted"] == 2
        assert approved["credits_remaining"] == 0
    finally:
        match_paid.terminate()
        match_paid.wait(timeout=5)

    freemium = start("freemium_server.py")
    try:
        result = payload(call(freemium, 2, "tools/call", {"name": "search_business", "arguments": {"business_name": "Starbucks", "city": "Ohio"}}))
        assert len(result["masked_samples"]) == 10
        upgrade = call(freemium, 3, "tools/call", {"name": "purchase_business", "arguments": {"search_id": result["search_id"], "count": 20}})
        assert upgrade["result"]["isError"] is True
        assert payload(upgrade)["status"] == "upgrade_required"
        business_match = payload(call(freemium, 4, "tools/call", {"name": "match_business", "arguments": {"records": [{"business_name": "Starbucks", "full_address": "1 Main Street, Columbus, OH", "email": "b@example.com"}]}}))
        assert business_match["matched_count"] == 1
        enrich = call(freemium, 5, "tools/call", {"name": "enrich_business", "arguments": {"match_id": business_match["match_id"], "count": 1}})
        assert enrich["result"]["isError"] is True
        assert payload(enrich)["status"] == "upgrade_required"
    finally:
        freemium.terminate()
        freemium.wait(timeout=5)

    print("PASS: paid and freemium MCP flows")


if __name__ == "__main__":
    main()
