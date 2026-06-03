"""
CLI (IOS) configuration generator for Packet Tracer devices.

From the TopologyPlan, generates command blocks ready to paste
into the terminal of each router/switch.
"""

from __future__ import annotations
from ...domain.models.plans import TopologyPlan, DevicePlan
from ...shared.utils import prefix_to_mask

def generate_all_configs(plan: TopologyPlan) -> dict[str, str]:
    """
    Generate CLI configs for all devices that need them.
    Returns {device_name: cli_block}.
    """
    configs: dict[str, str] = {}

    for dev in plan.devices:
        if dev.category == "router":
            configs[dev.name] = _router_config(dev, plan)
        elif dev.category == "switch":
            cfg = _switch_config(dev, plan)
            if cfg.strip():
                configs[dev.name] = cfg

    return configs


def _router_config(router: DevicePlan, plan: TopologyPlan) -> str:
    """Generate the complete config of a router."""
    lines: list[str] = []

    lines.append("enable")
    lines.append("configure terminal")
    lines.append(f"hostname {router.name}")
    lines.append("no ip domain-lookup")
    lines.append("")

    # --- dot1Q subinterfaces (router-on-a-stick) ---
    subs = [s for s in plan.subinterfaces if s.router == router.name]
    trunk_parents: list[str] = []
    for s in subs:
        if s.parent_port not in trunk_parents:
            trunk_parents.append(s.parent_port)

    # --- Physical interfaces (trunk ports are skipped: they carry no IP) ---
    for iface, ip_cidr in router.interfaces.items():
        if iface in trunk_parents:
            continue
        ip, prefix = ip_cidr.split("/")
        mask = prefix_to_mask(int(prefix))
        lines.append(f"interface {iface}")
        lines.append(f" ip address {ip} {mask}")
        lines.append(" no shutdown")
        lines.append(" exit")
        lines.append("")

    # Physical trunk port brought up WITHOUT IP, then one subinterface per VLAN.
    # The `exit` between blocks is MANDATORY: without it, PT does not create the
    # subinterface and the `ip address` commands land on the physical interface.
    for parent in trunk_parents:
        lines.append(f"interface {parent}")
        lines.append(" no ip address")
        lines.append(" no shutdown")
        lines.append(" exit")
        lines.append("")
    for s in subs:
        lines.append(f"interface {s.parent_port}.{s.vlan_id}")
        lines.append(f" encapsulation dot1Q {s.vlan_id}")
        lines.append(f" ip address {s.ip} {s.mask}")
        lines.append(" no shutdown")
        lines.append(" exit")
        lines.append("")

    # --- DHCP ---
    pools = [p for p in plan.dhcp_pools if p.router == router.name]
    for pool in pools:
        lines.append(f"ip dhcp excluded-address {pool.excluded_start} {pool.excluded_end}")
    for pool in pools:
        lines.append(f"ip dhcp pool {pool.pool_name}")
        lines.append(f" network {pool.network} {pool.mask}")
        lines.append(f" default-router {pool.gateway}")
        lines.append(f" dns-server {pool.dns}")
        lines.append(" exit")
        lines.append("")

    # --- Static routes ---
    static_routes = [r for r in plan.static_routes if r.router == router.name]
    for route in static_routes:
        line = f"ip route {route.destination} {route.mask} {route.next_hop}"
        if route.admin_distance != 1:
            line += f" {route.admin_distance}"
        lines.append(line)
    if static_routes:
        lines.append("")

    # --- OSPF ---
    ospf_cfgs = [o for o in plan.ospf_configs if o.router == router.name]
    for ospf in ospf_cfgs:
        lines.append(f"router ospf {ospf.process_id}")
        if ospf.router_id:
            lines.append(f" router-id {ospf.router_id}")
        for net in ospf.networks:
            lines.append(
                f" network {net['network']} {net['wildcard']} area {net['area']}"
            )
        lines.append(" exit")
        lines.append("")

    # --- RIP ---
    rip_cfgs = [r for r in plan.rip_configs if r.router == router.name]
    for rip in rip_cfgs:
        lines.append(f"router rip")
        lines.append(f" version {rip.version}")
        for net in rip.networks:
            lines.append(f" network {net}")
        if rip.no_auto_summary:
            lines.append(" no auto-summary")
        lines.append(" exit")
        lines.append("")

    # --- EIGRP ---
    eigrp_cfgs = [e for e in plan.eigrp_configs if e.router == router.name]
    for eigrp in eigrp_cfgs:
        lines.append(f"router eigrp {eigrp.as_number}")
        for net in eigrp.networks:
            lines.append(f" network {net['network']} {net['wildcard']}")
        if eigrp.no_auto_summary:
            lines.append(" no auto-summary")
        lines.append(" exit")
        lines.append("")

    lines.append("end")
    lines.append("write memory")

    return "\n".join(lines)


