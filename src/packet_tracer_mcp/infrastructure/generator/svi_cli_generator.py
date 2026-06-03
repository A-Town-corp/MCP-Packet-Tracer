"""IOS CLI generator for L3-switch inter-VLAN routing (SVI).

A multilayer switch (3560/3650) can route between VLANs by enabling
`ip routing` and giving each VLAN a Switched Virtual Interface (SVI)
with an IP address. This is the multilayer-switch alternative to
router-on-a-stick (dot1Q subinterfaces on a router).

Pure function: returns a list[str] of IOS BODY lines only. It does NOT
emit `enable`, `configure terminal`, `end` or `write memory`; a shared
wrapper adds those. Sub-commands inside a block get a single leading
space and every block ends with " exit".
"""

from __future__ import annotations


def generate_svi_cli(vlans: list[dict], enable_routing: bool = True) -> list[str]:
    """Generate the SVI / inter-VLAN routing config for a multilayer switch.

    Args:
        vlans: list of dicts, each with:
            - "vlan_id" (int):  the VLAN number (required)
            - "ip" (str):       the SVI IP address (required)
            - "mask" (str):     the SVI subnet mask, dotted-decimal (required)
            - "name" (str):     optional VLAN name; when present the VLAN is
                                created in the VLAN database before its SVI.
        enable_routing: when True, emit a leading `ip routing` line so the
            switch actually forwards traffic between the SVIs.

    Returns:
        A list of IOS body lines. For each VLAN: an optional VLAN-database
        block (`vlan <id>` / ` name <name>` / ` exit`) followed by the SVI
        block (`interface Vlan<id>` / ` ip address <ip> <mask>` /
        ` no shutdown` / ` exit`).
    """
    if not vlans and not enable_routing:
        raise ValueError("provide at least one VLAN (or enable_routing=True)")

    lines: list[str] = []

    if enable_routing:
        lines.append("ip routing")

    for vlan in vlans:
        vlan_id = vlan["vlan_id"]
        name = vlan.get("name")

        # Create the VLAN in the database first when a name is supplied.
        if name:
            lines.append(f"vlan {vlan_id}")
            lines.append(f" name {name}")
            lines.append(" exit")

        # SVI: the routed virtual interface for this VLAN.
        lines.append(f"interface Vlan{vlan_id}")
        lines.append(f" ip address {vlan['ip']} {vlan['mask']}")
        lines.append(" no shutdown")
        lines.append(" exit")

    return lines
