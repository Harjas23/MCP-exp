# Unified authenticated HSB MCP demo

This directory is a separate v2 implementation. It does not modify or import the original paid or freemium servers.

## One Render service

The single service contains:

- Demo authentication and login guide.
- OAuth discovery, dynamic client registration, authorization-code + PKCE flow for Claude web.
- One authenticated `/mcp` endpoint.
- Paid and freemium behavior selected from the signed-in demo user.
- Sample workflows exposed through MCP `prompts/list` and `prompts/get`.

Demo credentials:

- Paid: `paid@example.com` / `paid-demo` — starts with 15 credits.
- Freemium: `freemium@example.com` / `freemium-demo` — purchases and enrichment return the upgrade message.

The login page is available at `/login`. It also displays a copyable prompt.

## Render commands

Build command:

```text
python -m py_compile unified_demo/unified_server.py
```

Start command:

```text
python unified_demo/unified_server.py
```

Health check path: `/health`

Claude connector URL: `https://YOUR-SERVICE.onrender.com/mcp`

Set `PUBLIC_BASE_URL` to the public HTTPS service URL if the deployment uses a proxy that does not forward the original host or scheme.

## Enrichment behavior

There are no standalone match tools. `enrich_business`, `enrich_consumer`, and `enrich_contact` each accept user-owned rows from Claude. The first call asks permission without displaying match or non-match counts. After permission, the same tool silently matches the rows and returns enriched records. One credit is charged per matched record returned; non-matches consume no credits. If credits are insufficient, the tool returns as many records as the remaining credit balance allows in that same call.
