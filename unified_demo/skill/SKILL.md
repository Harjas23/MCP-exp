---
name: unified-auth-enrichment-workflow
description: Operate the unified authenticated Sales Genie MCP demo with paid and freemium users, masked search previews, credit-gated purchases, and user-owned business, consumer, and contact enrichment. Use when the MCP server identifies the signed-in demo user's plan and the workflow must preserve paid or freemium behavior.
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

- Paid user: charge one credit per returned record. With insufficient credits, return no records first and offer the available count or the top-up URL. With zero credits, return no records and the top-up URL. Show credits deducted and remaining whenever records are returned.
- Freemium user: return no records and the upgrade URL. Do not imply that freemium credits exist.

## Enrichment

There is no standalone match tool or match report. Use only the entity-specific enrichment tool, and only when the user brings their own uploaded data.

1. First call `enrich_business`, `enrich_consumer`, or `enrich_contact` with rows parsed from the user's uploaded file. Never pass a file path.
2. The tool validates records and returns matched and non-matched counts plus an `enrichment_id`. Do not deduct credits on this first call.
3. Display the permission message: each matched record consumes 1 credit; non-matches consume no credits. Ask how many matched records the user wants to enrich.
4. Do not call the second enrichment phase unless the user provides a number. Then call the same tool with the exact `enrichment_id`, count, and `confirm=true`.
5. Paid users follow the same no-credit and partial-credit behavior as purchases. Freemium users receive no enriched records and the upgrade URL.
6. Contact enrichment includes all matched contacts, including primary and secondary contacts.

## Demo users

- Paid: `paid@example.com` / `paid-demo`
- Freemium: `freemium@example.com` / `freemium-demo`

The login page contains a copyable prompt for testing.
