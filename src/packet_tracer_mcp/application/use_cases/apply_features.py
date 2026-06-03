"""Use cases for the "apply a feature to an existing device" tools.

Each thin use case builds IOS body lines with its generator and applies them
via the shared confirming bridge path (apply_ios). They mirror the ACL/NAT
use cases: validation is delegated to the generators (which raise ValueError on
bad input), and the MCP tool resolves device-specific facts (like whether a
switch needs `switchport trunk encapsulation dot1q`) before calling here.
"""

from __future__ import annotations
from typing import Callable

from ...infrastructure.generator.svi_cli_generator import generate_svi_cli
from ...infrastructure.generator.etherchannel_cli_generator import generate_etherchannel_cli
from ...infrastructure.generator.port_security_cli_generator import generate_port_security_cli
from ...infrastructure.generator.hsrp_cli_generator import generate_hsrp_cli
from ...infrastructure.generator.static_route_cli_generator import (
    generate_static_route_cli, generate_dhcp_relay_cli,
)
from ...infrastructure.generator.ipv6_cli_generator import generate_ipv6_cli
from ._bridge_apply import apply_ios

Sender = Callable[[str], str | None] | None


def apply_svi_uc(switch: str, vlans: list[dict], enable_routing: bool = True,
                 confirm_send: Sender = None, dry_run: bool = False) -> dict:
    body = generate_svi_cli(vlans, enable_routing=enable_routing)
    return apply_ios(switch, body, confirm_send, dry_run)


def configure_etherchannel_uc(device_a: str, ports_a: list[str], device_b: str, ports_b: list[str],
                              channel_id: int, mode: str = "active", layer: str = "l2",
                              trunk: bool = True, allowed_vlans: list[int] | None = None,
                              access_vlan: int | None = None,
                              needs_encap_a: bool = False, needs_encap_b: bool = False,
                              confirm_send: Sender = None, dry_run: bool = False) -> dict:
    body_a = generate_etherchannel_cli(ports_a, channel_id, mode=mode, layer=layer, trunk=trunk,
                                       allowed_vlans=allowed_vlans, access_vlan=access_vlan,
                                       needs_encap=needs_encap_a)
    body_b = generate_etherchannel_cli(ports_b, channel_id, mode=mode, layer=layer, trunk=trunk,
                                       allowed_vlans=allowed_vlans, access_vlan=access_vlan,
                                       needs_encap=needs_encap_b)
    ra = apply_ios(device_a, body_a, confirm_send, dry_run)
    rb = apply_ios(device_b, body_b, confirm_send, dry_run)
    if ra["applied"] is None or rb["applied"] is None:
        combined = None
    else:
        combined = ra["applied"] and rb["applied"]
    return {
        "device_a": {"device": device_a, **ra},
        "device_b": {"device": device_b, **rb},
        "applied": combined,
        "dry_run": dry_run,
    }


def apply_port_security_uc(switch: str, interface: str, max_mac: int = 1, sticky: bool = True,
                           violation: str = "shutdown", confirm_send: Sender = None,
                           dry_run: bool = False) -> dict:
    body = generate_port_security_cli(interface, max_mac=max_mac, sticky=sticky, violation=violation)
    return apply_ios(switch, body, confirm_send, dry_run)


def apply_hsrp_uc(router: str, interface: str, group: int, virtual_ip: str, priority: int = 100,
                  preempt: bool = True, version: int = 2, confirm_send: Sender = None,
                  dry_run: bool = False) -> dict:
    body = generate_hsrp_cli(interface, group, virtual_ip, priority=priority, preempt=preempt, version=version)
    return apply_ios(router, body, confirm_send, dry_run)


def add_static_routes_uc(router: str, routes: list[dict], confirm_send: Sender = None,
                         dry_run: bool = False) -> dict:
    body = generate_static_route_cli(routes)
    return apply_ios(router, body, confirm_send, dry_run)


def apply_dhcp_relay_uc(device: str, interface: str, helper_addresses: list[str],
                        confirm_send: Sender = None, dry_run: bool = False) -> dict:
    body = generate_dhcp_relay_cli(interface, helper_addresses)
    return apply_ios(device, body, confirm_send, dry_run)


def apply_ipv6_uc(device: str, interfaces: list[dict], enable_routing: bool = True,
                  ospfv3: dict | None = None, confirm_send: Sender = None,
                  dry_run: bool = False) -> dict:
    body = generate_ipv6_cli(interfaces, enable_routing=enable_routing, ospfv3=ospfv3)
    return apply_ios(device, body, confirm_send, dry_run)
