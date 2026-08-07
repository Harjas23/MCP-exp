"""Paid MCP demo: three searches, masked previews, and credit-gated purchases."""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from server_common import StdioMCPServer, text_result, tool


TOP_UP_URL = "https://teampitstop.wixsite.com/home"
INITIAL_CREDITS = 60


def _mask(value: str) -> str:
    value = str(value)
    return value if len(value) <= 2 else value[:2] + "*" * max(4, len(value) - 2)


def _value(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    return str(value).strip() if value is not None else ""


def _number_from_text(value: str) -> int | None:
    match = re.search(r"\d[\d,]*", value)
    return int(match.group(0).replace(",", "")) if match else None


class PaidDemo:
    def __init__(self) -> None:
        self.credits = INITIAL_CREDITS
        self.sequence = 0
        self.searches: dict[str, dict[str, Any]] = {}

    def _new_search(self, kind: str, arguments: dict[str, Any], records: list[dict[str, Any]], total: int, insights: dict[str, Any], preview_fields: list[str]) -> dict[str, Any]:
        self.sequence += 1
        search_id = f"{kind}-{self.sequence:03d}"
        self.searches[search_id] = {"kind": kind, "records": records}
        masked = [{key: _mask(str(record[key])) for key in preview_fields} for record in records[:10]]
        return {
            "status": "search_complete",
            "search_id": search_id,
            "total_matches": total,
            "masked_samples": masked,
            "insights": insights,
            "credits_available": self.credits,
            "reveal_cost": "1 credit per record",
        }

    def search_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        name = _value(arguments, "business_name") or "Starbucks"
        location = _value(arguments, "city") or "Ohio"
        base = [
            ("Starbucks", "coffee", "starbucks.com", "100 Main Street, Columbus, OH", "contact@starbucks.com"),
            ("Starbucks Reserve", "coffee", "reserve.starbucks.com", "200 High Street, Cleveland, OH", "reserve@starbucks.com"),
            ("Starbucks Roastery", "coffee", "roastery.starbucks.com", "300 Lake Avenue, Cincinnati, OH", "roastery@starbucks.com"),
        ]
        records = []
        for i in range(20):
            template = base[i % len(base)]
            address_prefix, address_rest = template[3].split(",", 1)
            street = address_prefix.split(" ", 1)[1]
            records.append({
                "name": f"{template[0]} {i + 1}",
                "sic": "5812",
                "emp_size": str(25 + i * 10),
                "estimated_revenue": f"${0.8 + i * 0.15:.2f}M",
                "address": f"{100 + i} {street},{address_rest}",
                "email": template[4],
                "website": template[2],
            })
        revenue_values = [float(record["estimated_revenue"].removeprefix("$").removesuffix("M")) for record in records]
        employee_values = [int(record["emp_size"]) for record in records]
        return self._new_search(
            "business",
            arguments,
            records,
            20,
            {
                "scope": "all matching records, not only the masked previews",
                "total_count": 20,
                "matched_location": location,
                "matched_name": name,
                "sic_distribution": {"5812": 20},
                "median_estimated_revenue": f"${median(revenue_values):.2f}M",
                "median_employee_size": int(median(employee_values)),
                "employee_size_range": f"{min(employee_values)}-{max(employee_values)}",
            },
            ["name", "email", "website", "address"],
        )

    def search_consumer(self, arguments: dict[str, Any]) -> dict[str, Any]:
        income_filter = _value(arguments, "income") or "more than 20000"
        city = _value(arguments, "city") or "Columbus"
        threshold = _number_from_text(income_filter) or 20000
        records = [
            {"name": f"Jordan Consumer {i + 1}", "age": str(25 + i), "income": f"${threshold + 5000 + i * 1500}", "email": f"consumer{i + 1}@example.com", "address": f"{10 + i} Broad Street, {city}, OH"}
            for i in range(20)
        ]
        income_values = [int(record["income"].removeprefix("$").replace(",", "")) for record in records]
        age_values = [int(record["age"]) for record in records]
        return self._new_search("consumer", arguments, records, 20, {
            "scope": "all matching records, not only the masked previews",
            "total_count": 20,
            "matched_city": city,
            "income_filter": income_filter,
            "minimum_income_used": threshold,
            "median_income": f"${int(median(income_values)):,}",
            "income_range": f"${min(income_values):,}-${max(income_values):,}",
            "age_range": f"{min(age_values)}-{max(age_values)}",
        }, ["name", "email", "address"])

    def search_contact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job_title = _value(arguments, "job_title") or "manager"
        company = _value(arguments, "company_name") or "Any company"
        records = [
            {"name": f"Alex Manager {i + 1}", "business_name": f"Ohio Business {i + 1}", "sic_code": "5812", "job_title": job_title.title(), "email_address": f"manager{i + 1}@example.com"}
            for i in range(20)
        ]
        return self._new_search("contact", arguments, records, 20, {
            "scope": "all matching records, not only the masked previews",
            "total_count": 20,
            "matched_company": company,
            "matched_job_title": job_title,
            "job_title_distribution": {job_title.title(): 20},
            "sic_distribution": {"5812": 20},
            "businesses_represented": 20,
        }, ["name", "email_address", "business_name"])

    def purchase(self, arguments: dict[str, Any], kind: str) -> dict[str, Any]:
        search_id = _value(arguments, "search_id")
        count = arguments.get("count")
        confirm = arguments.get("confirm", False)
        if not search_id or search_id not in self.searches:
            raise ValueError("A valid search_id from a previous search is required.")
        if self.searches[search_id]["kind"] != kind:
            raise ValueError(f"{search_id} belongs to a different search type.")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("count must be a positive integer.")

        if self.credits == 0:
            return text_result({
                "status": "no_credits",
                "error": "No credits left. No records were revealed.",
                "credits_available": 0,
                "top_up_url": TOP_UP_URL,
            }, is_error=True)
        if not confirm:
            return text_result({
                "status": "confirmation_required",
                "message": "User permission is required before revealing records.",
                "requested_records": count,
                "credits_required": count,
                "credits_available": self.credits,
                "partial_reveal_possible": min(count, self.credits),
                "confirm_parameter": "Call this purchase tool again with confirm=true only after the user approves.",
            })

        reveal_count = min(count, self.credits, len(self.searches[search_id]["records"]))
        records = self.searches[search_id]["records"][:reveal_count]
        self.credits -= reveal_count
        payload: dict[str, Any] = {
            "status": "partial_success" if reveal_count < count else "success",
            "records": [self._core_record(kind, record) for record in records],
            "requested_records": count,
            "records_returned": reveal_count,
            "credits_deducted": reveal_count,
            "credits_remaining": self.credits,
        }
        if reveal_count < count:
            payload.update({
                "error": f"Insufficient credits. Returned {reveal_count} of {count} requested records.",
                "top_up_url": TOP_UP_URL,
            })
        return text_result(payload)

    @staticmethod
    def _core_record(kind: str, record: dict[str, Any]) -> dict[str, Any]:
        fields = {
            "business": ["name", "sic", "emp_size", "estimated_revenue", "address", "email"],
            "consumer": ["name", "age", "income", "email", "address"],
            "contact": ["name", "business_name", "sic_code", "job_title", "email_address"],
        }[kind]
        return {key: record[key] for key in fields}


def build_server() -> StdioMCPServer:
    demo = PaidDemo()
    common_search = {
        "business_name": {"type": "string", "description": "Optional business name, e.g. Starbucks."},
        "sic_code": {"type": "string", "description": "Optional SIC code filter."},
        "street": {"type": "string", "description": "Optional street filter."},
        "city": {"type": "string", "description": "Optional city filter. City is not required."},
        "zip": {"type": "string", "description": "Optional ZIP code filter."},
        "revenue": {"type": "string", "description": "Optional revenue filter."},
    }
    consumer_search = {
        "city": {"type": "string", "description": "Optional city filter."}, "state": {"type": "string", "description": "Optional state filter."}, "name": {"type": "string", "description": "Optional consumer name filter."}, "income": {"type": "string", "description": "Optional income filter, e.g. more than 20000."}, "age": {"type": "string", "description": "Optional age filter."},
    }
    contact_search = {"company_name": {"type": "string", "description": "Optional company name filter."}, "industry": {"type": "string", "description": "Optional industry filter."}, "job_title": {"type": "string", "description": "Optional job title filter."}}
    purchase_props = {"search_id": {"type": "string"}, "count": {"type": "integer", "minimum": 1}, "confirm": {"type": "boolean", "description": "Must be true only after the user gives permission to reveal records."}}
    tools = [
        tool("search_business", "Search businesses. All filters are optional, including city. The search never reveals full records. Recommended workflow: 1) Return the 10 masked samples to the user together with total matches, aggregate insights for the full result set, and current credits. 2) Ask how many records the user wants revealed. 3) Explain that one credit will be deducted per record and ask for explicit permission. 4) Only after the user provides the number and permission, call purchase_business with this search_id, the requested count, and confirm=true.", common_search),
        tool("search_consumer", "Search consumers. All filters are optional. The search never reveals full records. Recommended workflow: 1) Return the 10 masked samples to the user together with total matches, aggregate insights for the full result set, and current credits. 2) Ask how many records the user wants revealed. 3) Explain that one credit will be deducted per record and ask for explicit permission. 4) Only after the user provides the number and permission, call purchase_consumer with this search_id, the requested count, and confirm=true.", consumer_search),
        tool("search_contact", "Search contacts. All filters are optional. The search never reveals full records. Recommended workflow: 1) Return the 10 masked samples to the user together with total matches, aggregate insights for the full result set, and current credits. 2) Ask how many records the user wants revealed. 3) Explain that one credit will be deducted per record and ask for explicit permission. 4) Only after the user provides the number and permission, call purchase_contact with this search_id, the requested count, and confirm=true.", contact_search),
        tool("purchase_business", "Workflow: call search_business first and use its returned search_id. Do not call this purchase tool without a prior search. After the user provides a record count and explicit permission, call this tool with confirm=true. It costs one credit per returned record and reports credits deducted and remaining.", purchase_props, ["search_id", "count", "confirm"]),
        tool("purchase_consumer", "Workflow: call search_consumer first and use its returned search_id. Do not call this purchase tool without a prior search. After the user provides a record count and explicit permission, call this tool with confirm=true. It costs one credit per returned record and reports credits deducted and remaining.", purchase_props, ["search_id", "count", "confirm"]),
        tool("purchase_contact", "Workflow: call search_contact first and use its returned search_id. Do not call this purchase tool without a prior search. After the user provides a record count and explicit permission, call this tool with confirm=true. It costs one credit per returned record and reports credits deducted and remaining.", purchase_props, ["search_id", "count", "confirm"]),
    ]
    return StdioMCPServer(
        name="paid-data-demo",
        version="1.0.0",
        tools=tools,
        handlers={
            "search_business": demo.search_business,
            "search_consumer": demo.search_consumer,
            "search_contact": demo.search_contact,
            "purchase_business": lambda args: demo.purchase(args, "business"),
            "purchase_consumer": lambda args: demo.purchase(args, "consumer"),
            "purchase_contact": lambda args: demo.purchase(args, "contact"),
        },
    )


if __name__ == "__main__":
    build_server().run()
