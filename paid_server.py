"""Paid MCP demo: searches, bulk matching, enrichment, and credit-gated reveals."""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from server_common import StdioMCPServer, text_result, tool


TOP_UP_URL = "https://teampitstop.wixsite.com/home"
INITIAL_CREDITS = 15


def _mask(value: str) -> str:
    value = str(value)
    return value if len(value) <= 2 else value[:2] + "*" * max(4, len(value) - 2)


def _value(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    return str(value).strip() if value is not None else ""


def _number_from_text(value: str) -> int | None:
    match = re.search(r"\d[\d,]*", value)
    return int(match.group(0).replace(",", "")) if match else None


def _record_value(record: dict[str, Any], *keys: str) -> str:
    """Read common CSV/JSON field aliases without relying on the LLM to normalize them."""
    normalized = {str(key).strip().lower(): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _address(record: dict[str, Any], *, business: bool = False) -> str:
    full_keys = ("business_full_address", "full_address", "address") if business else ("full_address", "address")
    full = _record_value(record, *full_keys)
    if full:
        return full
    prefix = "business_" if business else ""
    parts = [
        _record_value(record, f"{prefix}street", "street"),
        _record_value(record, f"{prefix}city", "city"),
        _record_value(record, f"{prefix}state", "state"),
        _record_value(record, f"{prefix}zip", "zip", "postal_code"),
    ]
    return ", ".join(part for part in parts if part)


def _has_full_address(record: dict[str, Any], *, business: bool = False) -> bool:
    full_keys = ("business_full_address", "full_address", "address") if business else ("full_address", "address")
    full = _record_value(record, *full_keys)
    if full:
        # Reject values such as a street-only string while accepting the compact
        # city/state/ZIP format used by the sample CSVs.
        return len(full.split()) >= 4 and bool(re.search(r"\d", full))
    prefix = "business_" if business else ""
    return all(
        _record_value(record, f"{prefix}{part}", part, "postal_code" if part == "zip" else part)
        for part in ("street", "city", "state", "zip")
    )


def _complete_match_record(kind: str, record: dict[str, Any]) -> bool:
    if kind == "business":
        return bool(
            _record_value(record, "business_name", "name")
            and _has_full_address(record)
            and _record_value(record, "website", "email", "phone")
        )
    if kind == "consumer":
        return bool(
            _record_value(record, "full_name", "name")
            or (_record_value(record, "first_name") and _record_value(record, "last_name"))
        ) and _has_full_address(record)
    if kind == "contact":
        return bool(
            _record_value(record, "contact_first_name", "first_name")
            and _record_value(record, "contact_last_name", "last_name")
            and _record_value(record, "job_title")
            and _record_value(record, "business_name", "company_name")
            and _has_full_address(record, business=True)
        )
    raise ValueError(f"Unsupported match type: {kind}")


def _match_label(kind: str) -> str:
    return {"business": "business", "consumer": "consumer", "contact": "contact"}[kind]


class PaidDemo:
    def __init__(self) -> None:
        self.credits = INITIAL_CREDITS
        self.sequence = 0
        self.searches: dict[str, dict[str, Any]] = {}
        self.match_sequence = 0
        self.matches: dict[str, dict[str, Any]] = {}

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
        }

    def search_business(self, arguments: dict[str, Any]) -> dict[str, Any]:
        name = _value(arguments, "business_name") or "Starbucks"
        city = _value(arguments, "city")
        state = _value(arguments, "state")
        location = city or state or "Ohio"
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
                "matched_city": city or None,
                "matched_state": state or None,
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

    def match(self, arguments: dict[str, Any], kind: str) -> dict[str, Any]:
        records = arguments.get("records")
        if not isinstance(records, list):
            raise ValueError("records must be an array of rows parsed from the uploaded file.")
        if len(records) > 100:
            raise ValueError("A maximum of 100 records can be matched in one call.")
        if not records:
            raise ValueError("records must contain at least one row.")
        if any(not isinstance(record, dict) for record in records):
            raise ValueError("Each records item must be an object representing one uploaded row.")

        self.match_sequence += 1
        match_id = f"match-{kind}-{self.match_sequence:03d}"
        matched_records = [record for record in records if _complete_match_record(kind, record)]
        dropped_records = [
            {"record_number": index + 1, "record_id": _record_value(record, "record_id", "id"), "reason": "insufficient_fields"}
            for index, record in enumerate(records)
            if not _complete_match_record(kind, record)
        ]
        self.matches[match_id] = {"kind": kind, "records": matched_records}
        matched_count = len(matched_records)
        return {
            "status": "match_complete",
            "match_id": match_id,
            "entity": _match_label(kind),
            "total_submitted": len(records),
            "matched_count": matched_count,
            "dropped_count": len(dropped_records),
            "dropped_records": dropped_records,
            "permission_message": "1 credit per record will be deducted, do you want me to proceed?",
            "next_step": f"If the user gives permission, call enrich_{kind} with this exact match_id, the requested record count, and confirm=true.",
        }

    def enrich(self, arguments: dict[str, Any], kind: str) -> dict[str, Any]:
        match_id = _value(arguments, "match_id")
        count = arguments.get("count")
        confirm = arguments.get("confirm", False)
        match = self.matches.get(match_id)
        if not match_id or match is None:
            raise ValueError("A valid match_id from a previous matching tool is required.")
        if match["kind"] != kind:
            raise ValueError(f"{match_id} belongs to a different match type.")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("count must be a positive integer.")
        if self.credits == 0:
            return text_result({
                "status": "no_credits",
                "error": "No credits left. No records were enriched.",
                "records": [],
                "credits_available": 0,
                "top_up_url": TOP_UP_URL,
            }, is_error=True)
        if not confirm:
            return text_result({
                "status": "confirmation_required",
                "message": "User permission is required before enriching records.",
                "requested_records": count,
                "credits_required": count,
                "credits_available": self.credits,
                "confirm_parameter": "Call this enrichment tool again with confirm=true only after the user approves.",
            })
        chargeable_count = min(count, len(match["records"]))
        if chargeable_count == 0:
            return text_result({
                "status": "no_matches",
                "message": "No complete matched records are available to enrich.",
                "records": [],
                "requested_records": count,
                "credits_remaining": self.credits,
            })
        if chargeable_count > self.credits:
            return text_result({
                "status": "insufficient_credits",
                "error": f"Insufficient credits. You can only enrich {self.credits} records with your remaining credits, or buy credits from the top-up page.",
                "records": [],
                "requested_records": count,
                "available_records": self.credits,
                "credits_available": self.credits,
                "top_up_url": TOP_UP_URL,
                "next_step": f"If the user says go ahead with {self.credits} records, call this tool again with count={self.credits} and confirm=true.",
            }, is_error=True)

        reveal_count = chargeable_count
        records = [self._enriched_record(kind, record, index) for index, record in enumerate(match["records"][:reveal_count])]
        self.credits -= reveal_count
        return text_result({
            "status": "partial_success" if reveal_count < count else "success",
            "records": records,
            "requested_records": count,
            "records_returned": reveal_count,
            "credits_deducted": reveal_count,
            "credits_remaining": self.credits,
        })

    @staticmethod
    def _enriched_record(kind: str, record: dict[str, Any], index: int) -> dict[str, Any]:
        number = index + 1
        if kind == "business":
            name = _record_value(record, "business_name", "name") or f"Matched Business {number}"
            return {
                "name": name,
                "sic": _record_value(record, "sic", "sic_code") or "5812",
                "emp_size": str(50 + index * 10),
                "estimated_revenue": f"${1.2 + index * 0.2:.2f}M",
                "address": _address(record),
                "email": _record_value(record, "email") or f"business{number}@example.com",
            }
        if kind == "consumer":
            name = _record_value(record, "full_name", "name") or " ".join(filter(None, [_record_value(record, "first_name"), _record_value(record, "last_name")]))
            return {
                "name": name or f"Matched Consumer {number}",
                "age": _record_value(record, "age") or str(30 + index),
                "income": _record_value(record, "income") or f"${35000 + index * 2500}",
                "email": _record_value(record, "email") or f"consumer{number}@example.com",
                "address": _address(record),
            }
        name = _record_value(record, "full_name", "name") or " ".join(filter(None, [_record_value(record, "contact_first_name", "first_name"), _record_value(record, "contact_last_name", "last_name")]))
        return {
            "name": name or f"Matched Contact {number}",
            "business_name": _record_value(record, "business_name", "company_name") or f"Matched Business {number}",
            "sic_code": _record_value(record, "sic_code", "sic") or "5812",
            "job_title": _record_value(record, "job_title"),
            "email_address": _record_value(record, "email", "email_address") or f"contact{number}@example.com",
        }

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

        if count > self.credits:
            return text_result({
                "status": "insufficient_credits",
                "error": f"You can reveal only {self.credits} records with your remaining credits, or top up credits.",
                "records": [],
                "requested_records": count,
                "available_records": self.credits,
                "credits_available": self.credits,
                "top_up_url": TOP_UP_URL,
                "next_step": f"If the user says go ahead with {self.credits} records, call this purchase tool again with count={self.credits} and confirm=true.",
            }, is_error=True)

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
        "city": {"type": "string", "description": "Optional city filter. Use this only when the user names a city."},
        "state": {"type": "string", "description": "Optional state filter. Use this when the user names a state, such as Ohio."},
        "zip": {"type": "string", "description": "Optional ZIP code filter."},
        "revenue": {"type": "string", "description": "Optional revenue filter."},
    }
    consumer_search = {
        "city": {"type": "string", "description": "Optional city filter."}, "state": {"type": "string", "description": "Optional state filter."}, "name": {"type": "string", "description": "Optional consumer name filter."}, "income": {"type": "string", "description": "Optional income filter, e.g. more than 20000."}, "age": {"type": "string", "description": "Optional age filter."},
    }
    contact_search = {"company_name": {"type": "string", "description": "Optional company name filter."}, "industry": {"type": "string", "description": "Optional industry filter."}, "job_title": {"type": "string", "description": "Optional job title filter."}}
    purchase_props = {
        "search_id": {"type": "string", "description": "Copy this value exactly from the immediately preceding matching search response. This is internal workflow state; never ask the user to provide it and never invent or transform it."},
        "count": {"type": "integer", "minimum": 1, "description": "Use the number requested by the user."},
        "confirm": {"type": "boolean", "description": "Set true when the user provides a number of records to reveal; the number is the permission signal. Do not ask a separate yes/no question."},
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
        "match_id": {"type": "string", "description": "Copy this value exactly from the preceding matching tool response. Never ask the user for it and never invent or transform it."},
        "count": {"type": "integer", "minimum": 1, "description": "Use the number of matched records the user authorized for enrichment."},
        "confirm": {"type": "boolean", "description": "Set true only when the user has provided the number of records to enrich; the number is the permission signal."},
    }
    match_description = {
        "business": "Match uploaded business rows. Required matching data is business name plus full address plus website, email, or phone.",
        "consumer": "Match uploaded consumer rows. Required matching data is consumer name plus full address.",
        "contact": "Match uploaded contact rows. Required matching data is contact first name, last name, job title, business name, and business full address. Return and enrich all contacts, not only primary contacts.",
    }
    enrich_description = {
        "business": "Enrich business rows from a previous match_business call. Return name, SIC, employee size, estimated revenue, address, and email.",
        "consumer": "Enrich consumer rows from a previous match_consumer call. Return name, age, income, email, and address.",
        "contact": "Enrich all matched contacts from a previous match_contact call, including primary and secondary contacts. Return name, business name, SIC code, job title, and email address.",
    }
    tools = [
        tool("search_business", "Search businesses. All filters are optional. Preserve every filter the user explicitly states: map a named city to city, and map a named state such as Ohio to state; do not put a state in city. The search never reveals full records. Recommended workflow: 1) Display all 10 masked samples to the user. 2) Show total matches and aggregate insights. 3) Ask the user how many records they want to reveal and state that each record consumes 1 credit. 4) If the user provides a number, treat it as permission and call purchase_business with the exact search_id returned by this search, the requested count, and confirm=true. If the user does not provide a number, do not call purchase_business.", common_search),
        tool("search_consumer", "Search consumers. All filters are optional. The search never reveals full records. Recommended workflow: 1) Display all 10 masked samples to the user. 2) Show total matches and aggregate insights. 3) Ask the user how many records they want to reveal and state that each record consumes 1 credit. 4) If the user provides a number, treat it as permission and call purchase_consumer with the exact search_id returned by this search, the requested count, and confirm=true. If the user does not provide a number, do not call purchase_consumer.", consumer_search),
        tool("search_contact", "Search contacts. All filters are optional. The search never reveals full records. Recommended workflow: 1) Display all 10 masked samples to the user. 2) Show total matches and aggregate insights. 3) Ask the user how many records they want to reveal and state that each record consumes 1 credit. 4) If the user provides a number, treat it as permission and call purchase_contact with the exact search_id returned by this search, the requested count, and confirm=true. If the user does not provide a number, do not call purchase_contact.", contact_search),
        tool("purchase_business", "Workflow: call search_business first. Copy the exact search_id from that response; never ask the user for it, invent it, or transform it. Do not call this tool unless the user provided a record count; the count is the permission signal. Then call with confirm=true. If requested count exceeds available credits, return the insufficient-credit error with no records and ask whether to proceed with the available count or top up. Only reveal records after the user chooses the available count. If at least one record is returned, explicitly show credits_deducted and credits_remaining.", purchase_props, ["search_id", "count", "confirm"]),
        tool("purchase_consumer", "Workflow: call search_consumer first. Copy the exact search_id from that response; never ask the user for it, invent it, or transform it. Do not call this tool unless the user provided a record count; the count is the permission signal. Then call with confirm=true. If requested count exceeds available credits, return the insufficient-credit error with no records and ask whether to proceed with the available count or top up. Only reveal records after the user chooses the available count. If at least one record is returned, explicitly show credits_deducted and credits_remaining.", purchase_props, ["search_id", "count", "confirm"]),
        tool("purchase_contact", "Workflow: call search_contact first. Copy the exact search_id from that response; never ask the user for it, invent it, or transform it. Do not call this tool unless the user provided a record count; the count is the permission signal. Then call with confirm=true. If requested count exceeds available credits, return the insufficient-credit error with no records and ask whether to proceed with the available count or top up. Only reveal records after the user chooses the available count. If at least one record is returned, explicitly show credits_deducted and credits_remaining.", purchase_props, ["search_id", "count", "confirm"]),
        tool("match_business", f"{match_description['business']} Pass rows parsed from the file uploaded in Claude; MCP validates fields and does not receive a file path. Process up to 100 rows. Return matched and dropped counts, identify incomplete rows, then display: 1 credit per record will be deducted, do you want me to proceed? Call enrich_business only after the user provides permission and a number.", match_props, ["records"]),
        tool("match_consumer", f"{match_description['consumer']} Pass rows parsed from the file uploaded in Claude; MCP validates fields and does not receive a file path. Process up to 100 rows. Return matched and dropped counts, identify incomplete rows, then display: 1 credit per record will be deducted, do you want me to proceed? Call enrich_consumer only after the user provides permission and a number.", match_props, ["records"]),
        tool("match_contact", f"{match_description['contact']} Pass rows parsed from the file uploaded in Claude; MCP validates fields and does not receive a file path. Process up to 100 rows. Return matched and dropped counts, identify incomplete rows, then display: 1 credit per record will be deducted, do you want me to proceed? Call enrich_contact only after the user provides permission and a number.", match_props, ["records"]),
        tool("enrich_business", f"Workflow: call match_business first and copy its exact match_id; never ask the user for it. {enrich_description['business']} Do not call unless the user has provided a record count as permission. Call with confirm=true. If credits are insufficient, return no records first and offer the available count or the top-up URL. If any records are returned, explicitly show credits_deducted and credits_remaining.", enrich_props, ["match_id", "count", "confirm"]),
        tool("enrich_consumer", f"Workflow: call match_consumer first and copy its exact match_id; never ask the user for it. {enrich_description['consumer']} Do not call unless the user has provided a record count as permission. Call with confirm=true. If credits are insufficient, return no records first and offer the available count or the top-up URL. If any records are returned, explicitly show credits_deducted and credits_remaining.", enrich_props, ["match_id", "count", "confirm"]),
        tool("enrich_contact", f"Workflow: call match_contact first and copy its exact match_id; never ask the user for it. {enrich_description['contact']} Do not call unless the user has provided a record count as permission. Call with confirm=true. If credits are insufficient, return no records first and offer the available count or the top-up URL. If any records are returned, explicitly show credits_deducted and credits_remaining.", enrich_props, ["match_id", "count", "confirm"]),
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
            "match_business": lambda args: demo.match(args, "business"),
            "match_consumer": lambda args: demo.match(args, "consumer"),
            "match_contact": lambda args: demo.match(args, "contact"),
            "enrich_business": lambda args: demo.enrich(args, "business"),
            "enrich_consumer": lambda args: demo.enrich(args, "consumer"),
            "enrich_contact": lambda args: demo.enrich(args, "contact"),
        },
    )


if __name__ == "__main__":
    build_server().run()
