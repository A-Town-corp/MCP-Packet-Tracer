"""IOS CLI generator for interface, loopback, serial, and GRE tunnel blocks."""
from __future__ import annotations

_VALID_ENCAPSULATIONS = {"ppp", "hdlc", "frame-relay"}
_VALID_PPP_AUTH = {"chap", "pap"}


def generate_interface_cli(
    interface: str,
    ip: str | None = None,
    mask: str | None = None,
    description: str | None = None,
    shutdown: bool | None = None,
    speed: str | None = None,
    duplex: str | None = None,
    mtu: int | None = None,
    no_switchport: bool = False,
) -> list[str]:
    """Generate a single interface configuration block.

    Returns IOS body lines only (no enable / configure terminal / end).
    Sub-commands carry exactly one leading space; the block ends with ' exit'.

    Raises ValueError if:
      - interface is empty
      - exactly one of ip / mask is given (both or neither are required)
    """
    if not interface:
        raise ValueError("interface must be a non-empty string")
    if (ip is None) != (mask is None):
        raise ValueError("ip and mask must both be provided or both omitted")

    lines: list[str] = [f"interface {interface}"]

    if no_switchport:
        lines.append(" no switchport")
    if description is not None:
        lines.append(f" description {description}")
    if ip is not None and mask is not None:
        lines.append(f" ip address {ip} {mask}")
    if speed is not None:
        lines.append(f" speed {speed}")
    if duplex is not None:
        lines.append(f" duplex {duplex}")
    if mtu is not None:
        lines.append(f" mtu {mtu}")
    if shutdown is True:
        lines.append(" shutdown")
    elif shutdown is False:
        lines.append(" no shutdown")

    lines.append(" exit")
    return lines


def generate_loopback_cli(
    number: int,
    ip: str,
    mask: str,
    description: str | None = None,
) -> list[str]:
    """Generate a loopback interface configuration block.

    Returns IOS body lines only (no enable / configure terminal / end).

    Raises ValueError if:
      - number is negative
      - ip or mask is empty
    """
    if not isinstance(number, int) or number < 0:
        raise ValueError("number must be a non-negative integer")
    if not ip:
        raise ValueError("ip must be a non-empty string")
    if not mask:
        raise ValueError("mask must be a non-empty string")

    lines: list[str] = [f"interface Loopback{number}"]

    if description is not None:
        lines.append(f" description {description}")
    lines.append(f" ip address {ip} {mask}")
    lines.append(" exit")
    return lines


def generate_serial_cli(
    interface: str,
    encapsulation: str | None = None,
    clock_rate: int | None = None,
    ip: str | None = None,
    mask: str | None = None,
    ppp_auth: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> list[str]:
    """Generate a serial interface configuration block, optionally with PPP auth.

    If username and password are both given, a global `username ... password ...`
    line is emitted BEFORE the interface block (peer credential for CHAP/PAP).

    Returns IOS body lines only (no enable / configure terminal / end).

    Raises ValueError if:
      - interface is empty
      - exactly one of ip / mask is given
      - encapsulation is not one of 'ppp', 'hdlc', 'frame-relay'
      - ppp_auth is not one of 'chap', 'pap'
    """
    if not interface:
        raise ValueError("interface must be a non-empty string")
    if (ip is None) != (mask is None):
        raise ValueError("ip and mask must both be provided or both omitted")
    if encapsulation is not None and encapsulation not in _VALID_ENCAPSULATIONS:
        raise ValueError(
            f"encapsulation must be one of {sorted(_VALID_ENCAPSULATIONS)}, got {encapsulation!r}"
        )
    if ppp_auth is not None and ppp_auth not in _VALID_PPP_AUTH:
        raise ValueError(
            f"ppp_auth must be one of {sorted(_VALID_PPP_AUTH)}, got {ppp_auth!r}"
        )

    lines: list[str] = []

    # Global peer credential line comes before the interface block.
    if username is not None and password is not None:
        lines.append(f"username {username} password {password}")

    lines.append(f"interface {interface}")

    if ip is not None and mask is not None:
        lines.append(f" ip address {ip} {mask}")
    if encapsulation is not None:
        lines.append(f" encapsulation {encapsulation}")
    if clock_rate is not None:
        lines.append(f" clock rate {clock_rate}")
    if ppp_auth is not None:
        lines.append(f" ppp authentication {ppp_auth}")

    lines.append(" exit")
    return lines


def generate_gre_tunnel_cli(
    tunnel_number: int,
    source: str,
    destination: str,
    ip: str,
    mask: str,
    description: str | None = None,
) -> list[str]:
    """Generate a GRE tunnel interface configuration block.

    Returns IOS body lines only (no enable / configure terminal / end).

    Raises ValueError if:
      - tunnel_number is negative
      - source, destination, ip, or mask is empty
    """
    if not isinstance(tunnel_number, int) or tunnel_number < 0:
        raise ValueError("tunnel_number must be a non-negative integer")
    if not source:
        raise ValueError("source must be a non-empty string")
    if not destination:
        raise ValueError("destination must be a non-empty string")
    if not ip:
        raise ValueError("ip must be a non-empty string")
    if not mask:
        raise ValueError("mask must be a non-empty string")

    lines: list[str] = [f"interface Tunnel{tunnel_number}"]

    if description is not None:
        lines.append(f" description {description}")
    lines.append(f" ip address {ip} {mask}")
    lines.append(f" tunnel source {source}")
    lines.append(f" tunnel destination {destination}")
    lines.append(" tunnel mode gre ip")
    lines.append(" exit")
    return lines
