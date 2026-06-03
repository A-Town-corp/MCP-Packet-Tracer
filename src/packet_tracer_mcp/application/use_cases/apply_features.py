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
from ...infrastructure.generator.routing_cli_generator import (
    generate_ospf_cli, generate_rip_cli, generate_eigrp_cli, generate_bgp_cli,
)
from ...infrastructure.generator.device_mgmt_cli_generator import (
    generate_device_security_cli, generate_management_cli,
)
from ...infrastructure.generator.switching_cli_generator import (
    generate_stp_cli, generate_vtp_cli, generate_vlans_cli,
)
from ...infrastructure.generator.interface_cli_generator import (
    generate_interface_cli, generate_loopback_cli, generate_serial_cli,
    generate_gre_tunnel_cli,
)
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


# ---------------------------------------------------------------------------
# Universal escape hatch: apply arbitrary IOS lines to any device.
# ---------------------------------------------------------------------------
def apply_raw_ios_uc(device: str, config_lines: list[str], confirm_send: Sender = None,
                     dry_run: bool = False) -> dict:
    """Apply caller-supplied IOS body lines verbatim (no generator).

    `config_lines` are the body lines WITHOUT the enable/configure terminal/end/
    write memory wrapper; the shared apply_ios path adds those. Anything
    configurable from the Cisco CLI is reachable through this.
    """
    if not config_lines or not any(str(l).strip() for l in config_lines):
        raise ValueError("config_lines must contain at least one IOS command")
    body = [str(l) for l in config_lines]
    return apply_ios(device, body, confirm_send, dry_run)


# ---------------------------------------------------------------------------
# Routing protocols (apply to an existing device).
# ---------------------------------------------------------------------------
def apply_ospf_uc(router: str, process_id: int, networks: list[dict],
                  router_id: str | None = None, passive_interfaces: list[str] | None = None,
                  default_originate: bool = False, confirm_send: Sender = None,
                  dry_run: bool = False) -> dict:
    body = generate_ospf_cli(process_id, networks, router_id=router_id,
                             passive_interfaces=passive_interfaces,
                             default_originate=default_originate)
    return apply_ios(router, body, confirm_send, dry_run)


def apply_rip_uc(router: str, networks: list[str], version: int = 2,
                 no_auto_summary: bool = True, passive_interfaces: list[str] | None = None,
                 default_originate: bool = False, confirm_send: Sender = None,
                 dry_run: bool = False) -> dict:
    body = generate_rip_cli(networks, version=version, no_auto_summary=no_auto_summary,
                            passive_interfaces=passive_interfaces,
                            default_originate=default_originate)
    return apply_ios(router, body, confirm_send, dry_run)


def apply_eigrp_uc(router: str, as_number: int, networks: list,
                   no_auto_summary: bool = True, router_id: str | None = None,
                   passive_interfaces: list[str] | None = None, confirm_send: Sender = None,
                   dry_run: bool = False) -> dict:
    body = generate_eigrp_cli(as_number, networks, no_auto_summary=no_auto_summary,
                              router_id=router_id, passive_interfaces=passive_interfaces)
    return apply_ios(router, body, confirm_send, dry_run)


def apply_bgp_uc(router: str, as_number: int, router_id: str | None = None,
                 neighbors: list[dict] | None = None, networks: list[dict] | None = None,
                 confirm_send: Sender = None, dry_run: bool = False) -> dict:
    body = generate_bgp_cli(as_number, router_id=router_id, neighbors=neighbors,
                            networks=networks)
    return apply_ios(router, body, confirm_send, dry_run)


# ---------------------------------------------------------------------------
# Device management / hardening.
# ---------------------------------------------------------------------------
def apply_device_security_uc(device: str, hostname: str | None = None,
                             enable_secret: str | None = None, console_password: str | None = None,
                             vty_password: str | None = None, ssh: dict | None = None,
                             banner_motd: str | None = None, service_password_encryption: bool = False,
                             domain_name: str | None = None, confirm_send: Sender = None,
                             dry_run: bool = False) -> dict:
    body = generate_device_security_cli(
        hostname=hostname, enable_secret=enable_secret, console_password=console_password,
        vty_password=vty_password, ssh=ssh, banner_motd=banner_motd,
        service_password_encryption=service_password_encryption, domain_name=domain_name)
    return apply_ios(device, body, confirm_send, dry_run)


