"""
Topology plan validator.

Uses the rules from domain/rules/ with typed errors.
"""

from __future__ import annotations
from ..models.plans import TopologyPlan
from ..models.errors import ValidationResult
from ..rules.device_rules import validate_devices, validate_port_capacity
from ..rules.ip_rules import validate_ips, validate_dhcp, validate_subnet_overlap
from ..rules.cable_rules import validate_links


def validate_plan(plan: TopologyPlan) -> ValidationResult:
    """
    Validate a complete plan.
    Returns a ValidationResult with typed errors and warnings.
    Also updates plan.errors and plan.warnings for compatibility.
    """
    result = ValidationResult()

    # Devices
    result.errors.extend(validate_devices(plan))
    result.errors.extend(validate_port_capacity(plan))

    # Links and cables
    link_errors, link_warnings = validate_links(plan)
    result.errors.extend(link_errors)
    result.warnings.extend(link_warnings)

    # IPs
    result.errors.extend(validate_ips(plan))

    # Subnet overlap (different subnets that overlap)
    result.errors.extend(validate_subnet_overlap(plan))

    # DHCP
    dhcp_issues = validate_dhcp(plan)
    # DHCP gateway mismatch is a warning, not a critical error
    for issue in dhcp_issues:
        if issue.code.value == "DHCP_GATEWAY_MISMATCH":
            result.warnings.append(issue)
        else:
            result.errors.append(issue)

    # Sync with plan.errors/warnings for compatibility
    plan.errors = result.error_messages()
    plan.warnings = result.warning_messages()

    return result
