"""
Static route + DHCP relay IOS-CLI generators for Packet Tracer devices.

Pure functions: each returns a list of IOS BODY lines (no enable / configure
terminal / end / write memory; a shared wrapper adds those). Sub-commands inside
an interface block carry a single leading space and the block ends with " exit".
"""

from __future__ import annotations


def generate_static_route_cli(routes: list[dict]) -> list[str]:
    """Generate `ip route` lines for static and default routes.

    Each route is a dict with keys:
      - destination: str (use "0.0.0.0" for a default route)
      - mask: str (use "0.0.0.0" for a default route)
      - next_hop: str
      - admin_distance: int (optional)

    The administrative distance is appended only when it is provided and is not
    the default value of 1.
    """
    lines: list[str] = []
    for route in routes:
        destination = route["destination"]
        mask = route["mask"]
        next_hop = route["next_hop"]
        line = f"ip route {destination} {mask} {next_hop}"
        admin_distance = route.get("admin_distance")
        if admin_distance is not None and admin_distance != 1:
            line += f" {admin_distance}"
        lines.append(line)
    return lines


def generate_dhcp_relay_cli(interface: str, helper_addresses: list[str]) -> list[str]:
    """Generate a DHCP relay (ip helper-address) interface block.

    Emits `interface {interface}`, then one indented `ip helper-address {addr}`
    for each helper address, and closes the block with ` exit`.
    """
    lines: list[str] = [f"interface {interface}"]
    for addr in helper_addresses:
        lines.append(f" ip helper-address {addr}")
    lines.append(" exit")
    return lines
