"""Remote paid MCP server for Claude web and Render."""

from paid_server import build_server
from remote_server_common import run_remote_server


if __name__ == "__main__":
    run_remote_server(build_server, "paid-data-demo")