def apply_management_uc(device: str, ntp_servers: list[str] | None = None,
                        snmp: dict | None = None, logging_hosts: list[str] | None = None,
                        clock_timezone: dict | None = None, confirm_send: Sender = None,
                        dry_run: bool = False) -> dict:
    body = generate_management_cli(ntp_servers=ntp_servers, snmp=snmp,
                                   logging_hosts=logging_hosts, clock_timezone=clock_timezone)
    return apply_ios(device, body, confirm_send, dry_run)


# ---------------------------------------------------------------------------
# Switching: STP / VTP / VLAN database.
# ---------------------------------------------------------------------------
def apply_stp_uc(switch: str, mode: str | None = None, vlan_root: list[dict] | None = None,
                 portfast_interfaces: list[str] | None = None,
                 bpduguard_interfaces: list[str] | None = None, portfast_default: bool = False,
                 bpduguard_default: bool = False, confirm_send: Sender = None,
                 dry_run: bool = False) -> dict:
    body = generate_stp_cli(mode=mode, vlan_root=vlan_root,
                            portfast_interfaces=portfast_interfaces,
                            bpduguard_interfaces=bpduguard_interfaces,
                            portfast_default=portfast_default, bpduguard_default=bpduguard_default)
    return apply_ios(switch, body, confirm_send, dry_run)


def apply_vtp_uc(switch: str, mode: str, domain: str | None = None,
                 password: str | None = None, version: int | None = None,
                 confirm_send: Sender = None, dry_run: bool = False) -> dict:
    body = generate_vtp_cli(mode, domain=domain, password=password, version=version)
    return apply_ios(switch, body, confirm_send, dry_run)


def create_vlans_uc(switch: str, vlans: list[dict], confirm_send: Sender = None,
                    dry_run: bool = False) -> dict:
    body = generate_vlans_cli(vlans)
    return apply_ios(switch, body, confirm_send, dry_run)


# ---------------------------------------------------------------------------
# Interfaces / WAN.
# ---------------------------------------------------------------------------
def configure_interface_uc(device: str, interface: str, ip: str | None = None,
                           mask: str | None = None, description: str | None = None,
                           shutdown: bool | None = None, speed: str | None = None,
                           duplex: str | None = None, mtu: int | None = None,
                           no_switchport: bool = False, confirm_send: Sender = None,
                           dry_run: bool = False) -> dict:
    body = generate_interface_cli(interface, ip=ip, mask=mask, description=description,
                                  shutdown=shutdown, speed=speed, duplex=duplex, mtu=mtu,
                                  no_switchport=no_switchport)
    return apply_ios(device, body, confirm_send, dry_run)


def apply_loopback_uc(device: str, number: int, ip: str, mask: str,
                      description: str | None = None, confirm_send: Sender = None,
                      dry_run: bool = False) -> dict:
    body = generate_loopback_cli(number, ip, mask, description=description)
    return apply_ios(device, body, confirm_send, dry_run)


def configure_serial_uc(device: str, interface: str, encapsulation: str | None = None,
                        clock_rate: int | None = None, ip: str | None = None,
                        mask: str | None = None, ppp_auth: str | None = None,
                        username: str | None = None, password: str | None = None,
                        confirm_send: Sender = None, dry_run: bool = False) -> dict:
    body = generate_serial_cli(interface, encapsulation=encapsulation, clock_rate=clock_rate,
                               ip=ip, mask=mask, ppp_auth=ppp_auth, username=username,
                               password=password)
    return apply_ios(device, body, confirm_send, dry_run)


def apply_gre_tunnel_uc(device: str, tunnel_number: int, source: str, destination: str,
                        ip: str, mask: str, description: str | None = None,
                        confirm_send: Sender = None, dry_run: bool = False) -> dict:
    body = generate_gre_tunnel_cli(tunnel_number, source, destination, ip, mask,
                                   description=description)
    return apply_ios(device, body, confirm_send, dry_run)
