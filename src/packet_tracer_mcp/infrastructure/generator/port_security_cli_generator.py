"""IOS CLI generator for switchport port-security.

Produces the body lines that configure port-security on an access port.
The output is a list[str] of IOS BODY lines only (NO enable / configure
terminal / end / write memory); a shared wrapper adds those.

Sub-commands inside the interface block carry a SINGLE leading space and
the block is closed with " exit", matching the house style of the other
generators in this package.
"""

from __future__ import annotations


# Allowed violation modes for `switchport port-security violation`.
_VIOLATION_MODES = ("shutdown", "restrict", "protect")


def generate_port_security_cli(
    interface: str,
    max_mac: int = 1,
    sticky: bool = True,
    violation: str = "shutdown",
) -> list[str]:
    """Generate the IOS lines to enable port-security on an access port.

    Args:
        interface: Interface name (e.g. "FastEthernet0/1").
        max_mac: Maximum number of secure MAC addresses on the port.
        sticky: When True, emit `mac-address sticky` to learn MACs dynamically.
        violation: One of {"shutdown", "restrict", "protect"}; controls the
            action taken when the maximum is exceeded.

    Returns:
        A list of IOS body lines for the interface block.

    Raises:
        ValueError: If `violation` is not one of the three allowed modes.
    """
    if violation not in _VIOLATION_MODES:
        raise ValueError(
            f"invalid violation mode {violation!r}; "
            f"expected one of {_VIOLATION_MODES}"
        )

    lines: list[str] = [
        f"interface {interface}",
        " switchport mode access",
        " switchport port-security",
        f" switchport port-security maximum {max_mac}",
    ]
    if sticky:
        lines.append(" switchport port-security mac-address sticky")
    lines.append(f" switchport port-security violation {violation}")
    lines.append(" exit")
    return lines