def _switch_port_for(link, switch_name: str) -> str | None:
    """Return the port on the `switch_name` side of a link, or None."""
    if link.device_a == switch_name:
        return link.port_a
    if link.device_b == switch_name:
        return link.port_b
    return None


def _needs_trunk_encap(model: str) -> bool:
    """Multilayer switches (3560/3650) require `switchport trunk
    encapsulation dot1q`; the 2950/2960 are dot1q-only and REJECT that command."""
    return any(m in (model or "") for m in ("3560", "3650"))


def _switch_config(switch: DevicePlan, plan: TopologyPlan) -> str:
    """Generate the config of a switch: hostname + VLANs + access/trunk ports.

    For a flat LAN without VLANs (plan.vlans empty and links in access mode with
    access_vlan=0) it only emits the hostname (ports stay in VLAN 1 by
    default), preserving the previous behavior.
    """
    lines: list[str] = ["enable", "configure terminal", f"hostname {switch.name}"]

    # --- VLAN database ---
    for v in [v for v in plan.vlans if v.switch == switch.name]:
        if v.vlan_id == 1:
            continue  # VLAN 1 exists by default
        lines.append(f"vlan {v.vlan_id}")
        if v.name:
            lines.append(f" name {v.name}")
        lines.append(" exit")

    # --- Ports (access / trunk) according to this switch's links ---
    for link in plan.links:
        sw_port = _switch_port_for(link, switch.name)
        if sw_port is None:
            continue
        if link.mode == "trunk":
            lines.append(f"interface {sw_port}")
            if _needs_trunk_encap(switch.model):
                lines.append(" switchport trunk encapsulation dot1q")
            lines.append(" switchport mode trunk")
            if link.trunk_allowed:
                allowed = ",".join(str(v) for v in link.trunk_allowed)
                lines.append(f" switchport trunk allowed vlan {allowed}")
            lines.append(" exit")
        elif link.access_vlan:
            lines.append(f"interface {sw_port}")
            lines.append(" switchport mode access")
            lines.append(f" switchport access vlan {link.access_vlan}")
            lines.append(" exit")

    lines.append("end")
    lines.append("write memory")
    return "\n".join(lines)


def generate_pc_config(device: DevicePlan, use_dhcp: bool | None = None) -> str:
    """Generate configuration instructions for a PC."""
    lines: list[str] = []
    lines.append(f"--- {device.name} ---")

    if device.interfaces:
        for iface, ip_cidr in device.interfaces.items():
            ip, prefix = ip_cidr.split("/")
            mask = prefix_to_mask(int(prefix))
            lines.append(f"IP Address: {ip}")
            lines.append(f"Subnet Mask: {mask}")
    if device.gateway:
        lines.append(f"Default Gateway: {device.gateway}")
    lines.append("DNS Server: 8.8.8.8")
    if use_dhcp:
        lines.append("Configure as DHCP to obtain an IP automatically.")
    else:
        lines.append("Configure a static IP with the values above.")
    return "\n".join(lines)
