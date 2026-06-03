"""NAT/PAT models - configuration and modes.

NAT is applied post-deploy to an existing router via configureIosDevice
through the bridge, just like ACLs.

Three modes:
  static  - Fixed 1:1. Each private IP maps to a permanent public IP.
             Use when: an internal server must always be reachable from the
             internet with the same public IP (e.g. web, FTP, or mail server).

  dynamic - Pool of public IPs assigned on demand. The router chooses which
             public IP to assign to each internal host based on availability.
             Use when: you have more public IPs than overload justifies but
             fewer than internal hosts; or when per-public-IP tracking matters.
             Rare in modern networks.

  pat     - PAT (Port Address Translation) / NAT Overload. Many internal hosts
             share ONE public IP using port numbers as the
             differentiator. This is what almost every home and
             enterprise router does when it has a single ISP IP.
             Use when: you have 1 (or few) public IPs and N internal hosts.
             Sub-modes:
               use_interface_overload=True  -> ip nat inside source list X interface <outside> overload
               use_interface_overload=False -> ip nat inside source list X pool POOL overload
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

NATMode = Literal["static", "dynamic", "pat"]


class NATStaticMapping(BaseModel):
    """inside-local <-> inside-global pair for static NAT."""
    inside_local: str   # private IP, e.g. "192.168.1.10"
    inside_global: str  # fixed public IP, e.g. "200.1.1.5"


class NATPool(BaseModel):
    """Pool of public IPs for dynamic NAT or PAT with pool."""
    name: str = "NAT-POOL"
    start_ip: str         # first IP of the pool, e.g. "200.1.1.1"
    end_ip: str           # last IP of the pool,  e.g. "200.1.1.10"
    netmask: str          # network mask, e.g. "255.255.255.0"


class NATConfig(BaseModel):
    """Complete NAT/PAT configuration for a router."""
    router: str
    mode: NATMode

    # Interface connected to the private network (LAN)
    inside_interface: str   # e.g. "GigabitEthernet0/0"
    # Interface connected to the public network (WAN/Internet)
    outside_interface: str  # e.g. "GigabitEthernet0/1"

    # --- static mode ---
    # List of inside-local <-> inside-global pairs.
    # Required when mode="static".
    static_mappings: list[NATStaticMapping] = Field(default_factory=list)

    # --- dynamic / pat modes ---
    # Number or name of the ACL that identifies the internal hosts to translate.
    acl_number: str = "1"
    # Internal networks in "network wildcard" format, e.g. "192.168.1.0 0.0.0.255".
    # Used to generate the inline access-list. If the ACL already exists in PT
    # you can leave this list empty and the generator omits the access-list.
    inside_networks: list[str] = Field(default_factory=list)

    # Pool of public IPs. Required for dynamic; optional for pat when
    # use_interface_overload=True.
    pool: NATPool | None = None

    # PAT only: if True, generates "ip nat inside source list X interface <outside> overload"
    # instead of using a pool. Typical when the ISP assigns a single IP to the WAN interface.
    use_interface_overload: bool = False
