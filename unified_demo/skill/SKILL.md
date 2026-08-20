---
name: unified-auth-enrichment-workflow
description: Operate the unified authenticated HSB MCP demo with paid and freemium users, masked search previews, credit-gated purchases, and user-owned business, consumer, and contact enrichment. Use when the MCP server identifies the signed-in demo user's plan and the workflow must preserve paid or freemium behavior.
---

# Unified Authenticated MCP Workflow

Use the authenticated user's plan from the MCP session. Do not ask the user to choose a plan.

## Search

1. Use the matching search tool. All filters are optional.
2. Display all 10 masked samples exactly as returned.
3. Show total matches and aggregate insights, including verified email and verified phone totals.
4. Ask only how many records the user wants to reveal and state that each record consumes 1 credit.
5. If the user gives a number, call the matching purchase tool with the exact search ID and `confirm=true`. If no number is given, do not purchase.

## Purchase

- Paid user: charge one credit per returned record. With insufficient credits, return records immediately up to the remaining credit balance, explain why fewer records were returned, and include the top-up URL; do not ask for permission again. With zero credits, return no records and the top-up URL. Show credits deducted and remaining whenever records are returned.
- Freemium user: return no records and the upgrade URL. Do not imply that freemium credits exist.

## Enrichment

There is no standalone match tool or match report. Use only the entity-specific enrichment tool, and only when the user brings their own uploaded data.

1. First call `enrich_business`, `enrich_consumer`, or `enrich_contact` with rows parsed from the user's uploaded file. Never pass a file path.
2. The tool validates and holds the rows, returns an opaque `enrichment_id`, and asks permission without displaying matched or non-matched counts. Do not deduct credits on this first call.
3. Explain that each matched record consumes 1 credit and non-matches consume no credits. Do not call the second phase until the user gives permission.
4. After permission, call the same tool with the exact `enrichment_id` and `confirm=true`. Include `count` only when the user requests a specific number; otherwise omit it to enrich all matched records.
5. Paid users follow the same no-credit and partial-credit behavior as purchases. If credits are insufficient, return available records immediately with the shortfall explanation and top-up URL; do not ask permission again. Freemium users receive no enriched records and the upgrade URL.
6. Contact enrichment includes all matched contacts, including primary and secondary contacts.

## Demo users

- Paid: `paid@example.com` / `paid-demo`
- Freemium: `freemium@example.com` / `freemium-demo`

The login page contains a copyable prompt for testing.
