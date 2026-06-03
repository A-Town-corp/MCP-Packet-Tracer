"""System constants."""

# Default router/switch
DEFAULT_ROUTER = "2911"
DEFAULT_SWITCH = "2960-24TT"

# Layout (pixel position for the Packet Tracer canvas)
LAYOUT_X_START = 100
LAYOUT_Y_ROUTER = 100
LAYOUT_Y_SWITCH = 250
LAYOUT_Y_PC = 400
LAYOUT_X_SPACING = 250
LAYOUT_PC_X_SPACING = 80
LAYOUT_CLOUD_X_OFFSET = 150

# IP defaults
DEFAULT_LAN_BASE = "192.168.0.0/16"
DEFAULT_LINK_BASE = "10.0.0.0/16"
DEFAULT_LAN_PREFIX = 24
DEFAULT_LINK_PREFIX = 30
DEFAULT_DNS = "8.8.8.8"

# System capabilities (so the LLM knows what we support)
CAPABILITIES = {
    "version": "0.4.0",
    "routing": ["static", "static_floating", "ospf", "eigrp", "rip", "none"],
    "features": ["dhcp", "wan", "switching", "auto_fix", "explain", "dry_run",
                 "floating_routes", "ospf_multi_process", "eigrp_as_config",
                 "acl_standard", "acl_extended", "acl_apply_via_bridge",
                 "nat_static", "nat_dynamic", "pat_overload",
                 "vlan", "inter_vlan_routing", "router_on_a_stick", "trunk_802_1q"],
    "unsupported": ["stp"],
    "max_routers": 20,
    "max_pcs_per_lan": 24,
    "max_switches_per_router": 4,
}

# Masks lookup
PREFIX_TO_MASK = {
    8:  "255.0.0.0",
    16: "255.255.0.0",
    24: "255.255.255.0",
    25: "255.255.255.128",
    26: "255.255.255.192",
    27: "255.255.255.224",
    28: "255.255.255.240",
    29: "255.255.255.248",
    30: "255.255.255.252",
    32: "255.255.255.255",
}
