"""IOS CLI generators for dynamic routing protocols (OSPF, RIP, EIGRP, BGP).

Pure functions: each returns a list of IOS BODY lines (no enable / configure
terminal / end / write memory; a shared wrapper adds those). Sub-commands inside
a router or interface block carry a single leading space and the block ends with
" exit". All functions raise ValueError on invalid or missing input.
"""

from __future__ import annotations


def generate_ospf_cli(
    process_id: int,
    networks: list[dict],
    router_id: str | None = None,
    passive_interfaces: list[str] | None = None,
    default_originate: bool = False,
) -> list[str]:
    """Generate IOS body lines that configure an OSPF process.

    Args:
        process_id: OSPF process ID; must be a positive integer.
        networks: Non-empty list of dicts, each with keys "network" (str),
            "wildcard" (str), and "area" (int or str).
        router_id: Optional OSPF router-id in dotted-decimal form.
        passive_interfaces: Optional list of interface names to mark passive.
        default_originate: If True, emit "default-information originate".

    Returns:
        A list of IOS body lines. Sub-commands use a single leading space and
        the block is terminated with " exit".
    """
    if not isinstance(process_id, int) or process_id < 1:
        raise ValueError(
            f"process_id must be a positive integer, got {process_id!r}"
        )
    if not networks:
        raise ValueError("networks must be a non-empty list")
    for i, entry in enumerate(networks):
        for key in ("network", "wildcard", "area"):
            if key not in entry:
                raise ValueError(
                    f"networks[{i}] is missing required key {key!r}"
                )

    lines: list[str] = [f"router ospf {process_id}"]
    if router_id is not None:
        lines.append(f" router-id {router_id}")
    for entry in networks:
        lines.append(
            f" network {entry['network']} {entry['wildcard']} area {entry['area']}"
        )
    for iface in passive_interfaces or []:
        lines.append(f" passive-interface {iface}")
    if default_originate:
        lines.append(" default-information originate")
    lines.append(" exit")
    return lines


def generate_rip_cli(
    networks: list[str],
    version: int = 2,
    no_auto_summary: bool = True,
    passive_interfaces: list[str] | None = None,
    default_originate: bool = False,
) -> list[str]:
    """Generate IOS body lines that configure RIP.

    Args:
        networks: Non-empty list of classful network addresses (str).
        version: RIP version; must be 1 or 2.
        no_auto_summary: If True, emit "no auto-summary" to disable automatic
            route summarization.
        passive_interfaces: Optional list of interface names to mark passive.
        default_originate: If True, emit "default-information originate".

    Returns:
        A list of IOS body lines. Sub-commands use a single leading space and
        the block is terminated with " exit".
    """
    if not networks:
        raise ValueError("networks must be a non-empty list")
    if version not in (1, 2):
        raise ValueError(f"version must be 1 or 2, got {version!r}")

    lines: list[str] = ["router rip"]
    lines.append(f" version {version}")
    for net in networks:
        lines.append(f" network {net}")
    if no_auto_summary:
        lines.append(" no auto-summary")
    for iface in passive_interfaces or []:
        lines.append(f" passive-interface {iface}")
    if default_originate:
        lines.append(" default-information originate")
    lines.append(" exit")
    return lines


def generate_eigrp_cli(
    as_number: int,
    networks: list,
    no_auto_summary: bool = True,
    router_id: str | None = None,
    passive_interfaces: list[str] | None = None,
) -> list[str]:
    """Generate IOS body lines that configure EIGRP.

    Args:
        as_number: EIGRP autonomous-system number; must be a positive integer
            in the range 1-65535.
        networks: Non-empty list where each item is either a plain classful
            network string (emits "network {net}") or a dict with keys
            "network" and "wildcard" (emits "network {network} {wildcard}").
        no_auto_summary: If True, emit "no auto-summary".
        router_id: Optional EIGRP router-id in dotted-decimal form.
        passive_interfaces: Optional list of interface names to mark passive.

    Returns:
        A list of IOS body lines. Sub-commands use a single leading space and
        the block is terminated with " exit".
    """
    if not isinstance(as_number, int) or not (1 <= as_number <= 65535):
        raise ValueError(
            f"as_number must be an integer in 1-65535, got {as_number!r}"
        )
    if not networks:
        raise ValueError("networks must be a non-empty list")

    lines: list[str] = [f"router eigrp {as_number}"]
    if router_id is not None:
        lines.append(f" eigrp router-id {router_id}")
    for entry in networks:
        if isinstance(entry, dict):
            lines.append(f" network {entry['network']} {entry['wildcard']}")
        else:
            lines.append(f" network {entry}")
    if no_auto_summary:
        lines.append(" no auto-summary")
    for iface in passive_interfaces or []:
        lines.append(f" passive-interface {iface}")
    lines.append(" exit")
    return lines


def generate_bgp_cli(
    as_number: int,
    router_id: str | None = None,
    neighbors: list[dict] | None = None,
    networks: list[dict] | None = None,
) -> list[str]:
    """Generate IOS body lines that configure BGP.

    Args:
        as_number: BGP autonomous-system number; must be a positive integer in
            the range 1-65535.
        router_id: Optional BGP router-id in dotted-decimal form.
        neighbors: Optional list of neighbor dicts, each with keys "ip" (str),
            "remote_as" (int), and optionally "description" (str). Emits a
            "neighbor {ip} remote-as {remote_as}" line and, when present, a
            "neighbor {ip} description {description}" line.
        networks: Optional list of network dicts, each with keys "network"
            (str) and "mask" (str). Emits "network {network} mask {mask}".

    Returns:
        A list of IOS body lines. Sub-commands use a single leading space and
        the block is terminated with " exit".
    """
    if not isinstance(as_number, int) or not (1 <= as_number <= 65535):
        raise ValueError(
            f"as_number must be an integer in 1-65535, got {as_number!r}"
        )
    if not neighbors and not networks:
        raise ValueError(
            "at least one of neighbors or networks must be a non-empty list"
        )

    lines: list[str] = [f"router bgp {as_number}"]
    if router_id is not None:
        lines.append(f" bgp router-id {router_id}")
    for nbr in neighbors or []:
        lines.append(f" neighbor {nbr['ip']} remote-as {nbr['remote_as']}")
        description = nbr.get("description")
        if description is not None:
            lines.append(f" neighbor {nbr['ip']} description {description}")
    for net in networks or []:
        lines.append(f" network {net['network']} mask {net['mask']}")
    lines.append(" exit")
    return lines
