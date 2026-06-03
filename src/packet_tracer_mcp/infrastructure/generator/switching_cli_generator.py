"""IOS CLI generator for switching features (STP, VTP, VLANs)."""
from __future__ import annotations

_VALID_STP_MODES = ("pvst", "rapid-pvst")
_VALID_VTP_MODES = ("server", "client", "transparent", "off")


def generate_stp_cli(
    mode: str | None = None,
    vlan_root: list[dict] | None = None,
    portfast_interfaces: list[str] | None = None,
    bpduguard_interfaces: list[str] | None = None,
    portfast_default: bool = False,
    bpduguard_default: bool = False,
) -> list[str]:
    """Generate IOS body lines for Spanning Tree Protocol configuration.

    Args:
        mode: STP mode, one of "pvst" or "rapid-pvst".
        vlan_root: List of dicts with keys "vlan" (int), optionally "role"
            ("primary" or "secondary"), and optionally "priority" (int).
            "priority" takes precedence over "role" when both are present.
        portfast_default: Emit ``spanning-tree portfast default`` globally.
        bpduguard_default: Emit ``spanning-tree portfast bpduguard default``
            globally.
        portfast_interfaces: Interfaces on which to enable PortFast per-port.
        bpduguard_interfaces: Interfaces on which to enable BPDU Guard per-port.

    Returns:
        A list of IOS body lines. Global commands have no leading space.
        Interface sub-commands use a single leading space; blocks end with
        " exit".

    Raises:
        ValueError: If mode is not a recognised value, or if no parameter
            produces any output.
    """
    lines: list[str] = []

    # --- mode ---
    if mode is not None:
        if mode not in _VALID_STP_MODES:
            raise ValueError(
                f"Invalid STP mode {mode!r}. Must be one of {_VALID_STP_MODES}."
            )
        lines.append(f"spanning-tree mode {mode}")

    # --- per-VLAN root / priority ---
    for entry in vlan_root or []:
        vlan_id = entry["vlan"]
        if "priority" in entry:
            p = entry["priority"]
            if not isinstance(p, int) or p < 0 or p > 61440 or p % 4096 != 0:
                raise ValueError(
                    f"STP priority for vlan {vlan_id} must be a multiple of 4096 "
                    f"in 0-61440, got {p!r}")
            lines.append(f"spanning-tree vlan {vlan_id} priority {p}")
        elif "role" in entry:
            role = entry["role"]
            if role not in ("primary", "secondary"):
                raise ValueError(
                    f"STP root role for vlan {vlan_id} must be 'primary' or "
                    f"'secondary', got {role!r}")
            lines.append(f"spanning-tree vlan {vlan_id} root {role}")
        else:
            raise ValueError(
                f"vlan_root entry for vlan {vlan_id} must specify 'role' or 'priority'")

    # --- global portfast / bpduguard defaults ---
    if portfast_default:
        lines.append("spanning-tree portfast default")
    if bpduguard_default:
        lines.append("spanning-tree portfast bpduguard default")

    # --- per-interface PortFast ---
    for iface in portfast_interfaces or []:
        lines.append(f"interface {iface}")
        lines.append(" spanning-tree portfast")
        lines.append(" exit")

    # --- per-interface BPDU Guard ---
    for iface in bpduguard_interfaces or []:
        lines.append(f"interface {iface}")
        lines.append(" spanning-tree bpduguard enable")
        lines.append(" exit")

    if not lines:
        raise ValueError(
            "generate_stp_cli called with no arguments that produce output."
        )

    return lines


def generate_vtp_cli(
    mode: str,
    domain: str | None = None,
    password: str | None = None,
    version: int | None = None,
) -> list[str]:
    """Generate IOS body lines for VTP configuration.

    Order emitted: domain, version, mode, password.

    Args:
        mode: VTP mode, one of "server", "client", "transparent", or "off".
        domain: VTP domain name.
        password: VTP authentication password.
        version: VTP version number (1, 2, or 3).

    Returns:
        A list of IOS body lines with no leading spaces (global commands).

    Raises:
        ValueError: If mode is not a recognised VTP mode.
    """
    if mode not in _VALID_VTP_MODES:
        raise ValueError(
            f"Invalid VTP mode {mode!r}. Must be one of {_VALID_VTP_MODES}."
        )

    lines: list[str] = []
    if domain is not None:
        lines.append(f"vtp domain {domain}")
    if version is not None:
        lines.append(f"vtp version {version}")
    lines.append(f"vtp mode {mode}")
    if password is not None:
        lines.append(f"vtp password {password}")
    return lines


def generate_vlans_cli(vlans: list[dict]) -> list[str]:
    """Generate IOS body lines to define one or more VLANs.

    Each entry in *vlans* is a dict with:
        - ``vlan_id`` (int, 1-4094): VLAN number.
        - ``name`` (str or None, optional): VLAN name.

    The generated block for each VLAN is::

        vlan <id>
         name <name>   (omitted when name is absent or None)
         exit

    Args:
        vlans: Non-empty list of VLAN definition dicts.

    Returns:
        A list of IOS body lines. The ``vlan <id>`` line has no leading space;
        the ``name`` sub-command has one leading space; each block closes with
        " exit".

    Raises:
        ValueError: If *vlans* is empty or a VLAN ID is outside 1-4094.
    """
    if not vlans:
        raise ValueError("vlans must be a non-empty list.")

    lines: list[str] = []
    for entry in vlans:
        vlan_id = entry["vlan_id"]
        if not isinstance(vlan_id, int) or not (1 <= vlan_id <= 4094):
            raise ValueError(
                f"vlan_id {vlan_id!r} is out of range. Must be an integer 1-4094."
            )
        lines.append(f"vlan {vlan_id}")
        name = entry.get("name")
        if name:
            lines.append(f" name {name}")
        lines.append(" exit")
    return lines
