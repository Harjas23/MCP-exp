"""Freemium MCP demo: business search followed by an upgrade-required purchase."""

from __future__ import annotations

from typing import Any

from paid_server import PaidDemo, TOP_UP_URL
from server_common import StdioMCPServer, text_result, tool


class FreemiumDemo:
    def __init__(self) -> None:
        self.paid_demo = PaidDemo()

    def search_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = self.paid_demo.search_business(arguments)
        payload["plan"] = "freemium"
        return payload

    def purchase_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return text_result({
            "status": "upgrade_required",
            "error": "You are on a freemium plan. Upgrade to a Pro or Teams plan to reveal business records.",
            "upgrade_url": TOP_UP_URL,
            "requested_records": arguments.get("count"),
            "records": [],
        }, is_error=True)


def build_server() -> StdioMCPServer:
    demo = FreemiumDemo()
    search_props = {
        "business_name": {"type": "string", "description": "Optional business name filter."}, "sic_code": {"type": "string", "description": "Optional SIC code filter."}, "street": {"type": "string", "description": "Optional street filter."}, "city": {"type": "string", "description": "Optional city or location filter. If the user states a location such as 'in Ohio', pass that value here; omit city only when no location is provided."}, "zip": {"type": "string", "description": "Optional ZIP code filter."}, "revenue": {"type": "string", "description": "Optional revenue filter."},
    }
    purchase_props = {
        "search_id": {"type": "string", "description": "Copy this value exactly from the preceding search_business response. Never ask the user to provide it and never invent or transform it."},
        "count": {"type": "integer", "minimum": 1, "description": "Use the number requested by the user, such as count=20 for 'give me 20 records'."},
    }
    tools = [
        tool("search_business", "Freemium business search. All filters are optional, including city. Preserve every filter the user explicitly states: when a location is provided, pass it as the city argument; omit city only when no location is provided. The search never reveals full records. Recommended workflow: 1) Display all 10 masked samples to the user. 2) Show total matches and aggregate insights. 3) Ask: 'How many records would you like to reveal? Each record will consume 1 credit per record. Do you want to proceed?' 4) Do not call purchase_business until the user provides the count and permission. Then call it with the exact search_id returned by this search and the requested count; it will return the Pro or Teams upgrade message.", search_props),
        tool("purchase_business", "Workflow: call search_business first. Copy the exact search_id from that response; never ask the user for it, invent it, or transform it. Do not call this tool before the search workflow has received the user's count and permission. Then call with the requested count; it always returns an upgrade-required message with the Pro or Teams subscription link.", purchase_props, ["search_id", "count"]),
    ]
    return StdioMCPServer(name="freemium-data-demo", version="1.0.0", tools=tools, handlers={"search_business": demo.search_business, "purchase_business": demo.purchase_business})


if __name__ == "__main__":
    build_server().run()
