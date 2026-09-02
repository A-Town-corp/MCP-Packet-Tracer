# Architecture

## Runtime Data Flow

```text
MCP client
  -> packet_tracer_mcp.server:main
  -> FastMCP tool registered in
     src/packet_tracer_mcp/adapters/mcp/tool_registry.py
  -> loopback HTTP bridge at 127.0.0.1:54321
  -> Packet Tracer QWebEngine polling bootstrap
  -> $se("runCode", javascript)
  -> Packet Tracer ipc object API
  -> reportResult(JSON.stringify(payload))
  -> bridge result queue
  -> MCP text response
```

## Process Ports

| Port | Bind address | Owner | Purpose |
|---|---|---|---|
| `39000` | `127.0.0.1` | `packet_tracer_mcp.server` | Streamable HTTP MCP transport |
| `54321` | `127.0.0.1` | `PTCommandBridge` | Packet Tracer command and result bridge |

The `--stdio` server mode omits port `39000`; the bridge on port `54321` still
starts when `register_tools()` runs.

## Live Tool Extension Point

`register_tools()` owns `_RUNTIME_PATCHES_JS`. The bridge sends this single-line
JavaScript bundle once per Packet Tracer connection. Named wrapper functions
contain Packet Tracer object-API calls and return JSON through `reportResult`.
New live tools call those wrappers through `_bridge_send_and_wait()`.

## Catalog Authority

| Concern | Authoritative module |
|---|---|
| Device models and categories | `src/packet_tracer_mcp/infrastructure/catalog/devices.py` |
| Cable names and Packet Tracer type codes | `src/packet_tracer_mcp/infrastructure/catalog/cables.py` and `src/packet_tracer_mcp/shared/constants.py` |
| Module compatibility | `src/packet_tracer_mcp/infrastructure/catalog/modules.py` |
| MCP tool registration | `src/packet_tracer_mcp/adapters/mcp/tool_registry.py` |
| Bridge server | `src/packet_tracer_mcp/infrastructure/execution/live_bridge.py` |

