"""Request models - what comes in from the LLM."""

from __future__ import annotations
from pydantic import BaseModel, Field

from ...shared.enums import RoutingProtocol, TopologyTemplate
from ...shared.constants import (
    DEFAULT_ROUTER, DEFAULT_SWITCH,
    DEFAULT_LAN_BASE, DEFAULT_LINK_BASE,
)


class TopologyRequest(BaseModel):
    """High-level request - what the LLM generates from the user."""
    template: TopologyTemplate = TopologyTemplate.MULTI_LAN
    routers: int = Field(ge=1, le=20, default=2)
    switches_per_router: int = Field(ge=0, le=4, default=1)
    pcs_per_lan: list[int] | int = Field(default=3)
    laptops_per_lan: list[int] | int = Field(default=0)
    servers: int = Field(ge=0, le=10, default=0)
    access_points: int = Field(ge=0, le=20, default=0)
    has_wan: bool = False
    dhcp: bool = True
    routing: RoutingProtocol = RoutingProtocol.STATIC
    router_model: str = DEFAULT_ROUTER
    switch_model: str = DEFAULT_SWITCH
    base_network: str = DEFAULT_LAN_BASE
    inter_router_network: str = DEFAULT_LINK_BASE
    # Advanced routing options
    floating_routes: bool = False          # Generates backup static routes (AD=254)
    ospf_process_id: int = Field(ge=1, le=65535, default=1)
    eigrp_as: int = Field(ge=1, le=65535, default=100)
    # VLANs (router_on_a_stick template only). 0 = use the template default (2).
    vlans: int = Field(ge=0, le=8, default=0)
