# `cisco-pt-mcp` Capability Fold

## Executive Summary

The useful upstream contribution is **Packet Tracer object-API knowledge**, not
its transport or package structure. Upstream release `v0.1.6` exposes 18 tools
through a Socket.IO bridge and an installable `.pts` module.[^1] The A-Town
target already has a larger planning, generation, validation, catalog, and live
configuration system, so this change adopts only missing interactive and
simulation operations.[^2]

The implementation scope is 11 additive A-Town tools: `pt_add_device`,
`pt_add_link`, `pt_get_network`, `pt_get_device_info`, `pt_set_device_power`,
`pt_set_simulation_mode`, `pt_get_simulation_status`, `pt_step_simulation`,
`pt_send_pdu`, `pt_get_pdu_results`, and `pt_get_command_log`. Confidence is
**well-sourced** for the capability comparison because both exact commits and
their encrypted extension payloads were inspected. Runtime compatibility with
every Packet Tracer build remains **thin** until the new controls are exercised
against a live application.

## Capability Matrix

| Upstream capability | Target state before this change | Decision | Confidence |
|---|---|---|---|
| Add a single device | Available only through plan deployment or raw JavaScript | Adopt as `pt_add_device` with target catalog validation | Well-sourced[^2][^3] |
| Add a single link | Available only through plan deployment or raw JavaScript | Adopt as `pt_add_link` with target cable validation | Well-sourced[^2][^3] |
| Add modules | Target has single and batch installation with compatibility checks | Retain target implementation | Well-sourced[^2][^3] |
| Remove device/link | Target has `pt_delete_device` and `pt_delete_link` | Retain target implementation | Well-sourced[^2][^3] |
| Rename/move device | Target has both tools | Retain target implementation | Well-sourced[^2][^3] |
| Configure host IP and IOS | Target has `pt_configure_pc`, `pt_apply_ios`, protocol-specific tools, and live CLI tools | Retain target implementation | Well-sourced[^2][^3] |
| Detailed network snapshot | Target query returns device identity and position, not interface occupancy and connection endpoints | Adopt as `pt_get_network` | Well-sourced[^3][^4] |
| Detailed device view | No dedicated incident-link view | Adopt as `pt_get_device_info` | Well-sourced[^3][^4] |
| Device power | Only port power and internal module power cycling exist | Adopt as `pt_set_device_power` | Well-sourced[^3][^4] |
| Simulation mode/status/step | No dedicated tools | Adopt three `pt_*` tools | Well-sourced[^4][^5] |
| Native simple PDU and results | Target `pt_ping` uses device CLI; it does not expose Packet Tracer simulation frames | Adopt `pt_send_pdu` and `pt_get_pdu_results` | Well-sourced[^4][^5] |
| Packet Tracer command log | No direct command-log reader | Adopt `pt_get_command_log` | Well-sourced[^4][^5] |
| Socket.IO bridge on `127.0.0.1:7531` | Target has an integrated HTTP polling bridge on `127.0.0.1:54321` | Reject transport replacement | Well-sourced; upstream Packet Tracer 9 support is contested by open issue `#1`[^6] |
| Alternate installable `.pts` | Target already ships a larger module and control center | Reject replacement; inject wrappers through the current runtime patch | Well-sourced[^1][^2] |
| Device/module lookup maps | Target catalogs are broader and shared with validation | Reject upstream maps | Well-sourced[^1][^2] |
| PyPI tag publishing and `uvx` onboarding | The PyPI name points to a third repository at version `0.9.0` | Reject without package ownership and release authority | Well-sourced[^7][^8] |

## Integration Design

```mermaid
flowchart LR
    A[MCP client] --> B[New pt_* tool]
    B --> C[Target catalog and argument validation]
    C --> D[Existing HTTP bridge :54321]
    D --> E[Existing MCP-BUILDER webview]
    E --> F[Packet Tracer ipc API]
    F --> G[reportResult JSON]
    G --> B
```

The design preserves one bridge lifecycle and one public naming convention.
String arguments are serialized with `json.dumps`; direction and traffic-type
filters are allowlisted before command composition. Mutation tools check device
models and cable names in the target catalog rather than adopting upstream's
smaller MCP enums.[^2][^3]

No data chart is warranted: the quantitative facts are static source-inventory
counts rather than a time series or distribution. The capability matrix and
data-flow diagram expose the meaningful relationships without implying a
performance comparison that was not measured.

## Security and Compatibility Findings

Both repositories bind their live bridge to loopback, limiting exposure to the
local machine.[^3][^9] The target nevertheless exposes `pt_send_raw`, so the new
typed tools reduce the need for callers to compose arbitrary Packet Tracer
JavaScript. The adopted commands must preserve JSON escaping and return
structured failures without swallowing bridge or Packet Tracer errors.

The upstream bridge uses broad CORS on a loopback Socket.IO listener and enforces
a single connected plugin, request IDs, timeouts, and pending-call cleanup.[^9]
Those protocol features are sound, but the target bridge has a different polling
contract and its live tools already depend on it. Replacing the transport would
expand dependencies and inherit an unresolved report that the upstream window
is blank on Packet Tracer `9.0.0`.[^6]

