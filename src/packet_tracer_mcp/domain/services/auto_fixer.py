"""
Plan auto-fixer.

Tries to correct common errors automatically:
  - Wrong cable type
  - Model upgrade when ports are missing
  - Invalid interface names
"""

from __future__ import annotations
from ..models.plans import TopologyPlan
from .validator import validate_plan
from ...infrastructure.catalog.devices import resolve_model
from ...infrastructure.catalog.cables import infer_cable
from ...shared.enums import PortSpeed

# 2911 has the most GigabitEthernet ports (3) among the common ISR routers,
# so it is the upgrade target when a router runs out of GigE ports.
_ROUTER_UPGRADE = "2911"


def fix_plan(plan: TopologyPlan) -> tuple[TopologyPlan, list[str]]:
    """
    Try to correct plan errors automatically.
    Returns (fixed_plan, list_of_applied_fixes).
    """
    fixes: list[str] = []

    # Fix 1: correct cables
    fixes.extend(_fix_cables(plan))

    # Fix 2: upgrade routers that lack enough ports
    fixes.extend(_fix_insufficient_ports(plan))

    # Fix 3: reassign invalid interfaces to valid ones on the model
    fixes.extend(_fix_invalid_ports(plan))

    # Re-validate
    validate_plan(plan)

    return plan, fixes


def _infer_port_speed(port_name: str) -> PortSpeed | None:
    """Infer the speed/type of a port from its name prefix (e.g.
    'GigabitEthernet0/0' -> GIGABIT_ETHERNET)."""
    for speed in PortSpeed:
        if port_name.startswith(speed.value):
            return speed
    return None


def _fix_cables(plan: TopologyPlan) -> list[str]:
    """Fix cables based on the connected device categories."""
    fixes = []
    for link in plan.links:
        dev_a = plan.device_by_name(link.device_a)
        dev_b = plan.device_by_name(link.device_b)
        if not dev_a or not dev_b:
            continue
        expected = infer_cable(dev_a.category, dev_b.category)
        if link.cable != expected:
            old = link.cable
            link.cable = expected
            fixes.append(
                f"Cable fixed: {link.device_a}<->{link.device_b} "
                f"from '{old}' to '{expected}'"
            )
    return fixes


def _fix_insufficient_ports(plan: TopologyPlan) -> list[str]:
    """Upgrade a router to 2911 only when it genuinely lacks enough TOTAL ports
    for its links AND the upgrade would satisfy the need. Comparing the link
    demand against the total port count (not GigE-only) matches
    validate_port_capacity, so this no longer rewrites perfectly valid
    FastEthernet / mixed-speed routers. If even 2911 is not enough, leave it so
    validation reports INSUFFICIENT_PORTS instead of mis-"fixing" the model."""
    fixes = []
    port_usage: dict[str, int] = {}

    for link in plan.links:
        for dev_name in (link.device_a, link.device_b):
            port_usage[dev_name] = port_usage.get(dev_name, 0) + 1

    best = resolve_model(_ROUTER_UPGRADE)
    best_cap = len(best.ports) if best else 0

    for dev in plan.devices:
        if dev.category != "router":
            continue
        model = resolve_model(dev.model)
        if not model:
            continue
        cap = len(model.ports)
        needed = port_usage.get(dev.name, 0)

        if needed > cap and dev.model != _ROUTER_UPGRADE and needed <= best_cap:
            old_model = dev.model
            dev.model = _ROUTER_UPGRADE
            fixes.append(
                f"Router {dev.name} upgraded from {old_model} to {_ROUTER_UPGRADE} "
                f"(needs {needed} ports; {old_model} only has {cap})"
            )

    return fixes


def _fix_invalid_ports(plan: TopologyPlan) -> list[str]:
    """Reassign invalid interfaces to a free port, preferring one of the SAME
    speed/type as the original (a router-router GigE link stays on GigE, not a
    serial port)."""
    fixes = []
    used_ports: dict[str, set[str]] = {d.name: set() for d in plan.devices}

    # First record ports already used validly
    for link in plan.links:
        for dev_name, port in [(link.device_a, link.port_a), (link.device_b, link.port_b)]:
            dev = plan.device_by_name(dev_name)
            if not dev:
                continue
            model = resolve_model(dev.model)
            if model and any(p.full_name == port for p in model.ports):
                used_ports[dev_name].add(port)

    # Now fix invalid ports
    for link in plan.links:
        for attr_dev, attr_port in [("device_a", "port_a"), ("device_b", "port_b")]:
            dev_name = getattr(link, attr_dev)
            port = getattr(link, attr_port)
            dev = plan.device_by_name(dev_name)
            if not dev:
                continue
            model = resolve_model(dev.model)
            if not model:
                continue
            if any(p.full_name == port for p in model.ports):
                continue  # already valid

            want_speed = _infer_port_speed(port)
            free = [p for p in model.ports if p.full_name not in used_ports[dev_name]]
            same_speed = [p for p in free if want_speed and p.speed == want_speed.value]
            chosen = same_speed or free
            if chosen:
                p = chosen[0]
                old_port = port
                setattr(link, attr_port, p.full_name)
                used_ports[dev_name].add(p.full_name)
                fixes.append(
                    f"Port fixed: {dev_name} from '{old_port}' to '{p.full_name}'"
                )

    return fixes
