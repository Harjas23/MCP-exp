---
name: paid-mcp-workflow
description: Operate the paid and freemium data-search MCP tools with masked previews, full-result insights, explicit reveal permission, credit-aware purchases, and upgrade handling. Use when handling business, consumer, or contact searches and subsequent record-reveal requests.
---

# Paid MCP Workflow

Use this workflow for the local or remote Data Axle MCP demo. Keep search and purchase as separate stages.

## Search

1. Select the matching search tool:
   - `search_business`: business name, SIC code, street, city, ZIP, revenue.
   - `search_consumer`: city, state, name, income, age.
   - `search_contact`: company name, industry, job title.
2. Treat every filter as optional when the user did not provide it. For business searches, map a named city to `city` and a named state such as Ohio to `state`; do not put a state in `city`.
3. Display the search result to the user:
   - All 10 masked sample records.
   - Total matching-record count.
   - Aggregate insights calculated for the full result set, not only the 10 samples.
4. Ask how many records the user wants to reveal and state that each record consumes 1 credit. Treat a number as permission to proceed.
5. If the user does not provide a number, do not call a purchase tool.

## Purchase

1. Call the matching search tool first and retain the exact `search_id` it returns. Never ask the user for `search_id`, invent it, or transform it.
2. After the user gives permission, call the matching purchase tool with:
   - `search_id` from the search response.
   - `count` requested by the user.
   - `confirm=true`.
3. Charge one credit per record returned. If at least one record is returned, explicitly show records returned, credits deducted, and credits remaining, including for partial results.
4. If the request exceeds the balance, return only the credit-supported number of records and include the insufficient-credit message and top-up link.
5. If the balance is zero, return no records and include the no-credits message and top-up link.

## Freemium behavior

Use `search_business` first. If the user requests a reveal and gives permission, call `purchase_business`; it must return no records and the Pro/Teams upgrade message with the subscription link.

## Query mapping examples

- "Find me Starbucks in Ohio" -> `search_business` with `business_name="Starbucks"`, `state="Ohio"`.
- "Find me contacts working as managers" -> `search_contact` with `job_title="manager"`.
- "Find consumers with income of more than 20K" -> `search_consumer` with `income="more than 20000"`.
- "Give me 15 records" after a search -> purchase the matching search with `count=15`, but only after explicit permission is established.
