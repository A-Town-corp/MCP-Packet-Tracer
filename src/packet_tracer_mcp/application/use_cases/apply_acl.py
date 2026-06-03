"""Use case: apply an ACL to a router in the active topology.

Pipeline:
  1. Build ACLPlan + optional ACLBinding from user-friendly args.
  2. Validate statically (ranges, types, IPs/wildcards, unreachable rules).
  3. Verify against the active PT topology (router and interface exist).
  4. Generate IOS CLI and assemble the configureIosDevice payload.
  5. Return a payload ready to send via the bridge (or send it if apply=True).

The actual application is delegated to the caller (MCP tool) to keep this
module free of HTTP bridge dependencies.
"""

from __future__ import annotations
import json
from typing import Callable

from ...domain.models.acls import ACLPlan, ACLEntry, ACLBinding
from ...domain.models.errors import PlanError, ErrorCode, ValidationResult
from ...domain.rules.acl_rules import validate_acl_plan, validate_acl_binding
from ...infrastructure.generator.acl_cli_generator import (
    build_configure_payload,
    build_remove_payload,
    generate_acl_cli,
    generate_acl_binding_cli,
)


def build_acl_plan(
    router: str,
    name_or_number: str,
    acl_type: str,
    entries_dicts: list[dict],
) -> ACLPlan:
    """Build an ACLPlan from dicts (typically from the LLM)."""
    entries = [ACLEntry(**e) for e in entries_dicts]
    return ACLPlan(
        router=router,
        name_or_number=str(name_or_number),
        acl_type=acl_type,
        entries=entries,
    )


def validate_against_topology(
    plan: ACLPlan,
    binding: ACLBinding | None,
    devices_in_pt: list[dict],
) -> ValidationResult:
    """Validate that the router (and its interface if there is a binding) exist in PT.

    `devices_in_pt` is the raw bridge output (queryTopology()):
    each dict has at least {name, type, model}. It does not include explicit
    interfaces, so interface verification is heuristic:
    if the router model is in the catalog, we validate against its
    known ports.
    """
    errors: list[PlanError] = []
    warnings: list[PlanError] = []

    device = next((d for d in devices_in_pt if d.get("name") == plan.router), None)
    if device is None:
        errors.append(PlanError(
            code=ErrorCode.ACL_ROUTER_NOT_FOUND,
            device=plan.router,
            message=f"Router '{plan.router}' does not exist in the active PT topology.",
            suggestion="Call pt_query_topology to see available devices.",
        ))
        return ValidationResult(errors=errors, warnings=warnings)

    if binding is not None:
        # Verify interface against the catalog (best-effort).
        from ...infrastructure.catalog.devices import resolve_model
        from ...shared.utils import is_port_or_subinterface
        model = resolve_model(device.get("model", ""))
        if model is not None:
            valid_ports = {p.full_name for p in model.ports}
            # Accept dot1Q subinterfaces (Gi0/0.10) for router-on-a-stick.
            if not is_port_or_subinterface(binding.interface, valid_ports):
                errors.append(PlanError(
                    code=ErrorCode.ACL_INTERFACE_NOT_FOUND,
                    device=plan.router,
                    message=f"Interface '{binding.interface}' does not exist on {device.get('model')}.",
                    suggestion=f"Available ports: {', '.join(sorted(valid_ports))} (or a subinterface such as Gi0/0.10)",
                ))

    return ValidationResult(errors=errors, warnings=warnings)


