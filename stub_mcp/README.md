# Stub MCP Server

The stub MCP server exposes deterministic tool behavior to let agents exercise tool
call flows without depending on live backends. It reads its configuration from
`generated/stub/stub_config.json`, the file produced by
`dcf_mcp.tools.dcf.csv_to_stub_config`.

## Hot-reloading behavior

The running server performs a lightweight check for the configuration file's
modification time on every JSON-RPC request (both `stdio` and websocket modes).
If the file changes while the process is running, the next tool listing or call
will transparently pick up the new configuration contents without restarting the
service. Missing files resolve to an empty configuration so the process keeps
running while you regenerate artifacts.

The generator writes updates atomically by streaming to a temporary file and
renaming it into place. This avoids the server ever reading a partial JSON blob
while the file is being regenerated.

## Lifecycle tips

1. Run the generator:
   ```bash
   python -m dcf_mcp.tools.dcf.csv_to_stub_config
   ```
2. Start the stub MCP server (e.g. via Docker Compose or directly with
   `python stub_mcp/stub_mcp_server.py`).
3. Regenerate the config as needed; no restart is required because of the hot
   reload logic described above.

