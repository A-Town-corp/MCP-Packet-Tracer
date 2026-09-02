# Rebuild Runbook

## Prerequisites

| Requirement | Value |
|---|---|
| Operating system target | Windows 11; project code also supports macOS and Linux |
| Python | `3.11`, `3.12`, or `3.13` |
| Package backend | `hatchling` from `pyproject.toml` |
| Packet Tracer bridge address | `http://127.0.0.1:54321` |
| MCP HTTP endpoint | `http://127.0.0.1:39000/mcp` |

## Install

Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected result: `packet-tracer-mcp` and `pytest>=8.0.0` install without a
dependency resolver error.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip install build
.\.venv\Scripts\python.exe -m build
```

Expected result: pytest exits `0`; the build command creates one wheel and one
source distribution under `dist\` and exits `0`.

## Run with stdio

```powershell
.\.venv\Scripts\python.exe -m packet_tracer_mcp --stdio
```

The MCP client owns process startup and shutdown. Standard output is reserved
for MCP framing.

## Run with Streamable HTTP

```powershell
.\.venv\Scripts\python.exe -m packet_tracer_mcp
```

Expected endpoint: `http://127.0.0.1:39000/mcp`.

## Connect Packet Tracer

1. Open `V3-MCP-BUILDER.pts` through Packet Tracer's scripting-module
   configuration.
2. Open the MCP-BUILDER window and keep it visible.
3. If polling is not active, run the bootstrap returned by
   `pt_bridge_status` in **Extensions > Builder Code Editor**.
4. Call `pt_bridge_status`; require the exact state `Bridge ACTIVE and CONNECTED`
   before running live tools.

