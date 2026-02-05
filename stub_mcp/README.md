# Stub MCP Server

The stub MCP server exposes deterministic tool behavior so that agents can
exercise tool call flows without depending on live backends. It reads its
configuration from `generated/stub/stub_config.json`, the file produced by
`dcf_mcp.tools.dcf.yaml_to_stub_config` from `skills_src/tools.yaml`.

## Protocol

The server now speaks the [Model Context Protocol](https://modelcontextprotocol.io/)
using the Streamable HTTP transport. Agents should issue POST/GET requests to the
`/mcp` endpoint and reuse the `mcp-session` header provided by the server to keep
stateful sessions alive. The previous stdio/websocket transports have been
removed.

A tiny health probe is also exposed at `/healthz`.

## Hot-reloading behavior

The running server performs a lightweight check for the configuration file's
modification time on every MCP request. If the file changes while the process is
running, the next tool listing or call will transparently pick up the new
configuration contents without restarting the service. Missing files resolve to
an empty configuration so the process keeps running while you regenerate
artifacts.

The generator writes updates atomically by streaming to a temporary file and
renaming it into place. This avoids the server ever reading a partial JSON blob
while the file is being regenerated.

## Lifecycle tips

1. Run the generator:
   ```bash
   python -c 'from dcf_mcp.tools.dcf.yaml_to_stub_config import yaml_to_stub_config; yaml_to_stub_config()'
   ```
2. Start the stub MCP server (e.g. via Docker Compose or directly with
   `uvicorn stub_mcp_server:app --host 0.0.0.0 --port 8765`).
3. Regenerate the config as needed; no restart is required because of the hot
   reload logic described above.

## Local testing

For quick smoke tests you can exercise the Streamable HTTP endpoint with curl:

```bash
curl -i -X POST http://localhost:8765/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{}}'
```

On success the server responds with a `200` status and includes the
`mcp-session` header that should be echoed on follow-up requests.
