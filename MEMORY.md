# MEMORY.md — Project knowledge & rationale

> **Purpose of this file.** This is a complete brain-dump of everything learned while
> building, hardening, and publishing this project, written so another Claude (or you)
> can pick up with full context — including the *why* behind decisions, not just the *what*.
> The repo is **private**, so this intentionally records internal details (reverse-engineered
> crypto, IPC quirks, hard-won gotchas) that wouldn't go in a public README.
>
> If you're reading this on a fresh machine: skim §1–§4 first (what/how it runs), then
> §5 (the bridge) and §6 (tools). The rest is reference. **Verify claims against the
> current code before trusting them — this is a point-in-time snapshot.**

---

## 1. What this project is

A **Model Context Protocol (MCP) server** that gives any LLM full programmatic control of
**Cisco Packet Tracer (PT)**. You describe a network in natural language; the server plans
it, validates it, generates IOS configs + a PTBuilder JS script, and can **deploy and
live-configure it directly into a running PT instance** via an HTTP bridge — then read
state back (ping, show commands, running-config) to verify.

- Language: **Python ≥3.11**, **pydantic v2**, **FastMCP** (the `mcp` package).
- Architecture: **hexagonal** (domain / application / infrastructure / adapters).
- **60 MCP tools**, **5 MCP resources**, **369 tests** (all passing).
- Origin: forked/derived from `Mats2208/MCP-Packet-Tracer` (author "Mateo", MIT). Published
  under **`github.com/mex-i/MCP-Packet-Tracer` (private)**, version **0.5.0**.

### Why MCP + a bridge (the core idea)
PT has an internal scripting extension called **PTBuilder** that runs JS in a QtWebEngine
webview and can drive PT's engine via `$se('runCode', ...)` (Script Engine). PT exposes **no
external API**. So the trick is: run a tiny HTTP server (the "bridge") inside the MCP
process on `:54321`; the PTBuilder extension *polls* that bridge and executes whatever JS we
queue. That indirection is the whole reason live deploy works — see §5.

---

## 2. How to run it

```bash
# install (editable)
python -m venv .venv && .venv/bin/pip install -e .      # Windows: .venv\Scripts\pip install -e .
# run
python -m packet_tracer_mcp            # streamable-http on http://127.0.0.1:39000/mcp (default)
python -m packet_tracer_mcp --stdio    # stdio transport (desktop clients spawn it as a child)
# console entrypoint also exists: `pt-mcp`
```

- **Two transports** (`server.py:main`): default **streamable-http** `:39000`; `--stdio` for
  desktop clients. Either way the internal **bridge starts on `:54321`** inside the process.
- **Port 39000** was chosen to dodge common dev ports (3000/5000/8000/8080); **54321** is the
  internal PT bridge.
- **`pip install -e .`** makes `packet_tracer_mcp` importable from any directory, so
  `python -m packet_tracer_mcp --stdio` works without `cd`-ing into the repo. Clients
  (Claude Code/Desktop, Copilot, Codex) auto-launch it on demand.

### Tests / dev loop
```bash
.venv/bin/python -m pytest -q        # 369 tests, ~2s
```
**IMPORTANT: restart the MCP server to pick up tool changes.** Tools are registered at
startup (`tool_registry.register_tools`); runtime JS patches are injected per PT connection.
The working tree drives the server, so a restart is enough — no reinstall, no commit needed.
A **bridge protocol change is backward-incompatible** (client + server load together on
restart), so always restart after touching `live_bridge.py` or `_bridge_*` client code.

---

## 3. Repository layout & architecture

Hexagonal — keep the dependency arrows pointing inward (adapters → application → domain).

