"""Shared utilities."""

from __future__ import annotations
import ipaddress
import re
from .constants import PREFIX_TO_MASK

# Characters Windows forbids in a path component (< > : " / \ | ? *) plus the
# ASCII control range. On macOS/Linux only "/" and NUL are illegal, so a name
# accepted there can crash mkdir()/write_text() on Windows. Stripping the full
# Windows set keeps save/export/deploy behaviour identical on every OS.
_ILLEGAL_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserves these device names (case-insensitive, with or without an
# extension); creating "CON", "NUL", "COM1"… raises on Windows but not macOS.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_name(name: str, fallback: str = "topology") -> str:
    """Normalize a name into a filesystem-safe token.

    Used for project and file names. Produces the SAME result on Windows and
    macOS/Linux so a project saved on one OS round-trips on the other:
      - spaces become "_"
      - characters illegal on Windows (< > : " / \\ | ? * and control chars) -> "_"
      - trailing dots/spaces are stripped (Windows silently drops them)
      - Windows reserved device names (CON, NUL, COM1..LPT9) get a "_" prefix

    Must be applied consistently across save/load/delete so the round-trip works.
    """
    base = (name or "").strip() or fallback
    safe = _ILLEGAL_FS_CHARS.sub("_", base).replace(" ", "_")
    safe = safe.rstrip(" .") or fallback
    if safe.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        safe = "_" + safe
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
