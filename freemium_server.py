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
        payload["next_step"] = "If the user asks to reveal records, call purchase_business to show the plan upgrade message."
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
        "business_name": {"type": "string"}, "sic_code": {"type": "string"}, "street": {"type": "string"}, "city": {"type": "string"}, "zip": {"type": "string"}, "revenue": {"type": "string"},
    }
    purchase_props = {"search_id": {"type": "string"}, "count": {"type": "integer", "minimum": 1}}
    tools = [
        tool("search_business", "Freemium business search. Returns 10 masked samples, total matches, and insights.", search_props),
        tool("purchase_business", "Attempt to reveal business records. This freemium server always returns an upgrade-required message.", purchase_props, ["search_id", "count"]),
    ]
    return StdioMCPServer(name="freemium-data-demo", version="1.0.0", tools=tools, handlers={"search_business": demo.search_business, "purchase_business": demo.purchase_business})


if __name__ == "__main__":
    build_server().run()
