# adapters/mcp/

MCP protocol layer - registers the tools and resources that the LLM can invoke.

## Files

### `tool_registry.py`
Registers 71 MCP tools.

Main function: `register_tools(mcp: FastMCP) -> None`

Each tool is defined as a function decorated with `@mcp.tool()` inside `register_tools()`.

#### Selected registered tools (34 of 71)

| Group | Tool | Description |
|-------|------|-------------|
| **Query** | `pt_list_devices` | Catalog of devices with ports |
| | `pt_list_templates` | Available topology templates |
| | `pt_get_device_details` | Detail of a specific model |
| **Estimation** | `pt_estimate_plan` | Dry-run without generating a complete plan |
| **Planning** | `pt_plan_topology` | Generates a complete plan -> JSON |
| **Validation** | `pt_validate_plan` | Typed errors/warnings |
| | `pt_fix_plan` | Auto-correction + re-validation |
| | `pt_explain_plan` | Natural-language explanation |
| **Generation** | `pt_generate_script` | PTBuilder JS script (+/- configs) |
| | `pt_generate_configs` | IOS CLI per device |
| **Pipeline** | `pt_full_build` | Plan + validate + generate + explain + estimate |
| **Deployment** | `pt_deploy` | Clipboard + files + instructions |
| | `pt_export` | Files to disk only |
| | `pt_live_deploy` | Direct deployment via HTTP bridge |
| **Bridge** | `pt_bridge_status` | Verify connection with PT |
| **Projects** | `pt_list_projects` | List saved topologies |
| | `pt_load_project` | Load a project by name |
| **Interaction** | `pt_add_device` | Add one catalog-validated live device |
| | `pt_add_link` | Add one catalog-validated live link |
| | `pt_query_topology` | Query current devices in PT |
| | `pt_get_network` | Query devices, ports, occupancy and links |
| | `pt_get_device_info` | Query one device and incident links |
| | `pt_delete_device` | Delete a device |
| | `pt_rename_device` | Rename a device |
| | `pt_move_device` | Move a device on the canvas |
| | `pt_set_device_power` | Power a device on or off |
| | `pt_delete_link` | Delete a link |
| | `pt_send_raw` | Send arbitrary JS to the Script Engine |
| **Simulation** | `pt_set_simulation_mode` | Select simulation or realtime mode |
| | `pt_get_simulation_status` | Read simulation state and frame position |
| | `pt_step_simulation` | Advance, rewind or reset simulation |
| | `pt_send_pdu` | Add a native simple ICMP PDU |
| | `pt_get_pdu_results` | Read and filter simulation-frame outcomes |
| | `pt_get_command_log` | Read redacted IOS command-log entries |

#### Internal helpers
- `_http_get(url)` / `_http_post(url, data)` - HTTP communication with the bridge
- `_js_escape(s)` - String escaping for JS
- `_bridge_is_up()` / `_bridge_pt_connected()` - Connectivity verification

### `resource_registry.py`
**~64 lines** - Registry of 5 static MCP resources.

Main function: `register_resources(mcp: FastMCP) -> None`

| Resource URI | Content |
|-------------|-----------|
| `pt://catalog/devices` | Complete catalog of devices with ports |
| `pt://catalog/cables` | Available cable types |
| `pt://catalog/aliases` | Common aliases -> real model |
| `pt://catalog/templates` | Templates with description, ranges, default routing |
| `pt://capabilities` | Version, features, server limits |
