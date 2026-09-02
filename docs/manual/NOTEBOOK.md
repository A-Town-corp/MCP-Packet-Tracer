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

### 2026-09-02 — TDD GREEN and review

- The default `python` command initially imported
  `E:\MCP-Packet-Tracer\src\packet_tracer_mcp` rather than this checkout.
  Setting `PYTHONPATH` to
  `C:\Users\Fonem\MCP-Packet-Tracer\src` made the test target explicit.
- Focused command:
  `python -m pytest -q tests/test_tool_registration.py tests/test_upstream_capabilities.py`
  returned `22 passed in 1.92s` after implementation and security hardening.
- Final Python `3.13` command:
  `coverage run --source=src/packet_tracer_mcp -m pytest -q` returned
  `389 passed in 5.12s`.
- `node --check -` parsed the complete injected `_RUNTIME_PATCHES_JS` bundle
  and returned exit code `0`.
- `pip-audit==2.10.1` reported `No known vulnerabilities found`; the local
  editable package was skipped because version `0.5.0` is not the current PyPI
  artifact.
- `bandit==1.9.4` initially found seven pre-existing warnings in
  `tool_registry.py`. Loopback URL sinks now have an enforced bridge-prefix
  guard, silent `except: pass` paths now use specific JSON fallback handling,
  and the route-literal false positive is documented. The rerun reported
  `No issues identified`.
- Full-suite line coverage is `64%` (`3022/4751` statements). Executable lines
  changed in `tool_registry.py` are `89.0%` covered (`121/136`). The global
  shortfall is captured in `BACKLOG.md` rather than presented as complete.
- Python `3.13` package build succeeded with `build==1.6.0`, producing
  `packet_tracer_mcp-0.5.0.tar.gz` and
  `packet_tracer_mcp-0.5.0-py3-none-any.whl`.
- Wheel and source-distribution inspection confirmed that both `LICENSE` and
  `THIRD_PARTY_NOTICES.md` are included. Hatchling `1.32.0` reads the explicit
  `project.license-files` declaration from `pyproject.toml`.
