"""Plan models - the validated and complete result."""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator

from ...shared.enums import DeviceRole


class DevicePlan(BaseModel):
    """A concrete device in the plan."""
    name: str
    model: str
    category: str
    role: DeviceRole = DeviceRole.END_HOST
    x: int = 0
    y: int = 0
    interfaces: dict[str, str] = Field(default_factory=dict)
    gateway: str = ""


class LinkPlan(BaseModel):
    """A link between two devices.

    For topologies with VLANs, the SWITCH port is configured according to `mode`:
      - "access": the port is an access port in VLAN `access_vlan`.
      - "trunk":  the port is a trunk (802.1Q) carrying `trunk_allowed`.
    On links without a switch or without VLANs these fields are ignored.
    """
    device_a: str
    port_a: str
    device_b: str
    port_b: str
    cable: str = "straight"
    mode: str = "access"          # "access" | "trunk"
    access_vlan: int = 0          # access VLAN (0 = default/unspecified)
    trunk_allowed: list[int] = Field(default_factory=list)  # VLANs allowed on the trunk


class VLAN(BaseModel):
    """A VLAN defined on a switch (VLAN database)."""
    switch: str
    vlan_id: int
    name: str = ""


class Subinterface(BaseModel):
    """dot1Q subinterface of a router (router-on-a-stick).

    Each routed VLAN has its own subinterface `parent_port.vlan_id` with
    `encapsulation dot1Q vlan_id` and the gateway IP for that VLAN.
    """
    router: str
    parent_port: str   # e.g. "GigabitEthernet0/0"
    vlan_id: int
    ip: str
    mask: str


class ModulePlan(BaseModel):
    """An expansion module to install on a device.

    `slot` is passed as-is to PTBuilder's `addModule(device, slot, model)`.
    The format depends on the device's slot type:
      - HWIC (1941/2901/2911): "0/0", "0/1", "0/2", "0/3"
      - NM (2911):             "1" or "2"
      - NIM (ISR4321/4331):    "0" or "1"
      - Cloud-PT/Server:       "0".."6" depending on the available slot
    """
    device: str
    slot: str
    module: str  # e.g. "HWIC-2T", "NIM-2T"

    @field_validator("slot", mode="before")
    @classmethod
    def _coerce_slot_to_str(cls, v):
        # We accept int (e.g. 0) for backward compatibility and convert it to "0".
        if isinstance(v, bool):
            raise ValueError("slot must be str or int, not bool")
        if isinstance(v, int):
            return str(v)
        return v


class DHCPPool(BaseModel):
    """A DHCP pool on a router."""
    router: str
    pool_name: str
    network: str
    mask: str
    gateway: str
    dns: str = "8.8.8.8"
    excluded_start: str = ""
    excluded_end: str = ""


class StaticRoute(BaseModel):
    """A static route. admin_distance > 1 makes it a floating route."""
    router: str
    destination: str
    mask: str
    next_hop: str
    admin_distance: int = 1


class OSPFConfig(BaseModel):
    """OSPF configuration for a router."""
    router: str
    process_id: int = 1
    router_id: str = ""
    networks: list[dict] = Field(default_factory=list)


class RIPConfig(BaseModel):
    """RIP v2 configuration for a router."""
    router: str
    version: int = 2
    networks: list[str] = Field(default_factory=list)
    no_auto_summary: bool = True


class EIGRPConfig(BaseModel):
    """EIGRP configuration for a router."""
    router: str
    as_number: int = 100
    networks: list[dict] = Field(default_factory=list)  # [{network, wildcard}]
    no_auto_summary: bool = True


class ValidationCheck(BaseModel):
    """A check to run post-deploy."""
    check_type: str
    from_device: str
    to_target: str = ""
    expected: str = ""


class TopologyPlan(BaseModel):
    """Complete, validated plan, ready to generate scripts."""
    name: str = "topology"
    devices: list[DevicePlan] = Field(default_factory=list)
    modules: list[ModulePlan] = Field(default_factory=list)
    links: list[LinkPlan] = Field(default_factory=list)
    vlans: list[VLAN] = Field(default_factory=list)
    subinterfaces: list[Subinterface] = Field(default_factory=list)
    dhcp_pools: list[DHCPPool] = Field(default_factory=list)
    static_routes: list[StaticRoute] = Field(default_factory=list)
    ospf_configs: list[OSPFConfig] = Field(default_factory=list)
    rip_configs: list[RIPConfig] = Field(default_factory=list)
    eigrp_configs: list[EIGRPConfig] = Field(default_factory=list)
    validations: list[ValidationCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def device_by_name(self, name: str) -> DevicePlan | None:
        for d in self.devices:
            if d.name == name:
                return d
        return None

    def devices_by_category(self, category: str) -> list[DevicePlan]:
        return [d for d in self.devices if d.category == category]
