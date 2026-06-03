"""Validation rules for NAT/PAT.

The static validations do not query PT. The dynamic verification (router
and interfaces exist in the active topology) is done from the use case,
just like for ACLs.
"""

from __future__ import annotations
import ipaddress

from ..models.nat import NATConfig, NATPool, NATStaticMapping
from ..models.errors import PlanError, ErrorCode, ValidationResult


def validate_nat_config(config: NATConfig) -> ValidationResult:
    """Validate a NATConfig statically."""
    errors: list[PlanError] = []
    warnings: list[PlanError] = []

    _validate_interfaces(config, errors)

    if config.mode == "static":
        _validate_static(config, errors)
    elif config.mode == "dynamic":
        _validate_dynamic(config, errors)
    elif config.mode == "pat":
        _validate_pat(config, errors)

    return ValidationResult(errors=errors, warnings=warnings)


def validate_nat_against_topology(
    config: NATConfig,
    devices_in_pt: list[dict],
) -> ValidationResult:
    """Validate that the router and its interfaces exist in PT's active topology."""
    errors: list[PlanError] = []
    warnings: list[PlanError] = []

    device = next((d for d in devices_in_pt if d.get("name") == config.router), None)
    if device is None:
        errors.append(PlanError(
            code=ErrorCode.NAT_ROUTER_NOT_FOUND,
            device=config.router,
            message=f"Router '{config.router}' does not exist in PT's active topology.",
            suggestion="Call pt_query_topology to see the available devices.",
        ))
        return ValidationResult(errors=errors, warnings=warnings)

    from ...infrastructure.catalog.devices import resolve_model
    from ...shared.utils import is_port_or_subinterface
    model = resolve_model(device.get("model", ""))
    if model is not None:
        valid_ports = {p.full_name for p in model.ports}
        for iface_label, iface in [
            ("inside_interface", config.inside_interface),
            ("outside_interface", config.outside_interface),
        ]:
            # Accept dot1Q subinterfaces (Gi0/0.10) for router-on-a-stick.
            if not is_port_or_subinterface(iface, valid_ports):
                errors.append(PlanError(
                    code=ErrorCode.NAT_INTERFACE_NOT_FOUND,
                    device=config.router,
                    message=f"{iface_label} '{iface}' does not exist on {device.get('model')}.",
                    suggestion=f"Available ports: {', '.join(sorted(valid_ports))} (or a subinterface like Gi0/0.10)",
                ))

    return ValidationResult(errors=errors, warnings=warnings)


# ----------------------------------------------------------------------
# Private helpers
# ----------------------------------------------------------------------

def _validate_interfaces(config: NATConfig, errors: list[PlanError]) -> None:
    if config.inside_interface == config.outside_interface:
        errors.append(PlanError(
            code=ErrorCode.NAT_SAME_INTERFACE,
            device=config.router,
            message="inside_interface and outside_interface cannot be the same interface.",
            suggestion="The 'inside' interface connects to the LAN and the 'outside' to the WAN/Internet.",
        ))


def _validate_static(config: NATConfig, errors: list[PlanError]) -> None:
    if not config.static_mappings:
        errors.append(PlanError(
            code=ErrorCode.NAT_MISSING_STATIC_MAPPINGS,
            device=config.router,
            message="Static NAT requires at least one static mapping (inside_local <-> inside_global).",
            suggestion="Add a dict {'inside_local': 'private_IP', 'inside_global': 'public_IP'}.",
        ))
        return

    for i, m in enumerate(config.static_mappings):
        label = f"static_mappings[{i}]"
        _require_ipv4(m.inside_local, f"{label}.inside_local", config.router, errors)
        _require_ipv4(m.inside_global, f"{label}.inside_global", config.router, errors)


def _validate_dynamic(config: NATConfig, errors: list[PlanError]) -> None:
    if not config.inside_networks:
        errors.append(PlanError(
            code=ErrorCode.NAT_MISSING_INSIDE_NETWORKS,
            device=config.router,
            message="Dynamic NAT requires inside_networks to generate the access-list.",
            suggestion="E.g.: ['192.168.1.0 0.0.0.255']. Or specify acl_number of an existing ACL.",
        ))
    else:
        _validate_inside_networks(config, errors)

    if config.pool is None:
        errors.append(PlanError(
            code=ErrorCode.NAT_MISSING_POOL,
            device=config.router,
            message="Dynamic NAT requires a pool of public IPs.",
            suggestion="Specify pool_name, pool_start, pool_end and pool_netmask.",
        ))
    else:
        _validate_pool(config.pool, config.router, errors)