```
src/packet_tracer_mcp/
  server.py                     # FastMCP app + main() (transport selection)
  __main__.py                   # python -m entrypoint
  adapters/mcp/
    tool_registry.py            # ALL 60 @mcp.tool() definitions + runtime JS patches  (the big file)
    resource_registry.py        # 5 read-only catalog resources (pt://catalog/...)
  application/
    use_cases/                  # thin orchestration: plan/validate/fix/generate/full_build,
                                #   apply_acl, apply_nat, apply_features, _bridge_apply (shared)
    dto/                        # request/response DTOs
  domain/
    models/                     # TopologyPlan, Device, Link, requests.py (TopologyRequest)
    services/orchestrator.py    # plan_from_request() — turns a request into a TopologyPlan
    rules/                      # validation rules (nat_rules, ip_rules, ...), ErrorCodes
  infrastructure/
    catalog/                    # devices(74) / modules(150) / cables / aliases / templates
    generator/                  # PURE CLI/JS generators (no I/O): *_cli_generator.py +
                                #   ptbuilder_generator.py (emits the addDevice/addLink JS)
    execution/deploy_executor.py# clipboard deploy (Windows-native; see §10)
  shared/                       # enums, constants, utils (safe_name, is_port_or_subinterface)
offline-tools/                  # standalone .pts/.pkt file-format utilities (see §8)
V3-MCP-BUILDER.pts              # the PTBuilder extension that hosts the bridge (see §5)
tests/                          # 369 tests
```

**Design rationale:** generators are *pure* (plan → strings) so they're trivially unit-tested
without PT. The bridge/PT side is isolated in `tool_registry` + `_bridge_apply`. Apply-tools
(ACL/NAT/routing/etc.) all share one pattern: **validate → generate IOS → send via bridge →
confirm** (the device runs `reportResult(JSON.stringify({ok:...}))` so we know it actually
landed, instead of optimistically claiming success).

---

## 4. The two design pillars: universal CONFIG + universal OBSERVE

Most tools are conveniences. Two are the real backbone:

- **`pt_apply_ios`** — apply **arbitrary** IOS config lines to any device. The escape hatch
  for anything without a dedicated tool (QoS, route-maps, prefix-lists, IP SLA…). Wrapped and
  confirmed like the rest.
- **`pt_run_command`** — run **any** EXEC command (`show ...`, `ping`, `traceroute`) and
  capture the real terminal text. The universal verify counterpart.

Together they mean the agent can configure *and* check its work — a closed loop. Everything
else is ergonomics on top.

---

## 5. The HTTP bridge (the most important mechanism)

```
LLM → MCP tools → MCP server (:39000) → HTTP bridge (:54321) → PTBuilder webview → $se → PT engine
                                              ↑ PTBuilder POLLS the bridge ↑
```

- The bridge (`infrastructure/.../live_bridge.py`) queues JS. **PTBuilder polls `GET /next`
  every 500 ms**, runs the JS via `$se('runCode', ...)`, and **POSTs results to `/result`**.
- Two ways to get PTBuilder polling:
  1. **Recommended — the bundled `V3-MCP-BUILDER.pts` extension** ("MCP-BUILDER" v0.3.0,
     id `com.matsoto.mcpbuilder`). It contains the full bridge (`/next` + `/result`) and
     **auto-starts** on load (`DOMContentLoaded` → `startBridge` → `main()`). Install it
     into PT's `extensions/` folder, restart PT, open its window once, **leave the window
     visible**.
  2. **Fallback — paste-in snippet** into PT's stock *Builder Code Editor* (a `setInterval`
     that polls `/next`). One-off per session; supports fire-and-forget deploy but the
     bundled extension is what gives reliable result read-back.

### Why the window must stay visible (critical gotcha)
**QtWebEngine freezes a *hidden* webview's JS timers within seconds.** A minimized/hidden
builder window polls once, then the timer dies and the bridge goes silent. So the extension
calls `window.show()` on startup and the window must remain visible — park it in a corner.
A Web Worker can't rescue this because executing commands needs `$se`, which only lives on
the (frozen) main page.

