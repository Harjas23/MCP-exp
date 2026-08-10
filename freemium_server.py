"""Freemium MCP demo: business search/match followed by upgrade-required reveals."""

from __future__ import annotations

from typing import Any

from paid_server import PaidDemo, TOP_UP_URL
from server_common import StdioMCPServer, text_result, tool, workflow_resource


class FreemiumDemo:
    def __init__(self) -> None:
        self.paid_demo = PaidDemo()

    def search_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = self.paid_demo.search_business(arguments)
        return payload

    def purchase_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return text_result({
            "status": "upgrade_required",
            "error": "You don't have an active paid subscription. Buy credits or upgrade to a Pro or Teams plan to reveal business records.",
            "upgrade_url": TOP_UP_URL,
            "requested_records": arguments.get("count"),
            "records": [],
        }, is_error=True)

    def match_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.paid_demo.match(arguments, "business")

    def enrich_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return text_result({
            "status": "upgrade_required",
            "error": "You don't have an active paid subscription. Buy credits or upgrade to a Pro or Teams plan to enrich business records.",
            "upgrade_url": TOP_UP_URL,
            "requested_records": arguments.get("count"),
            "records": [],
        }, is_error=True)


def build_server() -> StdioMCPServer:
    demo = FreemiumDemo()
    resources, resource_contents = workflow_resource()
    search_props = {
        "business_name": {"type": "string", "description": "Optional business name filter."}, "sic_code": {"type": "string", "description": "Optional SIC code filter."}, "street": {"type": "string", "description": "Optional street filter."}, "city": {"type": "string", "description": "Optional city filter. Use this only when the user names a city."}, "state": {"type": "string", "description": "Optional state filter. Use this when the user names a state, such as Ohio."}, "zip": {"type": "string", "description": "Optional ZIP code filter."}, "revenue": {"type": "string", "description": "Optional revenue filter."},
    }
    purchase_props = {
        "search_id": {"type": "string", "description": "Copy this value exactly from the preceding search_business response. Never ask the user to provide it and never invent or transform it."},
        "count": {"type": "integer", "minimum": 1, "description": "Use the number requested by the user."},
    }
    match_props = {
        "records": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "description": "Rows parsed by Claude from the file uploaded by the user. Do not pass a file path or upload the file to MCP.",
            "items": {"type": "object", "additionalProperties": True},
        },
    }
    enrich_props = {
        "match_id": {"type": "string", "description": "Copy this value exactly from the preceding match_business response. Never ask the user for it and never invent or transform it."},
        "count": {"type": "integer", "minimum": 1, "description": "Use the number of matched records the user authorized for enrichment."},
    }
    tools = [
        tool("search_business", "Freemium business search. All filters are optional. Preserve every filter the user explicitly states: map a named city to city, and map a named state such as Ohio to state; do not put a state in city. The search never reveals full records. Recommended workflow: MANDATORY RESPONSE ACTION: Display all 10 masked samples from the masked_samples field to the user exactly as returned; do not summarize, omit, or hide them. Then show total matches and aggregate insights. Ask the user how many records they want to reveal and state that each record consumes 1 credit. If the user provides a number, treat it as permission and call purchase_business with the exact search_id returned by this search and the requested count; if no number is provided, do not call it. It will return the Pro or Teams upgrade message.", search_props),
        tool("purchase_business", "Workflow: call search_business first. Copy the exact search_id from that response; never ask the user for it, invent it, or transform it. Do not call this tool unless the user provided a record count; the count is the permission signal. It always returns an upgrade-required message with the Pro or Teams subscription link.", purchase_props, ["search_id", "count"]),
        tool("match_business", "Match uploaded business rows for the freemium business match-and-enrich experience. Pass rows parsed from the file uploaded in Claude; MCP validates fields and does not receive a file path. Required matching data is business name plus full address plus website, email, or phone. Process up to 100 rows, return matched and dropped counts, identify incomplete rows, then display: 1 credit per record will be deducted, do you want me to proceed? Call enrich_business only after the user provides permission and a number.", match_props, ["records"]),
        tool("enrich_business", "Workflow: call match_business first and copy its exact match_id; never ask the user for it. Do not call unless the user has provided a record count as permission. It returns no records and an upgrade-required message: buy credits or upgrade to a Pro or Teams plan, with the subscription URL.", enrich_props, ["match_id", "count"]),
    ]
    return StdioMCPServer(name="freemium-data-demo", version="1.0.0", tools=tools, handlers={"search_business": demo.search_business, "purchase_business": demo.purchase_business, "match_business": demo.match_business, "enrich_business": demo.enrich_business}, resources=resources, resource_contents=resource_contents)


if __name__ == "__main__":
    build_server().run()
