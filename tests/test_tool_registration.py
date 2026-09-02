"""Regression guard for the full MCP tool surface.

The bridge/console tools are I/O-bound and are verified live against Packet
Tracer rather than unit-tested, but this test pins the registered tool set so a
rename or accidental removal is caught.
"""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP
from packet_tracer_mcp.adapters.mcp import tool_registry


EXPECTED = {
    # discovery / planning / deploy
    "pt_list_devices", "pt_list_templates", "pt_list_modules", "pt_get_device_details",
    "pt_query_topology", "pt_bridge_status", "pt_plan_topology", "pt_validate_plan",
    "pt_fix_plan", "pt_estimate_plan", "pt_explain_plan", "pt_full_build",
    "pt_generate_configs", "pt_generate_script", "pt_export", "pt_deploy", "pt_live_deploy",
    "pt_list_projects", "pt_load_project",
    # live mutation
    "pt_move_device", "pt_delete_device", "pt_rename_device", "pt_delete_link", "pt_set_port",
    "pt_add_device", "pt_add_link", "pt_add_module", "pt_install_modules_batch",
    "pt_get_network", "pt_get_device_info", "pt_set_device_power",
    "pt_set_simulation_mode", "pt_get_simulation_status", "pt_step_simulation",
    "pt_send_pdu", "pt_get_pdu_results", "pt_get_command_log", "pt_send_raw",
    # ACL / NAT
    "pt_apply_acl", "pt_apply_acl_object", "pt_remove_acl", "pt_remove_acl_object",
    "pt_apply_nat", "pt_remove_nat",
    # first wave of features
    "pt_apply_svi", "pt_configure_etherchannel", "pt_apply_port_security", "pt_apply_hsrp",
    "pt_add_static_route", "pt_apply_dhcp_relay", "pt_apply_ipv6",
    # CLI-parity wave
    "pt_apply_ios", "pt_configure_pc", "pt_apply_ospf", "pt_apply_rip", "pt_apply_eigrp",
    "pt_apply_bgp", "pt_apply_device_security", "pt_apply_management", "pt_apply_stp",
    "pt_apply_vtp", "pt_create_vlans", "pt_configure_interface", "pt_apply_loopback",
    "pt_configure_serial", "pt_apply_gre_tunnel",
    # observability / object-model wave
    "pt_run_command", "pt_ping", "pt_save_project", "pt_configure_wireless",
    "pt_get_running_config",
}


def _registered_names() -> set[str]:
    m = FastMCP("test")
    tool_registry.register_tools(m)
    return {t.name for t in asyncio.run(m.list_tools())}


def test_all_expected_tools_registered():
    names = _registered_names()
    assert names == EXPECTED


def test_tool_count_at_least_expected():
    names = _registered_names()
    assert len(names) == len(EXPECTED) == 71