### Why result read-back was historically broken — and the fix
`reportResult`/`queryTopology` didn't exist originally. The bridge build added: `runcode.js`
defines `reportResult(x)` (stash) + `bridgeRun(code)` (run, return stash or `""`).
`interface.js` polls → `$se("bridgeRun", cmd)` (returns a **Promise** resolving to the SE
function's return value) → POST to `/result`.
**Subtle bug that mattered:** a JS `null` marshals through QWebChannel as the **string
`"null"`**; POSTing that polluted `/result` and desynced *every* subsequent query (each read
a stale value). Fix: `bridgeRun` returns `""` not `null`, and `forward()` skips
`""`/`"null"`/`"undefined"`.

### Bridge reliability (from the 33-finding audit — see §11)
The original result channel had **no correlation/drain** and a fixed ~9s `/result` cap while
callers waited 10–20s, so slow ops *falsely* timed out and a late orphan result desynced the
*next* call. Fixed: `/result` honors `?timeout` (cap 30s) + a new `/drain` endpoint; the
client `_bridge_send_and_wait` drains stale results, passes its own timeout, and long-polls
(loops on HTTP 204) to the full deadline. `pt_apply_ios` reports `sent=True` on dispatch
(`applied=None` on timeout) rather than a misleading `sent=False`.

---

## 6. The 60 tools (by group)

Groups 1–12 are the **plan → deploy** pipeline; 13–19 **live-configure** any device already on
the canvas (they hit the bridge directly, so they work on a freshly built or hand-opened topo).

1. **Catalog** — `pt_list_devices`, `pt_list_templates`, `pt_get_device_details`
2. **Estimation** — `pt_estimate_plan`
3. **Planning** — `pt_plan_topology` (returns machine-readable JSON; feed it to other tools)
4. **Validation & fixing** — `pt_validate_plan`, `pt_fix_plan`, `pt_explain_plan`
5. **Generation** — `pt_generate_script`, `pt_generate_configs`
6. **Full pipeline** — `pt_full_build` (human-readable report; *not* JSON input for others)
7. **Live deploy** — `pt_deploy` (clipboard), `pt_live_deploy` (bridge), `pt_bridge_status`
8. **Topology interaction** — `pt_query_topology`, `pt_rename_device`, `pt_move_device`,
   `pt_delete_device`, `pt_delete_link`, `pt_set_port`, `pt_send_raw`
9. **Export & projects** — `pt_export`, `pt_list_projects`, `pt_load_project`
10. **Modules** — `pt_list_modules`, `pt_add_module`, `pt_install_modules_batch`
11. **ACL** — `pt_apply_acl`, `pt_remove_acl`, `pt_apply_acl_object`, `pt_remove_acl_object`
12. **NAT/PAT** — `pt_apply_nat`, `pt_remove_nat`
13. **Live routing** — `pt_apply_ospf`, `pt_apply_rip`, `pt_apply_eigrp`, `pt_apply_bgp`
14. **Live switching & VLANs** — `pt_create_vlans`, `pt_apply_vtp`, `pt_apply_stp`,
    `pt_configure_etherchannel`, `pt_apply_port_security`, `pt_apply_svi`
15. **Live L3 services** — `pt_add_static_route`, `pt_apply_hsrp`, `pt_apply_dhcp_relay`,
    `pt_apply_ipv6`
16. **Live interfaces & WAN** — `pt_configure_interface`, `pt_apply_loopback`,
    `pt_configure_serial`, `pt_apply_gre_tunnel`
17. **Live security & universal config** — `pt_apply_device_security`, `pt_apply_management`,
    **`pt_apply_ios`**
18. **End devices** — `pt_configure_pc`, `pt_configure_wireless`
19. **Observe & diagnostics** — **`pt_run_command`**, `pt_get_running_config`, `pt_ping`,
    `pt_save_project`

> `pt_apply_acl_object` / `pt_remove_acl_object` / `pt_set_port` came from the upstream
> `main` (the `lwAddDevice` commit) and were merged in — see §12. `acl_object` uses PT's
> object API (`AclProcess.addAcl`) instead of CLI: faster, fewer modal popups, but only
> binds to **physical** ports (use the CLI `pt_apply_acl` for subinterfaces).

### Why `pt_get_running_config` reads XML, not the console
Console `show running-config` is unreliable: PT ignores `terminal length 0`, pages with
`--More--`, and **idle-resets the console** ("Press RETURN…") mid-capture. So this tool reads
`device.serializeToXml()` and extracts the `<RUNNINGCONFIG>` block (each command is a
`<LINE>…</LINE>`; join with `\n`, `html.unescape`). Always complete, no enable/paging. The
extraction runs *in PT* so only the config text crosses the bridge, not the ~25 KB device XML.

---

## 7. PT IPC / JS API map (hard-won — dot-access ONLY)

Reverse-engineered live. **Enumerate** methods with `for (k in obj)` or
`Object.keys(Object.getPrototypeOf(obj))`.

> **HARD-ABORT gotcha:** on QWebChannel device/port proxies, **bracket access `obj[name]`**
> and **`getPort()` on a virtual/unknown interface** *crash the script engine* (bridgeRun
> returns `""` → None), **even inside try/catch**. Use literal **dot-access** only.

- **`ipc` top-level:** `appWindow()`, `network()`, `simulation()`, `systemFileManager()`,
  `options()`, `hardwareFactory()` — all called as functions.
- **`ipc.network()`** — `getDevice(name)`, `getDeviceAt(i)`, `getDeviceCount()`, `getLinkCount()`.
- **Device proxy** (~104 methods): `getName/setName`, `getType`, `getCommandLine`,
  `getProcess`, `getPortAt/getPortCount`, `serializeToXml`, `setDhcpFlag` (DHCP *client*
  flag only), `moveToLocation(x,y)`, `getXCoordinate/getYCoordinate`.
- **Port object:** `getIpAddress/getSubnetMask/setIpSubnetMask/setDefaultGateway/setDnsServerIp`,
  full IPv6 (`addIpv6Address/setv6DefaultGateway`), `setMacAddress`, `deleteLink`,
  `getAccessVlan/setAccessVlan/setAccessPort/addTrunkVlans/setAdminOpMode`,
  `getChannel/setChannel/setBandwidth/isWirelessPort` (**no SSID/auth setter**).
- **CommandLine** (`device.getCommandLine()`): `enterCommand`, `getOutput`, `getPrompt`,
  `getMode`, `flush`, `enterChar(" ")` (advance `--More--`). Console starts at the
  initial-config dialog (answer "no"); `enable` prompts "Password:".
- **`ipc.appWindow()`** (~113 methods): `fileNew/fileOpen/fileSave/fileSaveAs/
  fileSaveAsNoPrompt(path, true)` (**2nd bool arg mandatory** or "Invalid arguments"),
  `fileSaveToBytes` (~69 KB bytes obj), `getActiveFile`, `getActiveWorkspace`,
  `getDefaultFileSaveLocation`, `isSimulationMode`.
- **logicalWorkspace** (`ipc.appWindow().getActiveWorkspace().getLogicalWorkspace()`):
  `addDevice`/`removeDevice(name)`, `lwAddDevice`/`lwAddLink` (write to the **Logical**
  canvas so devices appear immediately — see §12), and shape/note **readback**
  (`getCanvasNoteIds/getCanvasNoteText`, `getCanvasEllipseIds`, etc.).

### Build-time gotchas via the bridge (these will bite you)
- **`pt_send_raw` JS must be a SINGLE LINE.** PTBuilder's `executeCode()` strips newlines
  (`code.replace(/\n/g, "")`), so multi-line source collapses and breaks. Use `;` between
  statements, and `/* */` block comments (never `//`).
- **`addLink(d1, p1, d2, p2, cableType)` — the 5th arg is MANDATORY** (omitting it throws
  "Invalid arguments for IPC call createLink", despite docs calling it optional). Working
  cable values used by the planner/bridge: **`"straight"`, `"cross"`, `"serial"`, `"fiber"`**
  (router↔router/switch↔switch = `cross`; router↔switch/host = `straight`). *Note:* the MCP
  server-instructions blurb says "crossover" — in practice `"cross"` is what works through
  `pt_send_raw` and `pt_live_deploy` plans.
- **Router subinterface creation needs an explicit `exit` between interface blocks** when
  sending IOS via `configureIosDevice`/`enterCommand`. Without it, `interface g0/0.10`
  silently fails and the `ip address` lines collapse onto the physical interface (last wins).
- **DHCP pools exclude `.1–.10`** by convention (gateway + headroom), so leases start at `.11`.
- **PCs have no `getCommandLine`** → you can't ping *from* a PC via the bridge. Ping from an
  IOS device with `pt_ping`, or check a PC's leased IP via `port.getIpAddress()`.
- **Ports per router model:** the default **2911 has 3 GigE ports** (`Gig0/0..0/2`). This caps
  per-router degree at 3 — that's why custom meshes are *partial* (e.g. one router dual-homed)
  rather than full, unless you add HWIC modules (`pt_add_module`, slot is a **string** like
  `"0/0"`) or use an L3 switch.

---

## 8. Offline tools (`offline-tools/`) — PT file-format utilities

Standalone Python that reads/writes/authors PT's encrypted file formats **without** running
PT. Same scheme as the public `pka2xml` project; the cipher keys are PT's fixed constants and
the CAST S-boxes are the **public RFC 2612** values (so this is interop, not secret-leaking).

| File | Purpose |
|------|---------|
| `cast256.py` | CAST-256 (RFC 2612) + EAX. **S-boxes baked in as literals** (see why below). Passes RFC vectors. |
| `eax.py` | EAX mode helper. |
| `pts_decrypt.py` / `pts_encrypt.py` | `.pts` extension modules — bit-perfect round-trip. |
| `pts_builder.py` | Author a new `.pts` from scratch (NetPilot-style). `build_pts(...)`. |
| `pkt_decrypt.py` / `pkt_encrypt.py` | `.pkt`/`.pka` save files — bit-perfect. **Needs `pip install twofish`.** |
| `pkt_inject_note.py` | Inject canvas **notes** + colored **ellipses** (VLAN circles) into a `.pkt` offline. |
| `example_build5.py` | Generates 5 distinct topologies as MCP deploy plans (also the device-placement reference). |

### Why the S-boxes are baked in
The original `cast256.py` *extracted* the 8 CAST S-boxes from the 78 MB PT binary at file
offset `0x323cbe4` at import time — hardcoded to a local path, useless on another machine.
But CAST-256's S-boxes are the **standard public RFC 2144/2612 constants** (the file even
asserts `S1[0..3] == 30fb40d4 9fa0ff0b 6beccd2f 3f258c7a`). So they were extracted once and
written in as literals → the module is now self-contained and portable (no PT binary needed).

