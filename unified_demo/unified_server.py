"""Unified authenticated HSB MCP demo.

This is a self-contained v2 demo. It does not import or modify the original
paid_server.py or freemium_server.py modules.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import secrets
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse


TOP_UP_URL = "https://teampitstop.wixsite.com/home"
INITIAL_CREDITS = 15
MAX_BULK_RECORDS = 100
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOLS = {"2025-06-18", "2025-03-26", "2024-11-05"}
RESOURCE_URI = "mcp://hsb/unified-auth-enrichment-workflow"

DEMO_USERS = {
    "paid@example.com": {"password": "paid-demo", "plan": "paid", "display_name": "Paid Demo User"},
    "freemium@example.com": {"password": "freemium-demo", "plan": "freemium", "display_name": "Freemium Demo User"},
}
ALLOWED_OAUTH_REDIRECT_URIS = {"https://claude.ai/api/mcp/auth_callback"}


def _json(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _text_result(payload: dict[str, Any], *, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": error}


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _mask(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 2 else text[:2] + "*" * max(4, len(text) - 2)


def _value(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    return str(value).strip() if value is not None else ""


def _number(value: str) -> int | None:
    match = re.search(r"\d[\d,]*", value)
    return int(match.group(0).replace(",", "")) if match else None


def _record_value(record: dict[str, Any], *keys: str) -> str:
    values = {str(key).strip().lower(): value for key, value in record.items()}
    for key in keys:
        value = values.get(key.lower())
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


def _has_address(record: dict[str, Any], *, business: bool = False) -> bool:
    full = _address(record, business=business)
    return bool(full and len(full.split()) >= 4 and re.search(r"\d", full))


def _is_match(kind: str, record: dict[str, Any]) -> bool:
    if kind == "business":
        return bool(_record_value(record, "business_name", "name") and _has_address(record) and _record_value(record, "website", "email", "phone"))
    if kind == "consumer":
        has_name = bool(_record_value(record, "full_name", "name") or (_record_value(record, "first_name") and _record_value(record, "last_name")))
        return has_name and _has_address(record)
    if kind == "contact":
        return bool(
            _record_value(record, "contact_first_name", "first_name")
            and _record_value(record, "contact_last_name", "last_name")
            and _record_value(record, "job_title")
            and _record_value(record, "business_name", "company_name")
            and _has_address(record, business=True)
        )
    raise ValueError(f"Unknown entity type: {kind}")


def _verified(records: list[dict[str, Any]], flag: str) -> int:
    return sum(1 for record in records if record.get(flag) is True)


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": _schema(properties, required)}


def _workflow_text() -> str:
    return (Path(__file__).resolve().parent / "skill" / "SKILL.md").read_text(encoding="utf-8")


class DemoState:
    def __init__(self, email: str, plan: str) -> None:
        self.email = email
        self.plan = plan
        self.credits = INITIAL_CREDITS if plan == "paid" else None
        self.sequence = 0
        self.searches: dict[str, dict[str, Any]] = {}
        self.enrichment_sequence = 0
        self.enrichments: dict[str, dict[str, Any]] = {}


class UnifiedMCP:
    def __init__(self) -> None:
        self.states: dict[str, DemoState] = {}
        self.lock = threading.Lock()
        self.tools = self._tools()
        self.prompts = self._prompts()

    def state_for(self, token: str) -> DemoState:
        with self.lock:
            if token not in self.states:
                user = TOKENS.get(token)
                if user is None:
                    raise ValueError("Invalid or expired access token.")
                self.states[token] = DemoState(user["email"], user["plan"])
            return self.states[token]

    def _new_search(self, state: DemoState, kind: str, records: list[dict[str, Any]], insights: dict[str, Any], preview_fields: list[str]) -> dict[str, Any]:
        state.sequence += 1
        search_id = f"{kind}-{state.sequence:03d}"
        state.searches[search_id] = {"kind": kind, "records": records}
        return {
            "status": "search_complete",
            "search_id": search_id,
            "total_matches": len(records),
            "masked_samples": [{field: _mask(record[field]) for field in preview_fields} for record in records[:10]],
            "insights": insights,
        }

    def search_business(self, state: DemoState, arguments: dict[str, Any]) -> dict[str, Any]:
        name = _value(arguments, "business_name") or "Starbucks"
        city = _value(arguments, "city")
        state_name = _value(arguments, "state")
        location = city or state_name or "Ohio"
        records = []
        for i in range(20):
            records.append({
                "name": f"{name} {i + 1}", "sic": "5812", "emp_size": str(25 + i * 10),
                "estimated_revenue": f"${0.8 + i * 0.15:.2f}M", "address": f"{100 + i} Main Street, {location}",
                "email": f"business{i + 1}@example.com", "website": "https://business.example.com",
                "phone": f"614-555-{1000 + i:04d}", "email_verified": i % 4 != 0, "phone_verified": i % 5 != 0,
            })
        revenues = [float(r["estimated_revenue"].removeprefix("$").removesuffix("M")) for r in records]
        employees = [int(r["emp_size"]) for r in records]
        insights = {
            "scope": "all matching records, not only the masked previews", "total_count": 20,
            "matched_name": name, "matched_city": city or None, "matched_state": state_name or None,
            "matched_location": location, "sic_distribution": {"5812": 20},
            "median_estimated_revenue": f"${median(revenues):.2f}M", "median_employee_size": int(median(employees)),
            "employee_size_range": f"{min(employees)}-{max(employees)}",
            "total_verified_emails": _verified(records, "email_verified"),
            "total_verified_phone_numbers": _verified(records, "phone_verified"),
        }
        return self._new_search(state, "business", records, insights, ["name", "email", "website", "address"])

    def search_consumer(self, state: DemoState, arguments: dict[str, Any]) -> dict[str, Any]:
        income_filter = _value(arguments, "income") or "more than 20000"
        city = _value(arguments, "city") or "Columbus"
        threshold = _number(income_filter) or 20000
        records = [{
            "name": f"Jordan Consumer {i + 1}", "age": str(25 + i), "income": f"${threshold + 5000 + i * 1500}",
            "email": f"consumer{i + 1}@example.com", "phone": f"614-555-{2000 + i:04d}",
            "email_verified": i % 5 != 0, "phone_verified": i % 4 != 0,
            "address": f"{10 + i} Broad Street, {city}, OH",
        } for i in range(20)]
        incomes = [int(r["income"].removeprefix("$").replace(",", "")) for r in records]
        ages = [int(r["age"]) for r in records]
        insights = {
            "scope": "all matching records, not only the masked previews", "total_count": 20, "matched_city": city,
            "income_filter": income_filter, "minimum_income_used": threshold, "median_income": f"${int(median(incomes)):,}",
            "income_range": f"${min(incomes):,}-${max(incomes):,}", "age_range": f"{min(ages)}-{max(ages)}",
            "total_verified_emails": _verified(records, "email_verified"),
            "total_verified_phone_numbers": _verified(records, "phone_verified"),
        }
        return self._new_search(state, "consumer", records, insights, ["name", "email", "address"])

    def search_contact(self, state: DemoState, arguments: dict[str, Any]) -> dict[str, Any]:
        job_title = _value(arguments, "job_title") or "manager"
        company = _value(arguments, "company_name") or "Any company"
        records = [{
            "name": f"Alex Manager {i + 1}", "business_name": f"Ohio Business {i + 1}", "sic_code": "5812",
            "job_title": job_title.title(), "email_address": f"manager{i + 1}@example.com",
            "phone": f"614-555-{3000 + i:04d}", "email_verified": i % 6 != 0, "phone_verified": i % 3 != 0,
        } for i in range(20)]
        insights = {
            "scope": "all matching records, not only the masked previews", "total_count": 20,
            "matched_company": company, "matched_job_title": job_title, "job_title_distribution": {job_title.title(): 20},
            "sic_distribution": {"5812": 20}, "businesses_represented": 20,
            "total_verified_emails": _verified(records, "email_verified"),
            "total_verified_phone_numbers": _verified(records, "phone_verified"),
        }
        return self._new_search(state, "contact", records, insights, ["name", "email_address", "business_name"])

    def purchase(self, state: DemoState, arguments: dict[str, Any], kind: str) -> dict[str, Any]:
        search_id = _value(arguments, "search_id")
        count = arguments.get("count")
        confirm = arguments.get("confirm", False)
        search = state.searches.get(search_id)
        if search is None or search["kind"] != kind:
            raise ValueError("Use the exact search_id returned by the matching search tool.")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("count must be a positive integer.")
        if state.plan == "freemium":
            return _text_result({"status": "upgrade_required", "error": "You don't have an active paid subscription. Buy credits or upgrade to a Pro or Teams plan to reveal records.", "upgrade_url": TOP_UP_URL, "records": []}, error=True)
        if state.credits == 0:
            return _text_result({"status": "no_credits", "error": "No credits left. No records were revealed.", "records": [], "credits_available": 0, "top_up_url": TOP_UP_URL}, error=True)
        if not confirm:
            return _text_result({"status": "confirmation_required", "message": "User permission is required before revealing records.", "requested_records": count, "credits_required": count, "credits_available": state.credits})
        if count > state.credits:
            reveal_count = min(state.credits, len(search["records"]))
            records = [self._core_record(kind, record) for record in search["records"][:reveal_count]]
            state.credits -= reveal_count
            return _text_result({
                "status": "insufficient_credits",
                "error": f"Insufficient credits: you requested {count} records, but only {reveal_count} could be returned with your remaining credits. Top up credits to reveal more.",
                "records": records,
                "records_returned": reveal_count,
                "available_records": reveal_count,
                "credits_deducted": reveal_count,
                "credits_remaining": state.credits,
                "top_up_url": TOP_UP_URL,
            }, error=True)
        reveal_count = min(count, len(search["records"]))
        records = [self._core_record(kind, record) for record in search["records"][:reveal_count]]
        state.credits -= reveal_count
        return _text_result({"status": "success", "records": records, "records_returned": reveal_count, "credits_deducted": reveal_count, "credits_remaining": state.credits})

    def enrich(self, state: DemoState, arguments: dict[str, Any], kind: str) -> dict[str, Any]:
        enrichment_id = _value(arguments, "enrichment_id")
        records = arguments.get("records")
        count = arguments.get("count")
        confirm = arguments.get("confirm", False)
        if not enrichment_id:
            if not isinstance(records, list) or not records:
                raise ValueError("Pass the user's own records in records for the first enrichment call.")
            if len(records) > MAX_BULK_RECORDS:
                raise ValueError("A maximum of 100 records can be enriched in one call.")
            if any(not isinstance(record, dict) for record in records):
                raise ValueError("Each records item must be an object.")
            state.enrichment_sequence += 1
            enrichment_id = f"enrich-{kind}-{state.enrichment_sequence:03d}"
            state.enrichments[enrichment_id] = {"kind": kind, "records": records}
            return _text_result({
                "status": "permission_required", "enrichment_id": enrichment_id, "entity": kind,
                "permission_message": "Each matched record will consume 1 credit; non-matched records consume no credits. Do you want me to proceed?",
                "next_step": f"After the user gives permission, call enrich_{kind} again with this exact enrichment_id and confirm=true. Include count only if the user requested a specific number; otherwise enrich all matched records.",
            })
        enrichment = state.enrichments.get(enrichment_id)
        if enrichment is None or enrichment["kind"] != kind:
            raise ValueError("Use the exact enrichment_id returned by the corresponding enrichment tool.")
        if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 1):
            raise ValueError("count must be a positive integer when provided.")
        if not confirm:
            return _text_result({"status": "confirmation_required", "message": "User permission is required before enriching records."})
        if state.plan == "freemium":
            return _text_result({"status": "upgrade_required", "error": "You don't have an active paid subscription. Buy credits or upgrade to a Pro or Teams plan to enrich records.", "upgrade_url": TOP_UP_URL, "records": []}, error=True)
        if state.credits == 0:
            return _text_result({"status": "no_credits", "error": "No credits left. No records were enriched.", "records": [], "credits_available": 0, "top_up_url": TOP_UP_URL}, error=True)
        matched_records = [record for record in enrichment["records"] if _is_match(kind, record)]
        requested_count = count if count is not None else len(matched_records)
        chargeable = min(requested_count, len(matched_records))
        partial = chargeable > state.credits
        if partial:
            chargeable = state.credits
        enriched = [self._enriched_record(kind, record, index) for index, record in enumerate(matched_records[:chargeable])]
        state.credits -= chargeable
        if partial:
            return _text_result({
                "status": "insufficient_credits",
                "error": f"Insufficient credits: you requested {requested_count} records, but only {chargeable} could be enriched with your remaining credits. Top up credits to enrich more.",
                "records": enriched,
                "records_returned": chargeable,
                "available_records": chargeable,
                "credits_deducted": chargeable,
                "credits_remaining": state.credits,
                "top_up_url": TOP_UP_URL,
            }, error=True)
        return _text_result({"status": "success", "records": enriched, "records_returned": chargeable, "credits_deducted": chargeable, "credits_remaining": state.credits})

    @staticmethod
    def _core_record(kind: str, record: dict[str, Any]) -> dict[str, Any]:
        fields = {"business": ["name", "sic", "emp_size", "estimated_revenue", "address", "email"], "consumer": ["name", "age", "income", "email", "address"], "contact": ["name", "business_name", "sic_code", "job_title", "email_address"]}[kind]
        return {key: record[key] for key in fields}

    @staticmethod
    def _enriched_record(kind: str, record: dict[str, Any], index: int) -> dict[str, Any]:
        number = index + 1
        if kind == "business":
            return {"name": _record_value(record, "business_name", "name") or f"Matched Business {number}", "sic": _record_value(record, "sic", "sic_code") or "5812", "emp_size": str(50 + index * 10), "estimated_revenue": f"${1.2 + index * 0.2:.2f}M", "address": _address(record), "email": _record_value(record, "email") or f"business{number}@example.com"}
        if kind == "consumer":
            name = _record_value(record, "full_name", "name") or " ".join(filter(None, [_record_value(record, "first_name"), _record_value(record, "last_name")]))
            return {"name": name or f"Matched Consumer {number}", "age": _record_value(record, "age") or str(30 + index), "income": _record_value(record, "income") or f"${35000 + index * 2500}", "email": _record_value(record, "email") or f"consumer{number}@example.com", "address": _address(record)}
        name = _record_value(record, "full_name", "name") or " ".join(filter(None, [_record_value(record, "contact_first_name", "first_name"), _record_value(record, "contact_last_name", "last_name")]))
        return {"name": name or f"Matched Contact {number}", "business_name": _record_value(record, "business_name", "company_name") or f"Matched Business {number}", "sic_code": _record_value(record, "sic_code", "sic") or "5812", "job_title": _record_value(record, "job_title"), "email_address": _record_value(record, "email", "email_address") or f"contact{number}@example.com"}

    def _tools(self) -> list[dict[str, Any]]:
        search_common = {
            "business_name": {"type": "string", "description": "Optional business name."}, "sic_code": {"type": "string", "description": "Optional SIC code."}, "street": {"type": "string", "description": "Optional street."}, "city": {"type": "string", "description": "Optional city; do not use for a state."}, "state": {"type": "string", "description": "Optional state, such as Ohio."}, "zip": {"type": "string", "description": "Optional ZIP."}, "revenue": {"type": "string", "description": "Optional revenue filter."},
        }
        consumer_props = {"city": {"type": "string"}, "state": {"type": "string"}, "name": {"type": "string"}, "income": {"type": "string"}, "age": {"type": "string"}}
        contact_props = {"company_name": {"type": "string"}, "industry": {"type": "string"}, "job_title": {"type": "string"}}
        purchase = {"search_id": {"type": "string", "description": "Copy exactly from the preceding matching search response; never ask the user for it."}, "count": {"type": "integer", "minimum": 1}, "confirm": {"type": "boolean", "description": "Set true only after the user provides a record count as permission."}}
        enrich = {"records": {"type": "array", "maxItems": MAX_BULK_RECORDS, "description": "The user's own uploaded rows parsed by Claude. Do not use this tool for MCP-generated or provider-owned records.", "items": {"type": "object", "additionalProperties": True}}, "enrichment_id": {"type": "string", "description": "Copy exactly from the first call to this same enrichment tool."}, "count": {"type": "integer", "minimum": 1, "description": "Optional number of records the user authorized; omit to enrich all matched records."}, "confirm": {"type": "boolean", "description": "Set true only after the user gives permission."}}
        search_desc = "MUST display all 10 masked samples exactly as returned, then show total matches and full-result insights including verified email and phone counts. Ask how many records to reveal; if the user gives a number, call the matching purchase tool. If no number is given, do not purchase."
        enrich_desc = "Use only when the user brings their own uploaded records. This is the only enrichment step; there is no separate match tool or match report. First call with records to validate and hold the user's rows, but do not display matched or non-matched counts. Ask only for permission to proceed, explaining that each matched record consumes 1 credit and non-matches consume no credits. Do not call the second phase until the user gives permission. Then call this same tool with the exact enrichment_id and confirm=true; include count only when the user requested a specific number, otherwise omit it to enrich all matched records. If credits are insufficient, return the available records immediately with the insufficient-credit explanation and top-up link; do not ask for permission again."
        return [
            _tool("search_business", "Search businesses. " + search_desc, search_common), _tool("search_consumer", "Search consumers. " + search_desc, consumer_props), _tool("search_contact", "Search contacts. " + search_desc, contact_props),
            _tool("purchase_business", "Call search_business first. Never ask for or invent search_id. Do not call without the user's record count permission. Paid users follow credit validation; if the requested count exceeds remaining credits, return the available records immediately and explain the shortfall without asking permission again; freemium users receive the upgrade link.", purchase, ["search_id", "count"]),
            _tool("purchase_consumer", "Call search_consumer first. Never ask for or invent search_id. Do not call without the user's record count permission. Paid users follow credit validation; if the requested count exceeds remaining credits, return the available records immediately and explain the shortfall without asking permission again; freemium users receive the upgrade link.", purchase, ["search_id", "count"]),
            _tool("purchase_contact", "Call search_contact first. Never ask for or invent search_id. Do not call without the user's record count permission. Paid users follow credit validation; if the requested count exceeds remaining credits, return the available records immediately and explain the shortfall without asking permission again; freemium users receive the upgrade link.", purchase, ["search_id", "count"]),
            _tool("enrich_business", enrich_desc + " Return business name, SIC, employee size, estimated revenue, address, and email.", enrich, []),
            _tool("enrich_consumer", enrich_desc + " Return consumer name, age, income, email, and address.", enrich, []),
            _tool("enrich_contact", enrich_desc + " Return all contacts, including secondary contacts, with name, business name, SIC code, job title, and email address.", enrich, []),
        ]

    @staticmethod
    def _prompts() -> list[dict[str, Any]]:
        return [
            {"name": "business_search", "title": "Business search demo", "description": "Find Starbucks in Ohio and display masked samples and insights."},
            {"name": "contact_search", "title": "Contact search demo", "description": "Find manager contacts and display masked samples and insights."},
            {"name": "consumer_search", "title": "Consumer search demo", "description": "Find consumers with income above 20K and display masked samples and insights."},
            {"name": "business_enrichment", "title": "Business enrichment from uploaded data", "description": "Enrich the user's uploaded business rows with permission and credit validation."},
            {"name": "consumer_enrichment", "title": "Consumer enrichment from uploaded data", "description": "Enrich the user's uploaded consumer rows with permission and credit validation."},
            {"name": "contact_enrichment", "title": "Contact enrichment from uploaded data", "description": "Enrich all matching uploaded contacts, including secondary contacts, with permission and credit validation."},
            {"name": "partial_credit_test", "title": "Partial-credit test", "description": "Request more records than the paid user's remaining credits to test immediate partial results and the top-up message."},
        ]

    @staticmethod
    def _prompt_text(name: str) -> str:
        prompts = {
            "business_search": "Find me Starbucks in Ohio. Show all 10 masked samples, total matches, and full-result insights. Then ask how many records I want to reveal.",
            "contact_search": "Find me contacts working as managers. Show all 10 masked samples and full-result insights. Then ask how many records I want to reveal.",
            "consumer_search": "Find me consumers with income of more than 20K. Show all 10 masked samples and full-result insights. Then ask how many records I want to reveal.",
            "business_enrichment": "I uploaded my business records. Use only my uploaded rows with the business enrichment tool. Ask permission to proceed without showing match or non-match counts. After I give permission, enrich all matched rows and return the records with credit totals.",
            "consumer_enrichment": "I uploaded my consumer records. Use only my uploaded rows with the consumer enrichment tool. Ask permission to proceed without showing match or non-match counts. After I give permission, enrich all matched rows and return the records with credit totals.",
            "contact_enrichment": "I uploaded my contact records. Use only my uploaded rows with the contact enrichment tool. Include primary and secondary contacts. Ask permission to proceed without showing match or non-match counts. After I give permission, enrich all matched rows and return the records with credit totals.",
            "partial_credit_test": "Request 25 records and follow the paid partial-credit flow. If the request exceeds remaining credits, return the available records immediately with the insufficient-credit explanation and top-up link; do not ask for permission again.",
        }
        if name not in prompts:
            raise ValueError(f"Unknown prompt: {name}")
        return prompts[name]

    def call(self, token: str, message: dict[str, Any]) -> dict[str, Any] | None:
        state = self.state_for(token)
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            requested = params.get("protocolVersion", "")
            return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": requested if requested in SUPPORTED_PROTOCOLS else PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}, "prompts": {"listChanged": False}}, "serverInfo": {"name": "hsb-unified-demo", "version": "2.0.0"}}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tools}}
        if method == "resources/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": [{"uri": RESOURCE_URI, "name": "unified-auth-enrichment-workflow", "mimeType": "text/markdown", "description": "Authenticated paid/freemium search, purchase, and user-data enrichment workflow."}]}}
        if method == "resources/read":
            if params.get("uri") != RESOURCE_URI:
                return _rpc_error(request_id, -32602, "Unknown resource URI")
            return {"jsonrpc": "2.0", "id": request_id, "result": {"contents": [{"uri": RESOURCE_URI, "mimeType": "text/markdown", "text": _workflow_text()}]}}
        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"prompts": self.prompts}}
        if method == "prompts/get":
            try:
                prompt_text = self._prompt_text(params.get("name", ""))
            except ValueError as exc:
                return _rpc_error(request_id, -32602, str(exc))
            return {"jsonrpc": "2.0", "id": request_id, "result": {"description": "HSB MCP demo prompt", "messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}}
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                if name == "search_business": result = self.search_business(state, args)
                elif name == "search_consumer": result = self.search_consumer(state, args)
                elif name == "search_contact": result = self.search_contact(state, args)
                elif name.startswith("purchase_"): result = self.purchase(state, args, name.removeprefix("purchase_"))
                elif name.startswith("enrich_"): result = self.enrich(state, args, name.removeprefix("enrich_"))
                else: return _rpc_error(request_id, -32602, f"Unknown tool: {name}")
                if "content" not in result: result = _text_result(result)
            except ValueError as exc:
                result = _text_result({"status": "invalid_request", "error": str(exc)}, error=True)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        return _rpc_error(request_id, -32601, f"Method not found: {method}")


TOKENS: dict[str, dict[str, str]] = {}
OAUTH_CLIENTS: dict[str, dict[str, Any]] = {}
AUTH_CODES: dict[str, dict[str, Any]] = {}


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    if method in ("", "plain"):
        return secrets.compare_digest(verifier, challenge)
    if method == "S256":
        return secrets.compare_digest(_base64url(hashlib.sha256(verifier.encode()).digest()), challenge)
    return False


def _demo_guide() -> str:
    return "Using HSB MCP, find me Starbucks in Ohio and show me the masked samples, total count, and insights."


def _demo_user(username: str) -> tuple[str, dict[str, str]] | None:
    """Accept the exact email or a friendly paid/freemium alias for the demo."""
    normalized = username.strip().lower()
    aliases = {"paid": "paid@example.com", "paid user": "paid@example.com", "freemium": "freemium@example.com", "freemium user": "freemium@example.com"}
    email = aliases.get(normalized, normalized)
    user = DEMO_USERS.get(email)
    return (email, user) if user else None


def _login_html(action: str, hidden: dict[str, str] | None = None, message: str = "") -> str:
    fields = "".join(f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value)}">' for key, value in (hidden or {}).items())
    prompt = html.escape(_demo_guide(), quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HSB MCP | Demo login</title>
  <style>
    :root {{ --ink:#172033; --muted:#667085; --line:#e7eaf0; --blue:#315efb; --blue-dark:#2448c8; --lavender:#eef2ff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; color:var(--ink); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:linear-gradient(135deg,#f7f9ff 0%,#ffffff 48%,#eef3ff 100%); }}
    .shell {{ width:min(1080px,calc(100% - 40px)); margin:0 auto; padding:28px 0 48px; }}
    .brand {{ display:flex; align-items:center; gap:12px; margin-bottom:28px; font-weight:750; letter-spacing:-.02em; }}
    .mark {{ width:42px; height:42px; display:grid; place-items:center; border-radius:13px; color:#fff; font-size:14px; letter-spacing:.08em; background:linear-gradient(145deg,#315efb,#7b61ff); box-shadow:0 8px 18px rgba(49,94,251,.24); }}
    .brand span {{ font-size:18px; }}
    .grid {{ display:grid; grid-template-columns:1.08fr .92fr; gap:22px; align-items:stretch; }}
    .card {{ background:rgba(255,255,255,.9); border:1px solid rgba(231,234,240,.95); border-radius:24px; box-shadow:0 22px 60px rgba(31,49,93,.09); }}
    .welcome {{ position:relative; overflow:hidden; padding:48px; background:linear-gradient(145deg,#172449 0%,#263b7c 58%,#315efb 100%); color:#fff; }}
    .welcome:after {{ content:""; position:absolute; width:230px; height:230px; right:-80px; bottom:-100px; border:34px solid rgba(255,255,255,.11); border-radius:50%; }}
    .eyebrow {{ color:#b9c7ff; font-size:12px; font-weight:750; letter-spacing:.14em; text-transform:uppercase; }}
    h1 {{ max-width:440px; margin:16px 0 16px; font-size:clamp(34px,5vw,54px); line-height:1.02; letter-spacing:-.055em; }}
    .lead {{ max-width:450px; margin:0; color:#d9e1ff; font-size:17px; line-height:1.6; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:9px; margin-top:30px; }}
    .chip {{ padding:8px 11px; color:#e8edff; border:1px solid rgba(255,255,255,.2); border-radius:999px; font-size:12px; background:rgba(255,255,255,.09); }}
    .login {{ padding:34px; }}
    .login h2 {{ margin:0 0 8px; font-size:25px; letter-spacing:-.03em; }}
    .subtle {{ margin:0 0 24px; color:var(--muted); font-size:14px; line-height:1.5; }}
    .notice {{ margin:0 0 16px; padding:10px 12px; color:#805b00; border:1px solid #f5df9a; border-radius:12px; background:#fff9e8; font-size:13px; }}
    label {{ display:block; margin:16px 0 7px; font-size:12px; font-weight:700; color:#475467; }}
    input {{ width:100%; padding:13px 14px; border:1px solid #dfe3eb; border-radius:12px; color:var(--ink); font:inherit; outline:none; background:#fff; }}
    input:focus {{ border-color:var(--blue); box-shadow:0 0 0 4px rgba(49,94,251,.1); }}
    .primary {{ width:100%; margin-top:21px; padding:13px 16px; border:0; border-radius:12px; color:#fff; font:inherit; font-weight:750; cursor:pointer; background:var(--blue); box-shadow:0 8px 16px rgba(49,94,251,.2); }}
    .primary:hover {{ background:var(--blue-dark); }}
    .demo {{ display:grid; grid-template-columns:1fr 1fr; gap:9px; margin-top:20px; }}
    .demo div {{ padding:11px; border:1px solid var(--line); border-radius:12px; background:#fafbff; }}
    .demo strong {{ display:block; margin-bottom:4px; font-size:12px; }}
    .demo code {{ color:#4d5c78; font-size:11px; word-break:break-word; }}
    .prompt {{ margin-top:22px; padding:16px; border:1px solid #dce4ff; border-radius:16px; background:var(--lavender); }}
    .prompt-head {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }}
    .prompt-head strong {{ font-size:13px; }}
    .copy {{ padding:7px 10px; border:1px solid #c8d4ff; border-radius:8px; color:#264bc9; font-size:12px; font-weight:700; cursor:pointer; background:#fff; }}
    .copy:hover {{ background:#f7f9ff; }}
    .prompt-text {{ margin:0; color:#34446e; font-size:12px; line-height:1.55; white-space:normal; }}
    .status {{ min-height:16px; margin:7px 0 0; color:#2e7d5b; font-size:11px; }}
    footer {{ margin-top:20px; color:#8a94a7; text-align:center; font-size:11px; }}
    @media (max-width:780px) {{ .shell {{ width:min(100% - 24px,560px); padding-top:18px; }} .grid {{ grid-template-columns:1fr; }} .welcome {{ padding:34px 28px; }} .login {{ padding:28px; }} .welcome h1 {{ font-size:42px; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <div class="brand"><div class="mark">HSB</div><span>HSB MCP</span></div>
    <section class="grid">
      <div class="card welcome">
        <div class="eyebrow">HSB data experience</div>
        <h1>One HSB MCP. Two plan experiences.</h1>
        <p class="lead">Test masked search, credit-aware reveal, and enrichment of your own business, consumer, and contact records.</p>
        <div class="chips"><span class="chip">Masked previews</span><span class="chip">Paid + freemium</span><span class="chip">Claude-ready</span></div>
      </div>
      <div class="card login">
        <h2>Sign in to the demo</h2>
        <p class="subtle">Choose a demo account to test its exact MCP behavior.</p>
        {f'<p class="notice">{html.escape(message)}</p>' if message else ''}
        <form method="post" action="{html.escape(action)}">
          {fields}
          <label for="username">Email</label>
          <input id="username" name="username" type="email" placeholder="you@example.com" autocomplete="username" required>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" placeholder="Enter demo password" autocomplete="current-password" required>
          <button class="primary" type="submit">Continue to HSB MCP</button>
        </form>
        <div class="demo"><div><strong>Paid demo</strong><code>paid@example.com<br>paid-demo</code></div><div><strong>Freemium demo</strong><code>freemium@example.com<br>freemium-demo</code></div></div>
        <div class="prompt"><div class="prompt-head"><strong>Try this prompt in Claude</strong><button class="copy" id="copyButton" type="button" onclick="copyPrompt()">Copy prompt</button></div><p class="prompt-text" id="prompt">{prompt}</p><p class="status" id="copyStatus" aria-live="polite"></p></div>
      </div>
    </section>
    <footer>HSB · MCP demonstration environment</footer>
  </main>
  <script>
    function showCopied() {{
      document.getElementById("copyButton").textContent = "Copied";
      document.getElementById("copyStatus").textContent = "Prompt copied to your clipboard.";
      window.setTimeout(function () {{ document.getElementById("copyButton").textContent = "Copy prompt"; }}, 1800);
    }}
    function fallbackCopy(text) {{
      var area = document.createElement("textarea"); area.value = text; document.body.appendChild(area); area.select();
      try {{ document.execCommand("copy"); showCopied(); }} catch (error) {{ document.getElementById("copyStatus").textContent = "Select and copy the prompt manually."; }}
      document.body.removeChild(area);
    }}
    function copyPrompt() {{
      var text = document.getElementById("prompt").innerText;
      if (navigator.clipboard && window.isSecureContext) {{ navigator.clipboard.writeText(text).then(showCopied).catch(function () {{ fallbackCopy(text); }}); }} else {{ fallbackCopy(text); }}
    }}
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        super().log_message(format, *args)

    def base_url(self) -> str:
        configured = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        if configured:
            return configured
        scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
        return f"{scheme}://{self.headers.get('Host', '127.0.0.1')}"

    def cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def send_bytes(self, status: int, body: bytes, content_type: str = "application/json", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.cors()
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        self.send_bytes(status, _json(payload), headers=headers)

    def body(self) -> bytes:
        transfer = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in transfer:
            chunks = []
            while True:
                size = int(self.rfile.readline().strip().split(b";", 1)[0], 16)
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size)); self.rfile.read(2)
            return b"".join(chunks)
        return self.rfile.read(int(self.headers.get("Content-Length", "0")))

    def form(self) -> dict[str, str]:
        values = parse_qs(self.body().decode(), keep_blank_values=True)
        return {key: items[-1] for key, items in values.items()}

    def token(self) -> str | None:
        header = self.headers.get("Authorization", "")
        return header[7:].strip() if header.lower().startswith("bearer ") else None

    def do_OPTIONS(self) -> None:
        self.send_bytes(204, b"", content_type="text/plain")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/login"):
            self.send_bytes(200, _login_html("/login").encode(), "text/html; charset=utf-8"); return
        if parsed.path == "/health":
            self.send_json(200, {"status": "ok", "service": "hsb-unified-demo"}); return
        if parsed.path == "/.well-known/oauth-authorization-server":
            base = self.base_url(); self.send_json(200, {"issuer": base, "authorization_endpoint": base + "/oauth/authorize", "token_endpoint": base + "/oauth/token", "registration_endpoint": base + "/oauth/register", "code_challenge_methods_supported": ["S256", "plain"]}); return
        if parsed.path == "/.well-known/oauth-protected-resource":
            self.send_json(200, {"resource": self.base_url() + "/mcp", "authorization_servers": [self.base_url()]}); return
        if parsed.path == "/oauth/authorize":
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            self.send_bytes(200, _login_html("/oauth/authorize", query, "Sign in to authorize Claude for this MCP demo.").encode(), "text/html; charset=utf-8"); return
        if parsed.path == "/mcp":
            self.send_bytes(405, b"", headers={"Allow": "POST, OPTIONS"}); return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            form = self.form(); identity = _demo_user(form.get("username", ""))
            if not identity or identity[1]["password"] != form.get("password"):
                self.send_bytes(401, _login_html("/login", message="Invalid demo credentials.").encode(), "text/html; charset=utf-8"); return
            email, user = identity
            token = _issue_token(email)
            self.send_bytes(200, (f"<html><body><h1>Signed in</h1><p>Plan: {html.escape(user['plan'])}</p><p>Use this bearer token for local testing:</p><code>{html.escape(token)}</code><h2>Prompt</h2><code>{html.escape(_demo_guide())}</code></body></html>").encode(), "text/html; charset=utf-8"); return
        if parsed.path == "/oauth/register":
            try: request = json.loads(self.body())
            except json.JSONDecodeError: self.send_json(400, {"error": "invalid_client_metadata"}); return
            client_id = "client_" + secrets.token_urlsafe(12)
            OAUTH_CLIENTS[client_id] = {"redirect_uris": request.get("redirect_uris", []), "client_secret": secrets.token_urlsafe(24), "token_endpoint_auth_method": request.get("token_endpoint_auth_method", "none")}
            self.send_json(201, {"client_id": client_id, "client_secret": OAUTH_CLIENTS[client_id]["client_secret"], "redirect_uris": request.get("redirect_uris", [])}); return
        if parsed.path == "/oauth/authorize":
            form = self.form()
            redirect_uri = form.get("redirect_uri", "")
            client_id = form.get("client_id", "")
            client = OAUTH_CLIENTS.get(client_id)
            if client is None and client_id.startswith("client_") and redirect_uri in ALLOWED_OAUTH_REDIRECT_URIS:
                # Claude may reuse a dynamic client ID after a Render restart.
                client = {"redirect_uris": [redirect_uri], "client_secret": "", "token_endpoint_auth_method": "none"}
                OAUTH_CLIENTS[client_id] = client
            identity = _demo_user(form.get("username", ""))
            if client is None:
                self.send_bytes(401, _login_html("/oauth/authorize", form, "This Claude sign-in session has expired. Close the connector login and start it again.").encode(), "text/html; charset=utf-8"); return
            if not identity:
                self.send_bytes(401, _login_html("/oauth/authorize", form, "Use paid@example.com / paid-demo or freemium@example.com / freemium-demo.").encode(), "text/html; charset=utf-8"); return
            email, user = identity
            if user["password"] != form.get("password"):
                self.send_bytes(401, _login_html("/oauth/authorize", form, "The demo password is incorrect. Paid uses paid-demo; freemium uses freemium-demo.").encode(), "text/html; charset=utf-8"); return
            if redirect_uri not in client["redirect_uris"]:
                self.send_json(400, {"error": "invalid_request", "error_description": "redirect_uri is not registered"}); return
            code = secrets.token_urlsafe(32)
            AUTH_CODES[code] = {"client_id": client_id, "redirect_uri": redirect_uri, "challenge": form.get("code_challenge", ""), "method": form.get("code_challenge_method", "S256"), "email": email}
            location = redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode({"code": code, "state": form.get("state", "")})
            self.send_bytes(302, b"", headers={"Location": location}); return
        if parsed.path == "/oauth/token":
            form = self.form(); code_data = AUTH_CODES.pop(form.get("code", ""), None); client = OAUTH_CLIENTS.get(form.get("client_id", ""))
            if not code_data or not client or code_data["client_id"] != form.get("client_id") or code_data["redirect_uri"] != form.get("redirect_uri") or not _verify_pkce(form.get("code_verifier", ""), code_data["challenge"], code_data["method"]):
                self.send_json(400, {"error": "invalid_grant"}); return
            token = _issue_token(code_data["email"])
            self.send_json(200, {"access_token": token, "token_type": "Bearer", "expires_in": 86400, "refresh_token": token}); return
        if parsed.path == "/mcp":
            token = self.token()
            if not token or token not in TOKENS:
                resource = self.base_url() + "/.well-known/oauth-protected-resource"
                self.send_json(401, {"error": "unauthorized"}, {"WWW-Authenticate": f'Bearer resource_metadata="{resource}"'}); return
            try: message = json.loads(self.body())
            except json.JSONDecodeError: self.send_json(400, _rpc_error(None, -32700, "Invalid JSON")); return
            try: response = MCP.call(token, message)
            except ValueError as exc: response = _rpc_error(message.get("id"), -32001, str(exc))
            if response is None: self.send_bytes(202, b""); return
            self.send_json(200, response, {"Mcp-Session-Id": token}); return
        self.send_json(404, {"error": "Not found"})


def _issue_token(email: str) -> str:
    token = "sg_" + secrets.token_urlsafe(24)
    user = DEMO_USERS[email]
    TOKENS[token] = {"email": email, "plan": user["plan"]}
    return token


MCP = UnifiedMCP()


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"hsb-unified-demo listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