def apply_acl_uc(
    plan: ACLPlan,
    binding: ACLBinding | None = None,
    query_pt_topology: Callable[[], list[dict]] | None = None,
    bridge_send: Callable[[str], bool] | None = None,
    confirm_send: Callable[[str], str | None] | None = None,
    dry_run: bool = False,
) -> dict:
    """Complete pipeline: validate + (optionally) apply.

    Args:
        plan: already-built ACLPlan.
        binding: optional, applies the ACL to an interface.
        query_pt_topology: callable that returns devices_in_pt (list of dicts).
            If None, the PT verification is skipped (static validation only).
        bridge_send: callable that receives the full JS payload and sends it to PT.
            If None or dry_run=True, nothing is sent.
        dry_run: if True, returns the payload but does not send it.

    Returns:
        dict with keys: valid, errors, warnings, cli_lines, js_payload, sent.
    """
    # 1. Static validation of the plan
    plan_result = validate_acl_plan(plan)
    errors = list(plan_result.errors)
    warnings = list(plan_result.warnings)

    # 2. Binding validation (if applicable)
    if binding is not None:
        binding_result = validate_acl_binding(binding, plan)
        errors.extend(binding_result.errors)
        warnings.extend(binding_result.warnings)

    # 3. Dynamic validation against PT
    if query_pt_topology is not None:
        try:
            devices_in_pt = query_pt_topology()
            topo_result = validate_against_topology(plan, binding, devices_in_pt)
            errors.extend(topo_result.errors)
            warnings.extend(topo_result.warnings)
        except Exception as exc:
            warnings.append(PlanError(
                code=ErrorCode.VALIDATION_ERROR,
                device=plan.router,
                message=f"Could not query the active topology: {exc}. Static validation applied.",
            ))

    # 4. Always generate CLI (useful for inspection even if there are errors)
    cli_lines = generate_acl_cli(plan)
    if binding is not None:
        cli_lines.extend(generate_acl_binding_cli(binding))

    full_payload = build_configure_payload(plan, binding)
    js_call = _build_js_call(plan.router, full_payload)

    sent = False
    applied: bool | None = None
    if not errors and not dry_run:
        if confirm_send is not None:
            # Confirming path: PT reports whether configureIosDevice succeeded.
            res = confirm_send(_build_js_call_confirm(plan.router, full_payload))
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


def remove_acl_uc(
    router: str,
    name_or_number: str,
    binding_interface: str = "",
    direction: str = "in",
    acl_type: str = "extended",
    bridge_send: Callable[[str], bool] | None = None,
    confirm_send: Callable[[str], str | None] | None = None,
    dry_run: bool = False,
) -> dict:
    """Build and send commands to remove an applied ACL."""
    payload = build_remove_payload(router, str(name_or_number), binding_interface, direction, acl_type)
    js_call = _build_js_call(router, payload)

    sent = False
    applied: bool | None = None
    if not dry_run:
        if confirm_send is not None:
            res = confirm_send(_build_js_call_confirm(router, payload))
            sent = res is not None
            applied = _parse_ok(res)
        elif bridge_send is not None:
            sent = bool(bridge_send(js_call))

    return {
        "router": router,
        "acl_id": str(name_or_number),
        "js_payload": js_call,
        "sent": sent,
        "applied": applied,
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


def _build_js_call_confirm(router: str, ios_payload: str) -> str:
    """Like _build_js_call but PT reports whether configureIosDevice succeeded.

    Lets the MCP layer confirm the actual application (not just the enqueue)
    via reportResult, instead of blindly claiming "Applied".
    """
    safe_router = router.replace("\\", "\\\\").replace('"', '\\"')
    safe_payload = (
        ios_payload
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
    return (
        f'var __ok = configureIosDevice("{safe_router}", "{safe_payload}"); '
        f'reportResult(JSON.stringify({{ok: __ok === true}}));'
    )


def _build_js_call(router: str, ios_payload: str) -> str:
    """Wrap the IOS payload in a configureIosDevice call as a single JS line.

    Important: the full string must be on a single line of JS code (without
    real line breaks in the code), but the \\n INSIDE the string do travel
    because they are string-literal escapes -- they are not source-code line
    breaks that executeCode() would strip.
    """
    safe_router = router.replace("\\", "\\\\").replace('"', '\\"')
    safe_payload = (
        ios_payload
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
    return f'configureIosDevice("{safe_router}", "{safe_payload}");'