### Why a Twofish venv on this Mac
`pkt_*` needs Twofish (pycryptodome lacks it). The `twofish` PyPI pkg was installed in
`~/pts-work/venv_tf` (its py3.13 `imp`→`importlib.util` was patched). On any machine, just
`pip install twofish`. The offline tools no longer hardcode that venv path.

---

## 9. Crypto specs (full detail)

### `.pts` (extension modules) — CAST-256-EAX
- **Cipher: EAX over CAST-256** (NOT AES — the binary's Rijndael RTTI misled an early attempt;
  confirmed via `N8CryptoPP9EAX_FinalINS_7CAST256ELb0EEE`).
- Key = **16 bytes of `0x12`**; Nonce/IV = **16 bytes of `0xfe`**; 16-byte EAX tag at the END.
- **Decode:** `file → inner_xor → CAST256-EAX-decrypt → outer_xor → qUncompress → outer_xor →
  qUncompress → XML`. **Encode = exact inverse.** Bit-perfect (same MD5).
  - `inner_xor` (decrypt): `out[i] = in[n-1-i] ^ (((1-i)*n) & 0xFF)` (reads backward).
  - `outer_xor` (self-inverse): even `i`: `^((n-i)&0xFF)`; odd `i`: `^((n+i)&0xFF)`.
  - `qCompress` = `struct.pack('>I', len) + zlib.compress(data, 6)` (Qt level 6, byte-identical).

