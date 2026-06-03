"""Use case: apply NAT/PAT to a router in the active topology.

Pipeline (identical to the ACL one):
  1. Build NATConfig from user-friendly args.
  2. Validate statically (IPs, interfaces, pool, inside networks).
  3. Verify against the active PT topology (router and interfaces exist).
  4. Generate IOS CLI and assemble the configureIosDevice payload.
  5. Send via the bridge or return a dry-run payload.
"""

from __future__ import annotations
import json
from typing import Callable

from ...domain.models.nat import NATConfig, NATPool, NATStaticMapping
from ...domain.models.errors import PlanError, ErrorCode, ValidationResult
from ...domain.rules.nat_rules import validate_nat_config, validate_nat_against_topology
from ...infrastructure.generator.nat_cli_generator import (
    build_nat_configure_payload,
    build_nat_remove_payload,
    build_nat_js_call,
    build_nat_js_call_confirm,
    generate_nat_interface_cli,
    generate_nat_body_cli,
)


def build_nat_config(
    router: str,
    mode: str,
    inside_interface: str,
    outside_interface: str,
    static_mappings: list[dict] | None = None,
    inside_networks: list[str] | None = None,
    acl_number: str = "1",
    pool_name: str = "NAT-POOL",
    pool_start: str = "",
    pool_end: str = "",
    pool_netmask: str = "",
    use_interface_overload: bool = False,
) -> NATConfig:
    """Build a NATConfig from flat parameters (typically from the LLM)."""
    mappings = [NATStaticMapping(**m) for m in (static_mappings or [])]

    pool: NATPool | None = None
    if pool_start and pool_end and pool_netmask:
        pool = NATPool(
            name=pool_name,
            start_ip=pool_start,
            end_ip=pool_end,
            netmask=pool_netmask,
        )

    return NATConfig(
        router=router,
        mode=mode,  # type: ignore[arg-type]
        inside_interface=inside_interface,
        outside_interface=outside_interface,
        static_mappings=mappings,
        inside_networks=inside_networks or [],
        acl_number=acl_number,
        pool=pool,
        use_interface_overload=use_interface_overload,
    )


def apply_nat_uc(
    config: NATConfig,
    query_pt_topology: Callable[[], list[dict]] | None = None,
    bridge_send: Callable[[str], bool] | None = None,
    confirm_send: Callable[[str], str | None] | None = None,
    dry_run: bool = False,
) -> dict:
    """Complete pipeline: validate + (optionally) apply NAT.

    Args:
        config: already-built NATConfig.
        query_pt_topology: callable -> list of devices in PT. If None, skips
            dynamic verification.
        bridge_send: callable that receives the JS payload and sends it. If None
            or dry_run=True, nothing is sent.
        dry_run: if True, returns the payload without sending it.

    Returns:
        dict with keys: valid, errors, warnings, cli_lines, js_payload, sent, dry_run.
    """
    # 1. Static validation
    result = validate_nat_config(config)
    errors = list(result.errors)
    warnings = list(result.warnings)

    # 2. Dynamic validation against PT
    if query_pt_topology is not None:
        try:
            devices_in_pt = query_pt_topology()
            topo_result = validate_nat_against_topology(config, devices_in_pt)
            errors.extend(topo_result.errors)
            warnings.extend(topo_result.warnings)
        except Exception as exc:
            warnings.append(PlanError(
                code=ErrorCode.VALIDATION_ERROR,
                device=config.router,
                message=f"Could not query the active topology: {exc}. Static validation applied.",
            ))

    # 3. Always generate CLI (useful for inspection even if there are errors)
    cli_lines = generate_nat_interface_cli(config)
    cli_lines.extend(generate_nat_body_cli(config))

    full_payload = build_nat_configure_payload(config)
    js_call = build_nat_js_call(config.router, full_payload)

    sent = False
    applied: bool | None = None
    if not errors and not dry_run:
        if confirm_send is not None:
            res = confirm_send(build_nat_js_call_confirm(config.router, full_payload))
            sent = res is not None
            applied = _parse_ok(res)
        elif bridge_send is not None:
            sent = bool(bridge_send(js_call))

    return {
        "valid": len(errors) == 0,
        "errors": [e.to_dict() for e in errors],
        "warnings": [w.to_dict() for w in warnings],
        "cli_lines": cli_lines,
        "js_payload": js_call,
        "sent": sent,
        "applied": applied,
        "dry_run": dry_run,
    }


def remove_nat_uc(
    router: str,
    mode: str,
    inside_interface: str,
    outside_interface: str,
    acl_number: str = "1",
    pool_name: str = "",
    static_mappings: list[dict] | None = None,
    bridge_send: Callable[[str], bool] | None = None,
    confirm_send: Callable[[str], str | None] | None = None,
    dry_run: bool = False,
) -> dict:
    """Build and send commands to remove NAT/PAT from a router."""
    payload = build_nat_remove_payload(
        router=router,
        mode=mode,
        inside_interface=inside_interface,
        outside_interface=outside_interface,
        acl_number=acl_number,
        pool_name=pool_name,
        static_mappings=static_mappings,
    )
    js_call = build_nat_js_call(router, payload)

    warnings: list[str] = []
    if mode == "static" and not static_mappings:
        warnings.append(
            "Static NAT removal without 'static_mappings' only clears the "
            "interface ip nat inside/outside marks -- the existing "
            "'ip nat inside source static' translations remain. Re-supply the "
            "static_mappings to remove them, or clear them on the device."
        )

    sent = False
    applied: bool | None = None
    if not dry_run:
        if confirm_send is not None:
            res = confirm_send(build_nat_js_call_confirm(router, payload))
            sent = res is not None
            applied = _parse_ok(res)
        elif bridge_send is not None:
            sent = bool(bridge_send(js_call))

    return {
        "router": router,
        "mode": mode,
        "js_payload": js_call,
        "sent": sent,
        "applied": applied,
        "warnings": warnings,
        "dry_run": dry_run,
    }


def _parse_ok(res: str | None) -> bool | None:
    """Interpret the bridge's JSON response {ok: bool}. None if there was no response."""
    if res is None:
        return None
    try:
        return bool(json.loads(res).get("ok"))
    except Exception:
        return None
