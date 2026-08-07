# Local MCP data-access demo

This workspace contains two dependency-free MCP servers for Claude Desktop:

- `paid_server.py`: `search_business`, `search_consumer`, `search_contact`, and the three matching purchase tools. It starts with 60 credits and charges one credit per returned record.
- `freemium_server.py`: `search_business` and `purchase_business`. Business records cannot be revealed until the user upgrades.
- `paid_remote_server.py`: paid-only remote HTTP wrapper for Claude web/remote connector testing.

The demo uses sample data only. All searches return 10 masked previews. Masking leaves the first two characters visible. Paid purchase calls require `confirm=true` after user permission. If the paid balance is zero, no records are returned and the top-up link is shown. If a request is larger than the balance, only the credit-supported number of records is returned with an insufficient-credit message.

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

`paid_remote_server.py` is the paid-only remote duplicate. It listens on Render's `PORT`, exposes the MCP endpoint at `/mcp`, and exposes `/health` for the service health check. `render.yaml` contains the Free web-service configuration.

After deployment, use the resulting HTTPS URL ending in `/mcp` as a custom connector URL in Claude web under Settings > Connectors > Add custom connector. The remote wrapper keeps the paid balance in process memory for this demo; a service restart or free-tier sleep resets the 60 credits.

## Demo sequence

For the paid server, use these searches and then request 20 records for each:

1. `search_business` with `business_name=Starbucks`, `city=Ohio`.
2. `search_contact` with `job_title=manager`.
3. `search_consumer` with `income=more than 20000`.

After three successful 20-record purchases, the 60 credits are exhausted. A subsequent purchase returns the no-credits error and top-up link.

The purchase response includes `credits_deducted` and `credits_remaining`.
