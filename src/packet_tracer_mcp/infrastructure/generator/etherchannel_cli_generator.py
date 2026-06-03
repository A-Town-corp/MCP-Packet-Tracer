"""IOS CLI generator for EtherChannel / Port-channel.

Bundles several physical interfaces into a single logical Port-channel and
configures the resulting logical interface as an L2 trunk, an L2 access port,
or an L3 routed port.

Returns a list[str] of IOS BODY lines only: it does NOT include `enable`,
`configure terminal`, `end` or `write memory` (a shared wrapper adds those).
The lines are ready to consume directly or to feed into such a wrapper.
"""

from __future__ import annotations


def generate_etherchannel_cli(
    interfaces: list[str],
    channel_id: int,
    mode: str = "active",
    layer: str = "l2",
    trunk: bool = True,
    allowed_vlans: list[int] | None = None,
    access_vlan: int | None = None,
    needs_encap: bool = False,
) -> list[str]:
    """Generate the IOS lines for an EtherChannel bundle.

    Each member interface is added to the channel group, then the logical
    `Port-channel<channel_id>` interface is configured.

    Args:
        interfaces: Physical member interfaces (e.g. ["GigabitEthernet0/1"]).
        channel_id: Port-channel number (e.g. 1 -> Port-channel1).
        mode: Channel mode. LACP: active/passive. PAgP: desirable/auto.
            Static: on. Emitted verbatim in `channel-group <id> mode <mode>`.
        layer: "l2" for a switched bundle, "l3" for a routed bundle.
        trunk: For layer=="l2", True -> trunk port, False -> access port.
        allowed_vlans: For an L2 trunk, the VLANs to allow (CSV is built).
        access_vlan: For an L2 access port, the VLAN to assign.
        needs_encap: For an L2 trunk on a multilayer switch (3560/3650), emit
            `switchport trunk encapsulation dot1q`. The 2960 is dot1q-only and
            REJECTS that command, so keep this False for the 2960.

    Returns:
        A list of IOS body lines. Sub-commands inside a block get a single
        leading space, and every block ends with " exit".
    """
    # Normalize + validate so a typo (e.g. "L3") errors loudly through the tool's
    # ValueError handler instead of silently falling through to an L2 trunk.
    layer = (layer or "").strip().lower()
    if layer not in {"l2", "l3"}:
        raise ValueError(f"invalid layer {layer!r}; expected 'l2' or 'l3'")
    mode = (mode or "").strip().lower()
    if mode not in {"active", "passive", "desirable", "auto", "on"}:
        raise ValueError(
            f"invalid mode {mode!r}; expected active/passive (LACP), "
            f"desirable/auto (PAgP), or on (static)")
    if not isinstance(channel_id, int) or not (1 <= channel_id <= 48):
        raise ValueError(f"channel_id must be an integer in 1-48, got {channel_id!r}")
    if not interfaces:
        raise ValueError("interfaces must be a non-empty list")

    lines: list[str] = []

    # --- Member interfaces join the channel group ---
    for iface in interfaces:
        lines.append(f"interface {iface}")
        lines.append(f" channel-group {channel_id} mode {mode}")
        lines.append(" exit")

    # --- Logical Port-channel interface ---
    lines.append(f"interface Port-channel{channel_id}")
    if layer == "l3":
        # Routed bundle: take the port out of switching. The caller adds the IP.
        lines.append(" no switchport")
    elif trunk:
        # Multilayer switches require explicit dot1q encapsulation; the
        # dot1q-only 2960 rejects it, so it is gated by needs_encap.
        if needs_encap:
            lines.append(" switchport trunk encapsulation dot1q")
        lines.append(" switchport mode trunk")
        if allowed_vlans:
            csv = ",".join(str(v) for v in allowed_vlans)
            lines.append(f" switchport trunk allowed vlan {csv}")
    else:
        # Access port.
        lines.append(" switchport mode access")
        if access_vlan is not None:
            lines.append(f" switchport access vlan {access_vlan}")
    lines.append(" exit")

    return lines
