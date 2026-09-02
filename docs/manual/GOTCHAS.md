# Gotchas

| Constraint | Exact consequence | Required handling |
|---|---|---|
| Packet Tracer Script Engine has no `XMLHttpRequest` | Network calls from `runCode` fail | Run the polling loop in the QWebEngine webview and use `$se("runCode", ...)` |
| A hidden Packet Tracer webview freezes timers | `GET /next` polling stops and `pt_bridge_status` reports disconnected after 5 seconds | Keep the MCP-BUILDER window visible |
| Bridge result messages have no request ID | A late response can satisfy the next request | `_bridge_send_and_wait()` drains stale results before queueing and serializes request/response use |
| Script Engine error popups terminate polling | A malformed command can disconnect all live tools | Compose commands with `json.dumps`, validate enums in Python, and keep generated JavaScript on one line |
| Packet Tracer traffic types can be numeric or enum strings | A PDU filter can miss equivalent frames | Map both forms, for example `0` and `eTrafficType_Icmp`, to `ICMP` |
| Upstream Socket.IO bridge has open issue `#1` on Packet Tracer `9.0.0` | Its installable bridge window can render blank and never bind port `7531` | Do not replace the target bridge with the upstream transport |
| `packet-tracer-mcp` is occupied on PyPI | A tag workflow can publish to a package owned by another repository or fail OIDC verification | Do not add publishing automation until package ownership is documented |

