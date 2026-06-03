"""
HSRP (Hot Standby Router Protocol) CLI generator for Packet Tracer devices.

Generates the IOS body lines for a single interface participating in HSRP
first-hop redundancy. Returns body lines ONLY: a shared wrapper is
responsible for `enable` / `configure terminal` / `end` / `write memory`.
"""

from __future__ import annotations


def generate_hsrp_cli(
    interface: str,
    group: int,
    virtual_ip: str,
    priority: int = 100,
    preempt: bool = True,
    version: int = 2,
) -> list[str]:
    """
    Generate the IOS body lines that configure HSRP on one interface.

    Args:
        interface: Interface name (e.g. "GigabitEthernet0/0" or "Vlan10").
        group: HSRP group number.
        virtual_ip: The shared virtual gateway IP for the group.
        priority: HSRP priority (higher wins active role); defaults to 100.
        preempt: If True, emit `standby <group> preempt` so a higher-priority
            router reclaims the active role; defaults to True.
        version: HSRP version (2 supports larger group ranges and IPv6);
            defaults to 2.

    Returns:
        A list of IOS body lines. Sub-commands inside the interface block use
        a single leading space and the block is terminated with " exit".
    """
    if not interface or not str(interface).strip():
        raise ValueError("interface is required")
    if not virtual_ip or not str(virtual_ip).strip():
        raise ValueError("virtual_ip is required")
    if not isinstance(group, int) or not (0 <= group <= 4095):
        raise ValueError(f"group must be an integer in 0-4095, got {group!r}")
    if not isinstance(priority, int) or not (0 <= priority <= 255):
        raise ValueError(f"priority must be an integer in 0-255, got {priority!r}")
    if version not in (1, 2):
        raise ValueError(f"version must be 1 or 2, got {version!r}")

    lines: list[str] = [f"interface {interface}"]
    lines.append(f" standby version {version}")
    lines.append(f" standby {group} ip {virtual_ip}")
    lines.append(f" standby {group} priority {priority}")
    if preempt:
        lines.append(f" standby {group} preempt")
    lines.append(" exit")
    return lines