def _validate_pat(config: NATConfig, errors: list[PlanError]) -> None:
    if not config.inside_networks:
        errors.append(PlanError(
            code=ErrorCode.NAT_MISSING_INSIDE_NETWORKS,
            device=config.router,
            message="PAT requires inside_networks to identify the hosts being translated.",
            suggestion="E.g.: ['192.168.1.0 0.0.0.255']. Include all internal subnets.",
        ))
    else:
        _validate_inside_networks(config, errors)

    if not config.use_interface_overload and config.pool is None:
        errors.append(PlanError(
            code=ErrorCode.NAT_MISSING_POOL,
            device=config.router,
            message="PAT with use_interface_overload=False requires a pool.",
            suggestion="Specify pool_name/start/end/netmask, or use use_interface_overload=True "
                       "if the public IP is directly on outside_interface.",
        ))
    elif not config.use_interface_overload and config.pool is not None:
        _validate_pool(config.pool, config.router, errors)


def _validate_inside_networks(config: NATConfig, errors: list[PlanError]) -> None:
    for i, net in enumerate(config.inside_networks):
        label = f"inside_networks[{i}]"
        net = net.strip()
        if net == "any":
            continue
        parts = net.split()
        if len(parts) == 2 and parts[0] == "host":
            _require_ipv4(parts[1], f"{label} (host)", config.router, errors)
            continue
        if len(parts) == 2:
            try:
                ipaddress.IPv4Address(parts[0])
                ipaddress.IPv4Address(parts[1])
            except ValueError:
                errors.append(PlanError(
                    code=ErrorCode.NAT_INVALID_IP,
                    device=config.router,
                    message=f"{label}: '{net}' is not a valid 'network wildcard' pair.",
                    suggestion="Format: 'A.B.C.D W.W.W.W' (e.g.: '192.168.1.0 0.0.0.255').",
                ))
            continue
        errors.append(PlanError(
            code=ErrorCode.NAT_INVALID_IP,
            device=config.router,
            message=f"{label}: invalid format '{net}'.",
            suggestion="Use 'any', 'host A.B.C.D' or 'A.B.C.D wildcard'.",
        ))


def _validate_pool(pool: NATPool, router: str, errors: list[PlanError]) -> None:
    _require_ipv4(pool.start_ip, "pool.start_ip", router, errors)
    _require_ipv4(pool.end_ip, "pool.end_ip", router, errors)
    try:
        ipaddress.IPv4Address(pool.netmask)
        # Verify it is a valid mask (not a wildcard)
        packed = int(ipaddress.IPv4Address(pool.netmask))
        # A valid network mask has all 1s followed by all 0s
        if packed != 0:
            inverted = packed ^ 0xFFFFFFFF
            if (inverted & (inverted + 1)) != 0:
                errors.append(PlanError(
                    code=ErrorCode.NAT_INVALID_NETMASK,
                    device=router,
                    message=f"pool.netmask '{pool.netmask}' is not a valid subnet mask.",
                    suggestion="Use mask format (e.g.: '255.255.255.0'), NOT a wildcard.",
                ))
    except ValueError:
        errors.append(PlanError(
            code=ErrorCode.NAT_INVALID_NETMASK,
            device=router,
            message=f"pool.netmask '{pool.netmask}' is not a valid IPv4 address.",
        ))

    # Verify that start <= end (only if both are valid IPv4)
    try:
        start = int(ipaddress.IPv4Address(pool.start_ip))
        end = int(ipaddress.IPv4Address(pool.end_ip))
        if start > end:
            errors.append(PlanError(
                code=ErrorCode.NAT_POOL_RANGE_INVALID,
                device=router,
                message=f"pool.start_ip '{pool.start_ip}' is greater than pool.end_ip '{pool.end_ip}'.",
            ))
    except ValueError:
        pass  # already reported above


def _require_ipv4(value: str, label: str, router: str, errors: list[PlanError]) -> None:
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        errors.append(PlanError(
            code=ErrorCode.NAT_INVALID_IP,
            device=router,
            message=f"{label}: '{value}' is not a valid IPv4 address.",
        ))
