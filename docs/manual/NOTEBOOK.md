# Project Notebook

## Active Problem

Fold the useful capabilities from `muhammadbalawal/cisco-pt-mcp` commit
`4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e` into this repository without
replacing the existing live bridge, Packet Tracer extension, catalogs, or
`pt_*` tool API.

## User Journey

As an MCP client controlling an already-open Packet Tracer topology, I want to
add individual devices and links, inspect live topology details, control device
power and simulation state, send native Packet Data Units (PDUs), inspect PDU
results, and read the Packet Tracer command log so that I can build and verify a
network without falling back to arbitrary JavaScript.

## Current Plan

1. Add failing registration and behavior tests for 11 new `pt_*` tools.
2. Implement the tools through the existing loopback HTTP bridge on
   `127.0.0.1:54321`.
3. Reuse the target catalog for device and cable validation.
4. Update tool documentation and exact counts.
5. Run focused tests, the full test suite, package build, and security checks.

## Adopted Capabilities

| Tool | Purpose |
|---|---|
| `pt_add_device` | Add one catalog-validated device to the logical workspace |
| `pt_add_link` | Add one catalog-validated cable between two live interfaces |
| `pt_get_network` | Return devices, interfaces, occupancy, and connections as JSON |
| `pt_get_device_info` | Return one device and its incident connections as JSON |
| `pt_set_device_power` | Power one live device on or off |
| `pt_set_simulation_mode` | Switch between simulation and realtime modes |
| `pt_get_simulation_status` | Return mode, time, frame count, and frame index |
| `pt_step_simulation` | Move forward, backward, or reset simulation state |
| `pt_send_pdu` | Add a native simple ICMP PDU between two devices |
| `pt_get_pdu_results` | Return filtered PDU frame outcomes |
| `pt_get_command_log` | Return newest Packet Tracer command-log entries |

## Rejected Options

| Option | Reason rejected |
|---|---|
| Replace HTTP polling with Socket.IO on port `7531` | The existing bridge is integrated with all live tools; upstream issue `#1` reports a blank bridge window on Packet Tracer `9.0.0` |
| Replace `V3-MCP-BUILDER.pts` | The target module decrypts to `470901` bytes of XML and contains the established control center; the upstream module is a separate `190043`-byte XML module with a different ID and transport |
| Copy upstream device/module maps | The target catalog contains 74 device models, 150 modules, and 15 cable types and is already used by planning and validation |
| Add upstream PyPI publishing workflow | The `packet-tracer-mcp` PyPI name currently belongs to `Mats2208/MCP-Packet-Tracer` at version `0.9.0`; A-Town release authority was not provided |

## Log

### 2026-09-02 — Source comparison

- Target `HEAD` and `origin/main` both resolved to
  `3e856a832a476704edd1686ed733deddf8741916` before edits.
- Upstream `HEAD` resolved to
  `4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e`, release `v0.1.6`.
- Both repositories use the MIT License.
- The detailed comparison and source trail are in
  `docs/research/cisco-pt-mcp-capability-fold.md`.
- No project-local `AGENTS.md` or `docs/manual/` precedent existed before this
  manual was created.

### 2026-09-02 — TDD RED

- Baseline command: `python -m pytest -q tests/test_tool_registration.py`
  returned `2 passed in 0.63s`.
- RED command:
  `python -m pytest -q tests/test_tool_registration.py tests/test_upstream_capabilities.py`
  returned `20 failed in 2.25s`.
- Intended failure: the registration test listed all 11 adopted names as
  missing; behavior tests raised `ToolError: Unknown tool` for the same names.
- Installed MCP package inspected before using its API: `mcp==1.27.2`;
  `FastMCP.call_tool(name, arguments)` is the exercised public test path.