### `.pkt`/`.pka` (save files) — Twofish-EAX ("pka2xml" scheme)
- **Cipher: Twofish-EAX.** Key = **16 bytes of `0x89`**; IV = **16 bytes of `0x10`**; 16-byte tag.
- **Decrypt (n = len):** (1) stage-1 `out[i]=data[n-1-i]^((n - i*n)&0xFF)`; (2) Twofish-EAX
  decrypt; (3) stage-3 `out[i]=data[i]^((n-i)&0xFF)` (self-inverse); (4) Qt **qUncompress
  once** → XML starting `<PACKETTRACER5><VERSION>9.0.0...`. Re-encrypt = exact inverse.

### Important: scripts/content are base64-in-CDATA
A `.pts`'s JS lives as `<SCRIPT>`/`<INTERFACE>` entries with
`<CONTENT><![CDATA[<base64 of source>]]></CONTENT>`. **So a plaintext grep of the decrypted
XML for code (e.g. "54321"/"setInterval") FALSELY returns nothing — base64-decode each CDATA
blob first.** (This exact mistake briefly made me think `V3-MCP-BUILDER.pts` had no bridge
code; it does.) There's no checksum/signature — the EAX tag is the only integrity check, so
inject-modified-content + re-encrypt Just Works.

### Canvas annotations (notes/shapes) are NOT live-scriptable → inject offline
`logicalWorkspace` *exposes* `addNote/drawLine/drawCircle`, but every argument form either
throws "Invalid arguments for IPC call addNote" or **hard-aborts the engine and creates
nothing** — they're interactive draw-tool entry points needing real mouse input (same
GUI-only class as server-Services and wireless-SSID). **Do not re-brute-force them — it
crashes the engine.** Instead, inject into the decrypted `.pkt` XML:
- **`<NOTE>`** goes in the **canvas `<NOTES>`** container (the one immediately after
  `</GRID_COLOR>` — NOT the option/activity-wizard NOTES). Schema:
  `<NOTE uuid="{…}"><X>..</X><Y>..</Y><Z>40000</Z><TEXT translate="true">..</TEXT><NOTECLUSTERID>1-1</NOTECLUSTERID></NOTE>`.
