"""Shared utilities."""

from __future__ import annotations
import ipaddress
from .constants import PREFIX_TO_MASK


def safe_name(name: str, fallback: str = "topology") -> str:
    """Normalize a name into a filesystem-safe token.

    Used for project and file names: spaces become "_" and path
    separators are removed. Must be applied consistently across save/load/delete
    so the project round-trip works.
    """
    base = (name or "").strip() or fallback
    safe = base.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return safe or fallback


def is_port_or_subinterface(iface: str, valid_ports) -> bool:
    """True if `iface` is a valid physical port OR a dot1Q subinterface
    (`Gi0/0.10`) whose parent port is valid.

    Router-on-a-stick routers use subinterfaces that are NOT in the
    static catalog; ACL/NAT must be able to bind to them.
    """
    if iface in valid_ports:
        return True
    if "." in iface:
        return iface.split(".", 1)[0] in valid_ports
    return False


def prefix_to_mask(prefix: int) -> str:
    """Convert a CIDR prefix to a decimal mask."""
    if prefix in PREFIX_TO_MASK:
        return PREFIX_TO_MASK[prefix]
    bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return f"{(bits >> 24) & 0xFF}.{(bits >> 16) & 0xFF}.{(bits >> 8) & 0xFF}.{bits & 0xFF}"


def wildcard_mask(network: ipaddress.IPv4Network) -> str:
    """Compute the wildcard mask of a network."""
    mask_int = int(network.netmask)
    wildcard_int = mask_int ^ 0xFFFFFFFF
    return str(ipaddress.IPv4Address(wildcard_int))


def first_ip(interfaces: dict[str, str]) -> str:
    """Return the first IP from a dict of interfaces."""
    for ip_cidr in interfaces.values():
        return ip_cidr.split("/")[0]
    return "0.0.0.0"
