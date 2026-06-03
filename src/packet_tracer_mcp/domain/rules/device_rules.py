"""Validation rules for devices."""

from __future__ import annotations
from ..models.plans import TopologyPlan
from ..models.errors import PlanError, ErrorCode, ValidationResult
from ...infrastructure.catalog.devices import resolve_model


def validate_devices(plan: TopologyPlan) -> list[PlanError]:
    """Validate that all devices are valid."""
    errors: list[PlanError] = []
    names_seen: set[str] = set()

    for dev in plan.devices:
        if dev.name in names_seen:
            errors.append(PlanError(
                code=ErrorCode.DUPLICATE_DEVICE_NAME,
                device=dev.name,
                message=f"Duplicate device name: '{dev.name}'",
                suggestion="Rename one of the duplicated devices.",
            ))
        names_seen.add(dev.name)

        model = resolve_model(dev.model)
        if model is None:
            errors.append(PlanError(
                code=ErrorCode.UNKNOWN_DEVICE_MODEL,
                device=dev.name,
                message=f"Unknown model '{dev.model}'.",
                suggestion=(
                    "Use a valid model. "
                    "Routers: 1841, 1941, 2620XM, 2621XM, 2811, 2901, 2911, "
                    "819HG-4G-IOX, 819HGW, 829, CGR1240, ISR4321, ISR4331, Router-PT, Router-PT-Empty. "
                    "Switches: 2950-24, 2950T-24, 2960-24TT, 3560-24PS, 3650-24PS, IE-2000, "
                    "Switch-PT, Switch-PT-Empty. "
                    "End devices: PC-PT, Server-PT, Laptop-PT, TabletPC-PT, SMARTPHONE-PT, Printer-PT, "
                    "WirelessEndDevice-PT, WiredEndDevice-PT, TV-PT, Home-VoIP-PT, Analog-Phone-PT, "
                    "Embedded-Server-PT. "
                    "Others: Cloud-PT, Cloud-PT-Empty, AccessPoint-PT, AccessPoint-PT-A, "
                    "AccessPoint-PT-N, AccessPoint-PT-AC, LAP-PT, 3702i, Hub-PT, Bridge-PT, "
                    "Repeater-PT, CoAxialSplitter-PT, 5505, 5506-X, WLC-PT, WLC-2504, WLC-3504, "
                    "DSL-Modem-PT, Cable-Modem-PT, Linksys-WRT300N, HomeRouter-PT-AC, "
                    "7960, Cell-Tower, Central-Office-Server, 802, 803, Sniffer, "
                    "MCU-PT, SBC-PT, DLC100, Meraki-MX65W, Meraki-Server, NetworkController, "
                    "Power Distribution Device, Copper Patch Panel, Fiber Patch Panel, "
                    "Copper Wall Mount, Fiber Wall Mount, Thing."
                ),
            ))

    return errors


def validate_port_capacity(plan: TopologyPlan) -> list[PlanError]:
    """Flag routers/switches with more links than physical ports.

    Subinterfaces (router-on-a-stick) do NOT consume extra ports: a single
    trunk link carries all VLANs, so only physical links are counted. Limited
    to routers and switches (end devices have 1 port).
    """
    errors: list[PlanError] = []
    link_count: dict[str, int] = {}
    for link in plan.links:
        link_count[link.device_a] = link_count.get(link.device_a, 0) + 1
        link_count[link.device_b] = link_count.get(link.device_b, 0) + 1

    for dev in plan.devices:
        if dev.category not in ("router", "switch"):
            continue
        model = resolve_model(dev.model)
        if model is None or not model.ports:
            continue
        cap = len(model.ports)
        used = link_count.get(dev.name, 0)
        if used > cap:
            errors.append(PlanError(
                code=ErrorCode.INSUFFICIENT_PORTS,
                device=dev.name,
                message=f"{dev.name} ({dev.model}) requires {used} ports but the model only has {cap}.",
                suggestion="Reduce links, use a model with more ports, or add an expansion module.",
            ))
    return errors