- **`<ELLIPSE>`** goes in the geometry **`<ELLIPSES>`** container (after `<RECTANGLES>`):
  TopLeftX/Y + BottomRightX/Y + `<Color><Red/><Green/><Blue/></Color>` +
  `<Filled OUTLINECOLOR="#hex" OUTLINED="true">0|1</Filled>` + `<ELLIPSECLUSTERID>`.
Verified rendering in PT after re-encrypt + reload.

---

## 10. Platform notes (you're on Windows now)

- **`pt_live_deploy` (bridge) is cross-platform** — it's just HTTP on localhost; the same
  `V3-MCP-BUILDER.pts` + visible window approach works on Windows.
- **`pt_deploy` (clipboard) is the Windows-native fallback.** `deploy_executor.py` copies the
  generated script to the clipboard — that path was historically Windows-only. On Mac the
  pipeline falls back to the live bridge / file export. On Windows clipboard deploy works.
- **PT folders differ by OS.** On Windows the extensions folder and the default save location
  live under the Packet Tracer install / user profile (e.g. `…\Cisco Packet Tracer X\extensions\`).
  Find the real save dir at runtime via `ipc.appWindow().getDefaultFileSaveLocation()`.
- **Paths in this repo's history/examples were Mac (`/Users/mexi/...`).** The shipped
  `offline-tools/` are now **portable** (no hardcoded paths). Use your own Windows paths.
- **venv:** `python -m venv .venv` then `.venv\Scripts\python -m pytest -q`. For `.pkt`
  tools also `pip install twofish`.

---

## 11. Reliability history (why the code looks careful)

The codebase went through deliberate hardening passes; that's why there are confirm-after-apply
patterns, guarded JSON loads, and defensive IO excepts:

- **English translation:** the upstream repo was Spanish (author Mats2208). The whole tree was
  translated to English (code identifiers/keys/JS payloads/enum values preserved byte-for-byte;
  only comments/docstrings/human messages changed). When the upstream `main` was later merged
  (§12) it reintroduced Spanish in 3 tools — that was re-translated. Repo is all-English now.
- **Adversarial reliability audit (33 confirmed findings, all fixed):** the bridge result
  channel (§5), a false-failure in `pt_run_command`'s poll loop, `auto_fixer` comparing total
  links vs GigE-only ports (rewrote valid FastEthernet routers), ACL/NAT named-removal
  guessing the type (now emits both standard+extended `no`), empty-plan rejection, planning
  tools returning `{"error"}` envelopes instead of crashing, generator input validation, etc.
  Regression tests in `tests/test_audit_fixes.py`.
- **Confirm-after-apply everywhere:** apply-tools send `reportResult(JSON.stringify({ok:...}))`
  and wait, so "applied: true" means PT actually accepted it — not optimism.

### Genuinely GUI-only in PT (not MCP gaps — PT design limits)
- Server **Services** tab: DHCP-server pool / DNS records / HTTP (`getProcess` returns
  nothing). BUT those functions are reachable on **routers** via IOS (`ip dhcp pool`,
  `ip dns server`) through `pt_apply_ios`.
- Wireless **SSID/authentication** (no port setter; channel/bandwidth do work).
- Full realtime ping output **from a PC** (PCs lack `getCommandLine`; use `pt_ping` from IOS).
- Canvas note/shape creation (see §9 → use offline injection).

---

## 12. Publication state & the merge story (read this before pushing)

- **Published:** `github.com/mex-i/MCP-Packet-Tracer` (**PRIVATE**), branch **`main`**, tag
  **`v0.5.0`**. Local branch `feature/feature-complete` == `main` (kept as a safety net).
- The original remote `Mats2208/MCP-Packet-Tracer` is **not writable** by the `mex-i` GitHub
  account (push → 403). So a fresh private repo was created under `mex-i`, `origin` was
  repointed there, and all `Mats2208` URLs were updated to `mex-i` (MIT copyright holder stays
  "Mateo"). To go public later: `gh repo edit mex-i/MCP-Packet-Tracer --visibility public`.
- **The merge that combined two feature lines.** The work branch (`feature/feature-complete`,
  57 tools) had diverged from the upstream `main`, which carried a separate commit (`bca2c3d`,
  "lwAddDevice/lwAddLink"). They were merged → **60 tools** (the 3 extras:
  `pt_apply_acl_object`, `pt_remove_acl_object`, `pt_set_port`). Conflicts (README,
  apply_acl, nat_rules, ptbuilder_generator) were resolved keeping the English /
  `is_port_or_subinterface` side; the generator now emits **`lwAddDevice`/`lwAddLink`** so
  deployed devices show up in the **Logical** view immediately (the global `addDevice` only
  writes the model + physical canvas).
- **That same merge had DELETED `V3-MCP-BUILDER.pts`** (the bridge extension) and the deletion
  silently rode into the first publish. It was restored byte-identical from git history and the
  README's Live Deploy Setup was corrected to lead with it (it auto-starts; see §5). **Lesson:
  watch for binary/asset deletions when merging upstream.**

### Version / metadata
- `pyproject.toml`: version `0.5.0`, full publishing metadata (authors, MIT license, readme,
  keywords, classifiers, project URLs, `dev` extra → pytest). `__version__` in
  `src/packet_tracer_mcp/__init__.py`. `CHANGELOG.md` documents 0.5.0 + 0.4.0.
- Builds clean: `pip wheel . --no-deps` → `packet_tracer_mcp-0.5.0-py3-none-any.whl`.

---

## 13. Design conventions worth keeping

- **IP plan for multi-LAN nets:** each network uses one `/16` (e.g. `10.N.0.0/16`); LANs are
  `10.N.{lan}.0/24` (gateway `.1`), router↔router links are `/30`s inside `10.N.100.x`. A
  **single OSPF statement** `network 10.N.0.0 0.0.255.255 area 0` on every router then
  advertises *all* of that router's interfaces — far simpler than per-link statements, and it
  converges fine for arbitrary topologies (chain/ring/mesh/tree/hub-spoke).
- **Device placement (aesthetics).** Don't let devices creep toward the far (right/bottom)
  edge. Use a tidy grid per network (routers in a row → switches below → PCs below), arrange
  multiple networks in a **2-column** grid (~1120 px wide, ~560 px tall cells, ~150 px start
  margin) so total width stays ~2300 px instead of sprawling to ~4000+. The architecture lives
  in the *links*, not the physical layout — a clean grid + link lines reads fine. Reusable
  generator: `offline-tools/example_build5.py` (5 distinct topologies, all 5R/≥3SW/10PC).
- **Verifying a network actually works** (not just "config applied"): ping across the whole
  routed path (e.g. R1 → the far LAN's gateway), check `show ip route` shows learned routes
  (`O` for OSPF), and confirm PCs got correct DHCP leases. The first ping of any path often
  drops on ARP (so 80% = 4/5 is healthy); a fresh `.pkt` reload needs ~30–40 s for OSPF to
  reconverge before pings pass.

---

## 14. Quick "where do I…" index

- Add a tool → `adapters/mcp/tool_registry.py` (`@mcp.tool()`), restart server.
- Add a CLI generator → `infrastructure/generator/*_cli_generator.py` (pure) + a thin use case
  in `application/use_cases/apply_features.py` + wire in `tool_registry`.
- Change planning/IP logic → `domain/services/orchestrator.py`, `domain/rules/`.
- Change the bridge → `infrastructure/.../live_bridge.py` + client `_bridge_*` in
  `tool_registry`/`_bridge_apply.py` (**restart required; protocol is co-versioned**).
- Touch PT file formats → `offline-tools/` (`.pts` = CAST-256, `.pkt` = Twofish; §9).
- Edit the PT-side bridge JS → the `V3-MCP-BUILDER.pts` scripts (decrypt with offline-tools,
  edit, re-encrypt) — or rebuild from PTBuilder source.
