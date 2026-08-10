# Local MCP data-access demo

This workspace contains two dependency-free MCP servers for Claude Desktop:

- `paid_server.py`: `search_business`, `search_consumer`, `search_contact`, the three purchase tools, and bulk `match_*`/`enrich_*` tools. It starts with 15 credits and charges one credit per returned or enriched record.
- `freemium_server.py`: business search/purchase plus business match/enrich. Business records cannot be revealed or enriched until the user upgrades.
- `paid_remote_server.py`: paid-only remote HTTP wrapper for Claude web/remote connector testing.

The demo uses sample data only. All searches return 10 masked previews. Masking leaves the first two characters visible. Paid purchase and enrichment calls require `confirm=true` after the user provides a record count. If the paid balance is zero, no records are returned and the top-up link is shown. If a request is larger than the balance, the first call returns no records and offers the available count or top-up; a second call with the approved available count returns those records.

Bulk matching accepts up to 100 rows parsed by Claude from an uploaded file. The MCP server validates required fields, reports matched and dropped rows, and returns a `match_id`. The corresponding enrichment tool uses that exact `match_id`. Matching itself does not consume credits; enrichment consumes one credit per returned record. Contact matching and enrichment include both primary and secondary contacts.

Top-up and upgrade link: https://teampitstop.wixsite.com/home

## Run locally

From this folder:

```powershell
python .\paid_server.py
python .\freemium_server.py
```

The processes speak MCP JSON-RPC over stdin/stdout. Do not add logging to stdout; Claude Desktop uses stdout for the protocol.

## Claude Desktop configuration

Add both servers to Claude Desktop's MCP configuration, using absolute paths for this folder:

```json
{
  "mcpServers": {
    "paid-data-demo": {
      "command": "C:\\Users\\hbajwa\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
      "args": ["C:\\Users\\hbajwa\\OneDrive - Data Axle\\MCP exp\\paid_server.py"]
    },
    "freemium-data-demo": {
      "command": "C:\\Users\\hbajwa\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
      "args": ["C:\\Users\\hbajwa\\OneDrive - Data Axle\\MCP exp\\freemium_server.py"]
    }
  }
}
```

Restart Claude Desktop after saving the configuration.

## Render deployment for Claude web

`paid_remote_server.py` and `freemium_remote_server.py` are the remote duplicates. They listen on Render's `PORT`, expose the MCP endpoint at `/mcp`, and expose `/health` for the service health check. `render.yaml` deploys both as separate Free web services.

After deployment, use the paid service HTTPS URL ending in `/mcp` for the paid connector and the freemium service HTTPS URL ending in `/mcp` for the freemium connector in Claude web under Settings > Connectors > Add custom connector. The remote wrapper keeps the paid balance in process memory for this demo; a service restart or free-tier sleep resets the 15 credits.

## Demo sequence

For the paid server, use these searches and then request 20 records for each:

1. `search_business` with `business_name=Starbucks`, `state=Ohio`.
2. `search_contact` with `job_title=manager`.
3. `search_consumer` with `income=more than 20000`.

With 15 credits, requesting 25 records first returns an insufficient-credit error with no records and offers the user a choice to proceed with 15 records or top up. If the user chooses 15, the next purchase returns 15 records with credits deducted and remaining. A subsequent purchase returns the no-credits error and top-up link.

The purchase and enrichment responses include `credits_deducted` and `credits_remaining` whenever at least one record is returned.

## Bulk match/enrich sequence

1. Upload one of the CSV samples to Claude and ask for details for the uploaded records.
2. Claude passes the parsed rows to `match_business`, `match_consumer`, or `match_contact`.
3. The match tool validates required fields and returns matched and dropped counts plus a `match_id`.
4. After the user gives a record count as permission, Claude calls the corresponding `enrich_*` tool with the exact `match_id`, count, and `confirm=true`.

Sample files:

- `sample_data/business_match_samples.csv`
- `sample_data/consumer_match_samples.csv`
- `sample_data/contact_match_samples.csv`
