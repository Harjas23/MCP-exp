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
        "business_name": {"type": "string", "description": "Optional business name filter."}, "sic_code": {"type": "string", "description": "Optional SIC code filter."}, "street": {"type": "string", "description": "Optional street filter."}, "city": {"type": "string", "description": "Optional city filter. Use this only when the user names a city."}, "state": {"type": "string", "description": "Optional state filter. Use this when the user names a state, such as Ohio."}, "zip": {"type": "string", "description": "Optional ZIP code filter."}, "revenue": {"type": "string", "description": "Optional revenue filter."},
    }
    purchase_props = {
        "search_id": {"type": "string", "description": "Copy this value exactly from the preceding search_business response. Never ask the user to provide it and never invent or transform it."},
        "count": {"type": "integer", "minimum": 1, "description": "Use the number requested by the user."},
    }
    tools = [
        tool("search_business", "Freemium business search. All filters are optional. Preserve every filter the user explicitly states: map a named city to city, and map a named state such as Ohio to state; do not put a state in city. The search never reveals full records. Recommended workflow: 1) Display all 10 masked samples to the user. 2) Show total matches and aggregate insights. 3) Ask the user how many records they want to reveal and state that each record consumes 1 credit. 4) If the user provides a number, treat it as permission and call purchase_business with the exact search_id returned by this search and the requested count; if no number is provided, do not call it. It will return the Pro or Teams upgrade message.", search_props),
        tool("purchase_business", "Workflow: call search_business first. Copy the exact search_id from that response; never ask the user for it, invent it, or transform it. Do not call this tool unless the user provided a record count; the count is the permission signal. It always returns an upgrade-required message with the Pro or Teams subscription link.", purchase_props, ["search_id", "count"]),
    ]
    return StdioMCPServer(name="freemium-data-demo", version="1.0.0", tools=tools, handlers={"search_business": demo.search_business, "purchase_business": demo.purchase_business})


if __name__ == "__main__":
    build_server().run()
