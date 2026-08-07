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
        payload.pop("credits_available", None)
        payload.pop("reveal_cost", None)
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
        "business_name": {"type": "string", "description": "Optional business name filter."}, "sic_code": {"type": "string", "description": "Optional SIC code filter."}, "street": {"type": "string", "description": "Optional street filter."}, "city": {"type": "string", "description": "Optional city filter. City is not required."}, "zip": {"type": "string", "description": "Optional ZIP code filter."}, "revenue": {"type": "string", "description": "Optional revenue filter."},
    }
    purchase_props = {"search_id": {"type": "string"}, "count": {"type": "integer", "minimum": 1}}
    tools = [
        tool("search_business", "Freemium business search. All filters are optional, including city. Returns masked previews, total matches, and aggregate insights. Workflow recommendation: after the search, ask the user how many records they want revealed and ask for permission to proceed. If the user provides a number and permission, call purchase_business with this search_id and count; it will return the Pro or Teams upgrade message.", search_props),
        tool("purchase_business", "Workflow: call search_business first and use its returned search_id. Do not call this purchase tool without a prior search. After the user provides a record count and permission, call this tool; it always returns an upgrade-required message with the Pro or Teams subscription link.", purchase_props, ["search_id", "count"]),
    ]
    return StdioMCPServer(name="freemium-data-demo", version="1.0.0", tools=tools, handlers={"search_business": demo.search_business, "purchase_business": demo.purchase_business})


if __name__ == "__main__":
    build_server().run()
