"""
IPv6 dual-stack + OSPFv3 (IOS) configuration generator.

Pure functions that emit IPv6 BODY lines for Packet Tracer routers.
No I/O and no bridge calls: the caller wraps the result with
enable / configure terminal / end / write memory.
"""

from __future__ import annotations


def generate_ipv6_cli(
    interfaces: list[dict],
    enable_routing: bool = True,
    ospfv3: dict | None = None,
) -> list[str]:
    """
    Generate IPv6 dual-stack and (optionally) OSPFv3 BODY lines.

    interfaces item:
        {"interface": str, "ipv6": str (e.g. "2001:db8:1::1/64"),
         "ospf_area": int (optional)}
    ospfv3 (optional):
        {"process_id": int, "router_id": str (optional)}

    Returns a list[str] of IOS body lines only (no enable / configure
    terminal / end / write memory). Sub-commands inside an interface or
    router block carry a single leading space and each block ends with
    " exit".
    """
    lines: list[str] = []

    if enable_routing:
        lines.append("ipv6 unicast-routing")

    for item in interfaces:
        lines.append(f"interface {item['interface']}")
        lines.append(f" ipv6 address {item['ipv6']}")
        if ospfv3 and "ospf_area" in item:
            lines.append(
                f" ipv6 ospf {ospfv3['process_id']} area {item['ospf_area']}"
            )
        lines.append(" no shutdown")
        lines.append(" exit")

    if ospfv3:
        lines.append(f"ipv6 router ospf {ospfv3['process_id']}")
        if ospfv3.get("router_id"):
            lines.append(f" router-id {ospfv3['router_id']}")
        lines.append(" exit")

    return lines
