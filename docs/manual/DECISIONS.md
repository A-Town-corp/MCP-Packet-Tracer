# Decisions

## ADR-001 — Preserve the existing HTTP bridge

- **Status:** Accepted on 2026-09-02.
- **Rule:** All adopted live controls use the existing HTTP polling bridge on
  `127.0.0.1:54321` and `_bridge_send_and_wait()`.
- **Why:** The bridge is already used by every A-Town live tool, supports both
  stdio and Streamable HTTP MCP transports, and requires no new dependency.
- **Rejected:** Add upstream `python-socketio`, `aiohttp`, port `7531`, and the
  upstream `.pts` module. This would create a second bridge lifecycle and inherit
  upstream issue `#1`, which reports failure on Packet Tracer `9.0.0`.

## ADR-002 — Add A-Town-native tool names

- **Status:** Accepted on 2026-09-02.
- **Rule:** New public tools use snake_case names beginning with `pt_`.
- **Why:** Every existing public tool in `tool_registry.py` follows this naming
  contract.
- **Rejected:** Register upstream camelCase names such as `sendPdu` and
  `getCommandLog`. Those names would create a second public convention and
  duplicate Packet Tracer implementation names.

## ADR-003 — Validate against target catalogs before mutation

- **Status:** Accepted on 2026-09-02.
- **Rule:** `pt_add_device` resolves models through `resolve_model()` and
  `pt_add_link` resolves cable names through the target cable catalog before a
  command is queued.
- **Why:** The target catalog is shared by planning, validation, and generation;
  accepting upstream's smaller hard-coded enums would create inconsistent live
  behavior.
- **Rejected:** Copy the upstream 11-model device enum or accept arbitrary model
  and cable strings.

## ADR-004 — Do not add publishing automation

- **Status:** Accepted on 2026-09-02.
- **Rule:** This change does not add a PyPI publish workflow or advertise `uvx`
  installation.
- **Why:** PyPI reports `packet-tracer-mcp` version `0.9.0` with repository URL
  `https://github.com/Mats2208/MCP-Packet-Tracer`; publishing authority for that
  name is outside this task.
- **Rejected:** Copy upstream `.github/workflows/publish.yml`, because its OIDC
  environment requires repository-specific PyPI trusted-publisher ownership.

## ADR-005 — Redact command-log credentials

- **Status:** Accepted on 2026-09-02.
- **Rule:** `pt_get_command_log` redacts commands entered at password, secret,
  or passphrase prompts and redacts recognized IOS secret-bearing command
  values before serializing the MCP response.
- **Why:** Packet Tracer command history can contain enable secrets, line
  passwords, username credentials, SNMP community strings, TACACS+ keys,
  RADIUS keys, key strings, and ISAKMP pre-shared keys.
- **Rejected:** Return the upstream command log unchanged. That would expose
  credentials to the MCP conversation and client logs.