Both codebases use the MIT License.[^10][^11] This report records the upstream
source and copyright. Adapted Packet Tracer API mappings remain attributable to
Muhammad Balawal; copied substantial source would require retaining his MIT
notice.

## Sources

[^1]: [cisco-pt-mcp at `4b277cb`](https://github.com/muhammadbalawal/cisco-pt-mcp/tree/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e) — upstream repository tree, README, package metadata, extension, and tests.
[^2]: [A-Town MCP-Packet-Tracer at `3e856a8`](https://github.com/A-Town-corp/MCP-Packet-Tracer/tree/3e856a832a476704edd1686ed733deddf8741916) — target repository tree, architecture, catalogs, tools, bridge, tests, and module.
[^3]: [Target MCP tool registry](https://github.com/A-Town-corp/MCP-Packet-Tracer/blob/3e856a832a476704edd1686ed733deddf8741916/src/packet_tracer_mcp/adapters/mcp/tool_registry.py) — existing live tools, runtime patches, naming, validation, and bridge calls.
[^4]: [Upstream Packet Tracer functions](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/extension/source/userfunctions.js) — native device, topology, simulation, PDU, power, and command-log implementations.
[^5]: [Simulation feature commit](https://github.com/muhammadbalawal/cisco-pt-mcp/commit/33579b507f1a78e86b738f0364107b6c662c5eb5) — introduction of simulation, PDU, power, and command-log tools.
[^6]: [Upstream issue #1](https://github.com/muhammadbalawal/cisco-pt-mcp/issues/1) — unresolved Packet Tracer 9.0.0 blank-window and port-listener report.
[^7]: [packet-tracer-mcp on PyPI](https://pypi.org/project/packet-tracer-mcp/0.9.0/) — current package version and ownership metadata.
[^8]: [Upstream PyPI publishing workflow](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/.github/workflows/publish.yml) — tag-triggered OIDC publishing design.
[^9]: [Upstream bridge implementation](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/mcp_server/bridge.py) — loopback Socket.IO protocol, timeouts, request correlation, and cleanup.
[^10]: [Upstream MIT License](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/LICENSE) — Muhammad Balawal copyright and license terms.
[^11]: [Target MIT License](https://github.com/A-Town-corp/MCP-Packet-Tracer/blob/3e856a832a476704edd1686ed733deddf8741916/LICENSE) — target repository license terms.

## Research Log

| # | Query | Tool | New sources | What it added |
|---|---|---|---|---|
| 1 | Open upstream repository URL; fall back to source clone | Web open, `git clone` | Upstream repository | Web fetch returned no content; clone established exact commit `4b277cb`, README, tree, and manifest |
| 2 | Inspect upstream MCP server, bridge, schemas, and tests | PowerShell file reads | 4 Python modules and smoke tests | Established 18-tool contract, Socket.IO protocol, validation level, and test depth |
| 3 | Inspect current A-Town architecture and live bridge | `git fetch`, PowerShell file reads | Target commit `3e856a8` | Confirmed target is current and already owns planning, catalogs, live HTTP bridge, and 60-tool documentation claim |
| 4 | Trace upstream tools into Packet Tracer JavaScript | PowerShell file reads | Upstream extension source | Located native `ipc` calls for simulation, PDU frames, command log, device power, and network inspection |
| 5 | Locate target live-tool and test precedents | `rg`, PowerShell file reads | Target registration tests and UI helper | Identified nested `FastMCP` tool pattern, runtime patches, JSON escaping, and current query limitations |
| 6 | Compare encrypted modules and target runtime patch | SHA-256, byte inspection, source reads | Both `.pts` artifacts | Proved modules differ and target has its own established extension and bridge contract |
| 7 | Review upstream history, releases, issues, and licenses | `git log`, GitHub CLI API | Upstream history, issue index, both licenses | Found simulation feature commit, seven tags, one open issue, and MIT compatibility |
| 8 | Review A-Town history, releases, and issues | `git log`, GitHub CLI API | Target repository API | Confirmed current main history and no published release or issue proposing a competing design |
| 9 | Inspect generator/catalog equivalents and simulation diff | `rg`, file reads, `git show` | Target catalog/generator; upstream feature diff | Added single-device/link gaps and verified upstream simulation tests only pin registration |
| 10 | Decrypt temporary module copies and compare manifests | Target `pts_decrypt.py`, `rg -a` | Decrypted module XML | Authenticated both files and measured `470901` versus `190043` XML bytes; confirmed parallel script-module structure |
| 11 | Check package availability and publishing workflows | `pip index`, workflow reads | PyPI index; both CI workflows | Found PyPI version `0.9.0` and upstream OIDC workflow; identified namespace risk |
| 12 | Verify PyPI ownership metadata | PyPI JSON API | PyPI project metadata | Confirmed the package points to `Mats2208/MCP-Packet-Tracer`, not A-Town |

**Totals:** 12 research rounds; 9 unique external repository/API locations
consulted; 14 primary source files read in full; 11 sources cited.

**Dead ends:** the first GitHub rendered-page fetch returned no content, so the
repository was cloned and inspected directly. `pts_decrypt.py --help` failed
because the script treats its first argument as a path; its source and README
were read, then temporary copies were decrypted with the documented positional
argument. The first text search over decrypted XML returned no matches because
the files were detected as binary; `rg -a` produced the manifest matches.
