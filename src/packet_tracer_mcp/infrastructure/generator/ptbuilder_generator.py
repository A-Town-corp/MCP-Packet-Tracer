"""
PTBuilder script generator.

Converts a validated TopologyPlan into JavaScript compatible
with the Packet Tracer PTBuilder extension.
"""

from __future__ import annotations
import json
from ...domain.models.plans import TopologyPlan
from ...shared.constants import (
    PT_DEVICE_TYPE,
    PT_DEVICE_TYPE_DEFAULT,
    PT_CONNECT_TYPE,
    PT_CONNECT_TYPE_DEFAULT,
)


def generate_ptbuilder_script(plan: TopologyPlan) -> str:
    """Generate a PTBuilder JS script from a validated plan."""
    lines: list[str] = []

    for dev in plan.devices:
        device_type = PT_DEVICE_TYPE.get(dev.category, PT_DEVICE_TYPE_DEFAULT)
        lines.append(
            f'lwAddDevice("{dev.name}", {device_type}, "{dev.model}", {dev.x}, {dev.y});'
        )

    for mod in plan.modules:
        lines.append(f'addModule("{mod.device}", "{mod.slot}", "{mod.module}");')

    for link in plan.links:
        connect_type = PT_CONNECT_TYPE.get(link.cable, PT_CONNECT_TYPE_DEFAULT)
        lines.append(
            f'lwAddLink("{link.device_a}", "{link.port_a}", '
            f'"{link.device_b}", "{link.port_b}", {connect_type});'
        )

    return "\n".join(lines)


def generate_executable_script(plan: TopologyPlan) -> str:
    """
    Generate a complete, executable JS script: devices, links,
    configureIosDevice() for routers/switches, and configurePcIp() for PCs.
    """
    from .cli_config_generator import generate_all_configs

    lines: list[str] = []
    lines.append(generate_ptbuilder_script(plan))

    configs = generate_all_configs(plan)
    for device_name, cli_block in configs.items():
        lines.append(f'configureIosDevice({json.dumps(device_name)}, {json.dumps(cli_block)});')

    pcs = [d for d in plan.devices if d.category in ("pc", "server", "laptop")]
    for pc in pcs:
            if pc.interfaces:
                iface_ip = next(iter(pc.interfaces.values()), None)
                if iface_ip:
                    ip, prefix = iface_ip.split("/")
                    from ...shared.utils import prefix_to_mask
                    mask = prefix_to_mask(int(prefix))
                    gw = pc.gateway or ""
                    if plan.dhcp_pools:
                        lines.append(f'configurePcIp({json.dumps(pc.name)}, true);')
                    else:
                        lines.append(
                            f'configurePcIp({json.dumps(pc.name)}, false, '
                            f'{json.dumps(ip)}, {json.dumps(mask)}, {json.dumps(gw)});'
                        )

    return "\n".join(lines)


def generate_full_script(plan: TopologyPlan) -> str:
    """
    Generate the complete script: PTBuilder + CLI configuration block
    as comments (for visual reference).
    """
    from .cli_config_generator import generate_all_configs

    parts: list[str] = []
    parts.append(generate_ptbuilder_script(plan))

    configs = generate_all_configs(plan)
    if configs:
        parts.append("/* === CLI configurations per device ===")
        parts.append("Copy and paste into the CLI of each device. */")
        for device_name, cli_block in configs.items():
            parts.append(f"/* --- {device_name} ---")
            for line in cli_block.splitlines():
                parts.append(line)
            parts.append("*/ ")

    return "\n".join(parts)
