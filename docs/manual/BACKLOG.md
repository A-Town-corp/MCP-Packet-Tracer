# Backlog

## Now

- None.

## Next

- Decide whether A-Town will use a distinct PyPI package name or obtain control of `packet-tracer-mcp`; the current PyPI project points to `Mats2208/MCP-Packet-Tracer`.
- Raise repository-wide line coverage from the measured `64%` to at least `80%`; prioritize `tool_registry.py`, which measured `23%` because most pre-existing live-tool bodies lack offline behavior tests.
- Align `pyproject.toml` and README repository links with the intended A-Town ownership; current metadata still points to `mex-i/MCP-Packet-Tracer`.

## Icebox

- None.

## Done

- [2026-09-02] Added RED tests and implemented the 11 adopted live-control tools.
- [2026-09-02] Updated the public tool catalog and exact registered-tool count from 60 to 71.
- [2026-09-02] Completed focused tests, the full Python 3.13 suite, JavaScript syntax validation, package builds, wheel notice inspection, and security review.
- [2026-09-02] Compared `muhammadbalawal/cisco-pt-mcp` `v0.1.6` with A-Town `main` and recorded the adoption matrix.
