---
name: paid-mcp-workflow
description: Operate the paid and freemium data-search and bulk match/enrich MCP tools with masked previews, aggregate insights, explicit record-count permission, server-side incomplete-row validation, credit-aware reveals, and upgrade handling. Use when handling business, consumer, or contact searches, uploaded record matching, enrichment, and subsequent record-reveal requests.
---

# Paid MCP Workflow

Use this workflow for the local or remote Data Axle MCP demo. Keep search/match and purchase/enrichment as separate stages.

## Search

1. Select the matching search tool:
   - `search_business`: business name, SIC code, street, city, ZIP, revenue.
   - `search_consumer`: city, state, name, income, age.
   - `search_contact`: company name, industry, job title.
2. Treat every filter as optional when the user did not provide it. For business searches, map a named city to `city` and a named state such as Ohio to `state`; do not put a state in `city`.
3. Display the search result to the user:
   - All 10 masked sample records.
   - Total matching-record count.
   - Aggregate insights calculated for the full result set, not only the 10 samples, including `total_verified_emails` and `total_verified_phone_numbers`.
4. Ask how many records the user wants to reveal and state that each record consumes 1 credit. Treat a number as permission to proceed.
5. If the user does not provide a number, do not call a purchase tool.

## Purchase

1. Call the matching search tool first and retain the exact `search_id` it returns. Never ask the user for `search_id`, invent it, or transform it.
2. After the user gives permission, call the matching purchase tool with:
   - `search_id` from the search response.
   - `count` requested by the user.
   - `confirm=true`.
3. Charge one credit per record returned. If at least one record is returned, explicitly show records returned, credits deducted, and credits remaining, including for partial results.
4. If the request exceeds the balance, return no records and include the insufficient-credit message, the available count, and top-up link. Reveal records only after the user chooses the available count.
5. If the balance is zero, return no records and include the no-credits message and top-up link.

## Bulk match and enrichment

1. Treat file upload as a Claude action. Pass the parsed file rows in the `records` array; never pass a local path or ask MCP to upload the file. Keep each call at 100 rows or fewer.
2. Select the entity-specific match tool:
   - `match_business`: business name + full address + website, email, or phone.
   - `match_consumer`: consumer name + full address.
   - `match_contact`: contact first name + last name + job title + business name + business full address.
3. Let MCP validate completeness. Display `matched_count`, `dropped_count`, and the dropped-row reasons. Do not perform this validation in the conversation layer.
4. Display: `1 credit per record will be deducted, do you want me to proceed?` A user-provided number is permission. If no number is provided, do not call an enrichment tool.
5. Call only the corresponding enrichment tool with the exact `match_id` from the match response, the user-authorized `count`, and `confirm=true`. Never ask the user for `match_id`, invent it, or transform it.
6. Apply the same paid credit behavior as purchases: no credits returns no records with the top-up link; insufficient credits returns no records first and offers the available count or top-up; a follow-up call for the available count returns those records. Show `credits_deducted` and `credits_remaining` whenever any records are returned.
7. Contact enrichment includes all matched contacts, including secondary contacts, not only primary contacts.

## Freemium behavior

Use `search_business` first. If the user requests a reveal and gives permission, call `purchase_business`; it must return no records and the Pro/Teams upgrade message with the subscription link. For the freemium bulk flow, use `match_business` first and call `enrich_business` only after permission; it must return no records and the paid-subscription upgrade message with the subscription link.

## Query mapping examples

- "Find me Starbucks in Ohio" -> `search_business` with `business_name="Starbucks"`, `state="Ohio"`.
- "Find me contacts working as managers" -> `search_contact` with `job_title="manager"`.
- "Find consumers with income of more than 20K" -> `search_consumer` with `income="more than 20000"`.
- "Give me 15 records" after a search -> purchase the matching search with `count=15`, but only after explicit permission is established.
- "I need details for these uploaded records" -> pass the parsed rows to the matching `match_*` tool, then use the exact returned `match_id` for the corresponding `enrich_*` tool after the user gives a count.
