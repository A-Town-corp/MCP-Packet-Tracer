"""Validation rules for IPs."""

from __future__ import annotations
import ipaddress
from ..models.plans import TopologyPlan
from ..models.errors import PlanError, ErrorCode


def validate_ips(plan: TopologyPlan) -> list[PlanError]:
    """Verify that there are no IP conflicts."""
    errors: list[PlanError] = []
    all_ips: dict[str, str] = {}

    for dev in plan.devices:
        for iface, ip_cidr in dev.interfaces.items():
            try:
                ip_obj = ipaddress.IPv4Interface(ip_cidr)
                ip_str = str(ip_obj.ip)
            except ValueError:
                errors.append(PlanError(
                    code=ErrorCode.INVALID_IP_ADDRESS,
                    device=dev.name,
                    message=f"Invalid IP '{ip_cidr}' on interface {iface}.",
                    suggestion="Check the IP format. Example: 192.168.1.1/24",
                ))
                continue

            key = f"{dev.name}:{iface}"
            if ip_str in all_ips:
                errors.append(PlanError(
                    code=ErrorCode.IP_CONFLICT,
                    device=dev.name,
                    message=f"IP {ip_str} duplicated between {all_ips[ip_str]} and {key}.",
                    suggestion="Reassign one of the conflicting IPs.",
                ))
            else:
                all_ips[ip_str] = key

    return errors


def validate_subnet_overlap(plan: TopologyPlan) -> list[PlanError]:
    """Detect subnets that overlap but are not identical.

    Two interfaces in the SAME subnet (e.g. router .1 and PC .2 in 192.168.1.0/24)
    is normal in a LAN and is NOT flagged. What is flagged is the overlap between
    DIFFERENT subnets (e.g. 192.168.1.0/24 and 192.168.1.0/25, or a link /30 that
    falls inside a LAN), which breaks routing.
    """
    errors: list[PlanError] = []
    nets: dict = {}  # network -> "device:iface" (first occurrence)

    def _collect(owner: str, iface: str, ip_cidr: str):
        try:
            net = ipaddress.IPv4Interface(ip_cidr).network
        except ValueError:
            return
        nets.setdefault(net, f"{owner}:{iface}")

    for dev in plan.devices:
        for iface, ip_cidr in dev.interfaces.items():
            _collect(dev.name, iface, ip_cidr)
    # Router-on-a-stick subinterfaces (each VLAN is its own /24)
    for sub in getattr(plan, "subinterfaces", []):
        _collect(sub.router, f"{sub.parent_port}.{sub.vlan_id}", f"{sub.ip}/{_prefix_of(sub.mask)}")

    unique = list(nets.items())
    flagged: set = set()
    for i in range(len(unique)):
        na, la = unique[i]
        for j in range(i + 1, len(unique)):
            nb, lb = unique[j]
            if na != nb and na.overlaps(nb):
                pair = tuple(sorted((str(na), str(nb))))
                if pair in flagged:
                    continue
                flagged.add(pair)
                errors.append(PlanError(
                    code=ErrorCode.SUBNET_OVERLAP,
                    device=la.split(":")[0],
                    message=f"Overlapping subnets: {na} ({la}) and {nb} ({lb}).",
                    suggestion="Reassign one of the subnets to a range that does not overlap.",
                ))
    return errors


def _prefix_of(mask: str) -> int:
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except ValueError:
        return 24


def validate_dhcp(plan: TopologyPlan) -> list[PlanError]:
    """Verify DHCP pools."""
    errors: list[PlanError] = []

    for pool in plan.dhcp_pools:
        router = plan.device_by_name(pool.router)
        if router is None:
            errors.append(PlanError(
                code=ErrorCode.DHCP_ROUTER_NOT_FOUND,
                device=pool.router,
                message=f"DHCP pool '{pool.pool_name}' references a nonexistent router.",
                suggestion="Check the router name.",
            ))
            continue

        gw_found = any(
            str(ipaddress.IPv4Interface(ip).ip) == pool.gateway
            for ip in router.interfaces.values()
            if _is_valid_ip(ip)
        )
        if not gw_found:
            errors.append(PlanError(
                code=ErrorCode.DHCP_GATEWAY_MISMATCH,
                device=pool.router,
                message=f"Gateway {pool.gateway} of pool '{pool.pool_name}' is not assigned to an interface of {pool.router}.",
                suggestion="Assign the gateway to a router interface.",
            ))

    return errors


def _is_valid_ip(ip_cidr: str) -> bool:
    try:
        ipaddress.IPv4Interface(ip_cidr)
        return True
    except ValueError:
        return False
