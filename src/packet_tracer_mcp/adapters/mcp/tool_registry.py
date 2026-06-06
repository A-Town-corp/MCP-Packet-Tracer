"""
MCP Tools registry.

Defines all the tools the LLM can invoke.
"""

from __future__ import annotations
import html
import json
import re
import time
import urllib.request
from mcp.server.fastmcp import FastMCP

from ...domain.models.plans import TopologyPlan
from ...domain.models.requests import TopologyRequest
from ...domain.models.acls import ACLPlan, ACLBinding, ACLEntry
from ...domain.services.orchestrator import plan_from_request
from ...domain.services.validator import validate_plan
from ...domain.services.auto_fixer import fix_plan
from ...domain.services.explainer import explain_plan
from ...domain.services.estimator import estimate_from_request, estimate_from_plan
from ...application.use_cases.apply_acl import (
    build_acl_plan,
    apply_acl_uc,
    remove_acl_uc,
)
from ...application.use_cases.apply_nat import (
    build_nat_config,
    apply_nat_uc,
    remove_nat_uc,
)
from ...application.use_cases.apply_features import (
    apply_svi_uc,
    configure_etherchannel_uc,
    apply_port_security_uc,
    apply_hsrp_uc,
    add_static_routes_uc,
    apply_dhcp_relay_uc,
    apply_ipv6_uc,
    apply_raw_ios_uc,
    apply_ospf_uc,
    apply_rip_uc,
    apply_eigrp_uc,
    apply_bgp_uc,
    apply_device_security_uc,
    apply_management_uc,
    apply_stp_uc,
    apply_vtp_uc,
    create_vlans_uc,
    configure_interface_uc,
    apply_loopback_uc,
    configure_serial_uc,
    apply_gre_tunnel_uc,
)
from ...application.use_cases._bridge_apply import parse_ok
from ...infrastructure.generator.ptbuilder_generator import (
    generate_ptbuilder_script,
    generate_full_script,
    generate_executable_script,
)
from ...infrastructure.generator.cli_config_generator import (
    generate_all_configs,
    generate_pc_config,
)
from ...infrastructure.execution.manual_executor import ManualExecutor
from ...infrastructure.execution.deploy_executor import DeployExecutor
from ...infrastructure.execution.live_bridge import PTCommandBridge
from ...infrastructure.persistence.project_repository import ProjectRepository
from ...infrastructure.catalog.devices import ALL_MODELS, resolve_model
from ...infrastructure.catalog.cables import CABLE_TYPES
from ...infrastructure.catalog.aliases import MODEL_ALIASES
from ...infrastructure.catalog.templates import list_templates
from ...infrastructure.catalog.modules import ALL_MODULES, resolve_module
from ...shared.enums import RoutingProtocol, TopologyTemplate
from ...shared.constants import DEFAULT_LAN_BASE, DEFAULT_LINK_BASE, CAPABILITIES
from pydantic import ValidationError


def _load_plan_or_error(plan_json: str) -> tuple[TopologyPlan | None, str | None]:
    """Parse plan JSON into a TopologyPlan.

    Returns (plan, None) on success, or (None, error_json) when the JSON is
    malformed or doesn't match the schema - so tools return a structured error
    instead of crashing the MCP layer with an uncaught ValidationError.
    """
    try:
        plan = TopologyPlan.model_validate_json(plan_json)
        if not plan.devices:
            # A structurally-valid but empty plan would silently no-op the whole
            # deploy/generate path and report success; reject it explicitly.
            return None, json.dumps({
                "valid": False, "error_count": 1, "warning_count": 0,
                "errors": [{"code": "EMPTY_PLAN", "message": "The plan has no devices."}],
                "warnings": [],
                "summary": "The plan is empty (no devices). Build one with pt_plan_topology first.",
            }, indent=2, ensure_ascii=False)
        return plan, None
    except ValidationError as exc:
        errs = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e.get("loc", ()))
            errs.append({"code": "INVALID_PLAN_SCHEMA", "message": f"{loc}: {e.get('msg')}"})
        return None, json.dumps({
            "valid": False, "error_count": len(errs) or 1, "warning_count": 0,
            "errors": errs or [{"code": "INVALID_PLAN_SCHEMA", "message": str(exc)}],
            "warnings": [],
            "summary": "The JSON does not match the TopologyPlan schema. Regenerate the plan with pt_plan_topology.",
        }, indent=2, ensure_ascii=False)
    except (ValueError, json.JSONDecodeError) as exc:
        return None, json.dumps({
            "valid": False, "error_count": 1, "warning_count": 0,
            "errors": [{"code": "INVALID_JSON", "message": f"Invalid JSON: {exc}"}],
            "warnings": [],
            "summary": "Invalid JSON - the plan could not be parsed.",
        }, indent=2, ensure_ascii=False)


def _apply_summary(kind: str, ident: str, router: str, result: dict, dry_run: bool, bridge_ok: bool) -> list[str]:
    """Status line(s) for apply/remove of ACL/NAT, based on real confirmation.

    Distinguishes: confirmed by PT (applied=True), rejected (applied=False),
    sent without confirmation (timeout), bridge disconnected, or dry_run.
    """
    valid = result.get("valid", True)
    applied = result.get("applied")
    sent = result.get("sent")
    if dry_run:
        return ["dry_run mode - NOT sent to the bridge."]
    if not valid:
        return ["Not sent: fix the plan errors first."]
    if applied is True:
        return [f"{kind} '{ident}' confirmed by PT on '{router}' (configureIosDevice OK)."]
    if applied is False:
        return [f"PT rejected {kind} '{ident}' on '{router}' (configureIosDevice returned false - check the router/interface name)."]
    if sent and applied is None:
        return [f"{kind} '{ident}' sent to '{router}' but PT did not confirm (timeout). Verify with pt_query_topology."]
    if not bridge_ok:
        return ["Bridge not connected - payload generated but NOT sent."]
    return ["Bridge OK but the send was not confirmed."]


def register_tools(mcp: FastMCP) -> None:
    """Register all tools on the MCP server."""

    # ------------------------------------------------------------------
    # QUERY
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_list_devices() -> str:
        """
        List all devices available in Packet Tracer with their ports.
        Use this to know which models, ports and cables you can use.
        """
        lines = []
        for name, model in ALL_MODELS.items():
            ports = ", ".join(p.full_name for p in model.ports)
            lines.append(f"**{model.display_name}** (type: `{name}`, category: {model.category})")
            lines.append(f"  Ports: {ports}")
            lines.append("")
        lines.append("**Available aliases:**")
        for alias, target in MODEL_ALIASES.items():
            lines.append(f"  {alias} -> {target}")
        return "\n".join(lines)

    @mcp.tool()
    def pt_list_templates() -> str:
        """
        List all available topology templates with their descriptions.
        """
        templates = list_templates()
        lines = []
        for t in templates:
            lines.append(f"**{t.name}** (key: `{t.key.value}`)")
            lines.append(f"  {t.description}")
            lines.append(f"  Routers: {t.min_routers}-{t.max_routers} (default: {t.default_routers})")
            lines.append(f"  PCs/LAN: {t.default_pcs_per_lan}  |  WAN: {'yes' if t.requires_wan else 'no'}")
            lines.append(f"  Routing: {t.default_routing.value}")
            lines.append(f"  Tags: {', '.join(t.tags)}")
            lines.append("")
        return "\n".join(lines)

    @mcp.tool()
    def pt_get_device_details(model_name: str) -> str:
        """
        Show details of a specific device model.

        Accepts both the exact model name (e.g. '2911', '2960-24TT')
        and a catalog alias (e.g. 'router', 'switch', 'firewall').

        Parameters:
        - model_name: model name or alias
        """
        model = resolve_model(model_name)
        if not model:
            return f"Model '{model_name}' not found. Use pt_list_devices to see models."
        info = {
            "display_name": model.display_name,
            "category": model.category,
            "ports": [
                {"name": p.full_name, "speed": p.speed.value if p.speed else "N/A"}
                for p in model.ports
            ],
            "total_ports": len(model.ports),
        }
        return json.dumps(info, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # ESTIMATION (dry-run)
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_estimate_plan(
        routers: int = 2,
        pcs_per_lan: int = 3,
        laptops_per_lan: int = 0,
        switches_per_router: int = 1,
        servers: int = 0,
        access_points: int = 0,
        has_wan: bool = False,
        dhcp: bool = True,
        routing: str = "static",
        floating_routes: bool = False,
    ) -> str:
        """
        Quick dry-run estimate without generating the full plan.
        Shows how many devices, links and subnets will be created.

        Parameters:
        - routers: number of routers (1-20)
        - pcs_per_lan: PCs per LAN
        - laptops_per_lan: laptops per LAN (Laptop-PT)
        - switches_per_router: switches per router
        - servers: servers
        - access_points: Access Points (AccessPoint-PT)
        - has_wan: include WAN
        - dhcp: configure DHCP
        - routing: static, ospf, eigrp, rip, none
        - floating_routes: backup static routes (AD=254) - must match
          pt_plan_topology so the estimate reflects the real build
        """
        try:
            request = TopologyRequest(
                routers=routers,
                pcs_per_lan=pcs_per_lan,
                laptops_per_lan=laptops_per_lan,
                switches_per_router=switches_per_router,
                servers=servers,
                access_points=access_points,
                has_wan=has_wan,
                dhcp=dhcp,
                routing=RoutingProtocol(routing),
                floating_routes=floating_routes,
            )
            est = estimate_from_request(request)
        except (ValueError, ValidationError, KeyError, TypeError) as exc:
            return json.dumps(
                {"error": f"Invalid estimate request: {exc}"}, indent=2, ensure_ascii=False)
        return json.dumps(est, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # PLANNING
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_plan_topology(
        routers: int = 2,
        pcs_per_lan: int = 3,
        laptops_per_lan: int = 0,
        switches_per_router: int = 1,
        servers: int = 0,
        access_points: int = 0,
        has_wan: bool = False,
        dhcp: bool = True,
        routing: str = "static",
        router_model: str = "2911",
        switch_model: str = "2960-24TT",
        template: str = "multi_lan",
        floating_routes: bool = False,
        ospf_process_id: int = 1,
        eigrp_as: int = 100,
        vlans: int = 0,
    ) -> str:
        """
        Generate a complete network topology plan for Packet Tracer.

        Parameters:
        - routers: Number of routers (1-20)
        - pcs_per_lan: PCs per LAN
        - laptops_per_lan: Laptops per LAN (Laptop-PT)
        - switches_per_router: Switches per router (0-4)
        - servers: Number of servers
        - access_points: Number of Access Points (AccessPoint-PT), one per LAN
        - has_wan: Include WAN connection (Cloud)
        - dhcp: Configure DHCP automatically
        - routing: Routing protocol (static, ospf, eigrp, rip, none)
        - router_model: Router model (1941, 2901, 2911, ISR4321)
        - switch_model: Switch model (2960-24TT, 3560-24PS)
        - template: Template (single_lan, multi_lan, multi_lan_wan, star, hub_spoke,
          branch_office, router_on_a_stick, three_router_triangle, custom)
        - floating_routes: If True with routing=static, adds backup routes with AD=254
          over alternate paths (requires a topology with multiple paths)
        - ospf_process_id: OSPF process ID (1-65535, default 1)
        - eigrp_as: AS number for EIGRP (1-65535, default 100)

        Returns the complete plan JSON.
        """
        try:
            request = TopologyRequest(
                template=TopologyTemplate(template),
                routers=routers,
                pcs_per_lan=pcs_per_lan,
                laptops_per_lan=laptops_per_lan,
                switches_per_router=switches_per_router,
                servers=servers,
                access_points=access_points,
                has_wan=has_wan,
                dhcp=dhcp,
                routing=RoutingProtocol(routing),
                router_model=router_model,
                switch_model=switch_model,
                floating_routes=floating_routes,
                ospf_process_id=ospf_process_id,
                eigrp_as=eigrp_as,
                vlans=vlans,
            )
            plan, validation = plan_from_request(request)
            return plan.model_dump_json(indent=2)
        except (ValueError, ValidationError, KeyError, TypeError) as exc:
            return json.dumps(
                {"error": f"Invalid topology request: {exc}",
                 "hint": "Check template/routing values and numeric ranges."},
                indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_validate_plan(plan_json: str) -> str:
        """
        Validate a topology plan. Returns typed errors and warnings.

        Parameters:
        - plan_json: plan JSON (output of pt_plan_topology)
        """
        try:
            raw = json.loads(plan_json)
        except json.JSONDecodeError as exc:
            return json.dumps({
                "valid": False,
                "error_count": 1,
                "warning_count": 0,
                "errors": [{"code": "INVALID_JSON", "message": f"Invalid JSON: {exc.msg}"}],
                "warnings": [],
                "summary": "Invalid JSON - the plan could not be parsed.",
            }, indent=2, ensure_ascii=False)

        if not isinstance(raw, dict) or "devices" not in raw or not raw.get("devices"):
            return json.dumps({
                "valid": False,
                "error_count": 1,
                "warning_count": 0,
                "errors": [{
                    "code": "EMPTY_PLAN",
                    "message": "The JSON does not contain a valid plan (missing 'devices' or empty). Generate the plan with pt_plan_topology first.",
                }],
                "warnings": [],
                "summary": "Empty or unstructured plan - it must include at least one device.",
            }, indent=2, ensure_ascii=False)

        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr
        result = validate_plan(plan)

        output = result.to_dict()
        if result.is_valid:
            output["summary"] = "Valid plan. No errors."
        else:
            output["summary"] = f"Plan with {len(result.errors)} error(s)."
        return json.dumps(output, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # AUTO-FIX
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_fix_plan(plan_json: str) -> str:
        """
        Try to fix plan errors automatically.
        Fixes cables, upgrades routers if ports are missing, reassigns ports.

        Parameters:
        - plan_json: JSON of the plan to fix
        """
        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr
        fixed_plan, fixes = fix_plan(plan)

        return json.dumps({
            "fixes_applied": fixes,
            "fixes_count": len(fixes),
            "is_valid": fixed_plan.is_valid,
            "plan": json.loads(fixed_plan.model_dump_json()),
        }, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # EXPLANATION
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_explain_plan(plan_json: str) -> str:
        """
        Explain the plan decisions in natural language.
        Useful to understand why certain models, IPs, etc. were chosen.

        Parameters:
        - plan_json: plan JSON
        """
        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr
        explanations = explain_plan(plan)
        return "\n".join(f"- {e}" for e in explanations)

    # ------------------------------------------------------------------
    # GENERATION
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_generate_script(plan_json: str, include_configs: bool = True) -> str:
        """
        Generate the PTBuilder JavaScript script.

        Parameters:
        - plan_json: plan JSON
        - include_configs: if True, includes CLI configs as comments
        """
        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr
        if include_configs:
            return generate_full_script(plan)
        return generate_ptbuilder_script(plan)

    @mcp.tool()
    def pt_generate_configs(plan_json: str) -> str:
        """
        Generate the CLI (IOS) configurations for all routers and switches.

        Parameters:
        - plan_json: plan JSON
        """
        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr
        configs = generate_all_configs(plan)

        result_parts = []
        for device_name, cli_block in configs.items():
            result_parts.append(f"=== {device_name} ===")
            result_parts.append(cli_block)
            result_parts.append("")

        pcs = [d for d in plan.devices if d.category in ("pc", "server", "laptop")]
        if pcs:
            result_parts.append("=== Host configuration ===")
            use_dhcp = bool(plan.dhcp_pools)
            for pc in pcs:
                result_parts.append(generate_pc_config(pc, use_dhcp=use_dhcp))
                result_parts.append("")

        return "\n".join(result_parts)

    # ------------------------------------------------------------------
    # FULL BUILD
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_full_build(
        routers: int = 2,
        pcs_per_lan: int = 3,
        laptops_per_lan: int = 0,
        switches_per_router: int = 1,
        servers: int = 0,
        access_points: int = 0,
        has_wan: bool = False,
        dhcp: bool = True,
        routing: str = "static",
        router_model: str = "2911",
        switch_model: str = "2960-24TT",
        template: str = "multi_lan",
        deploy: bool = True,
        floating_routes: bool = False,
        ospf_process_id: int = 1,
        eigrp_as: int = 100,
        vlans: int = 0,
    ) -> str:
        """
        Full pipeline: plan, validate, generate, explain, estimate and deploy.

        If deploy=True (default), copies the script to the Windows clipboard
        and generates step-by-step instructions for Packet Tracer.

        Parameters:
        - routers: Number of routers (1-20)
        - pcs_per_lan: PCs per LAN
        - laptops_per_lan: Laptops per LAN (Laptop-PT)
        - switches_per_router: Switches per router
        - servers: Servers
        - access_points: Access Points (AccessPoint-PT), one per LAN
        - has_wan: Include WAN
        - dhcp: Configure DHCP
        - routing: static, ospf, eigrp, rip, none
        - router_model: 1941, 2901, 2911, ISR4321
        - switch_model: 2960-24TT, 3560-24PS
        - template: single_lan, multi_lan, multi_lan_wan, star, hub_spoke,
          branch_office, router_on_a_stick, three_router_triangle, custom
        - deploy: If True, copies the script to the clipboard and exports files
        - floating_routes: If True with routing=static, adds backup routes with AD=254
        - ospf_process_id: OSPF process ID (1-65535, default 1)
        - eigrp_as: AS number for EIGRP (1-65535, default 100)
        """
        try:
            request = TopologyRequest(
                template=TopologyTemplate(template),
                routers=routers,
                pcs_per_lan=pcs_per_lan,
                laptops_per_lan=laptops_per_lan,
                switches_per_router=switches_per_router,
                servers=servers,
                access_points=access_points,
                has_wan=has_wan,
                dhcp=dhcp,
                routing=RoutingProtocol(routing),
                router_model=router_model,
                switch_model=switch_model,
                floating_routes=floating_routes,
                ospf_process_id=ospf_process_id,
                eigrp_as=eigrp_as,
                vlans=vlans,
            )
            plan, validation = plan_from_request(request)
        except (ValueError, ValidationError, KeyError, TypeError) as exc:
            return json.dumps(
                {"error": f"Invalid build request: {exc}",
                 "hint": "Check template/routing values and numeric ranges."},
                indent=2, ensure_ascii=False)
        explanation = explain_plan(plan)
        estimation = estimate_from_plan(plan)

        parts: list[str] = []

        # --- Summary ---
        parts.append("=" * 60)
        parts.append("TOPOLOGY SUMMARY")
        parts.append("=" * 60)
        parts.append(f"Devices: {len(plan.devices)}")
        parts.append(f"Links: {len(plan.links)}")
        parts.append(f"DHCP Pools: {len(plan.dhcp_pools)}")
        parts.append(f"Static routes: {len(plan.static_routes)}")
        parts.append(f"OSPF configs: {len(plan.ospf_configs)}")
        parts.append(f"RIP configs: {len(plan.rip_configs)}")
        parts.append(f"EIGRP configs: {len(plan.eigrp_configs)}")
        parts.append("")

        # --- Validation ---
        if validation.is_valid:
            parts.append("Validation: PASS")
        else:
            parts.append("Validation: FAIL")
            for err in validation.errors:
                parts.append(f"  ERROR [{err.code.value}]: {err.message}")
        if validation.warnings:
            for warn in validation.warnings:
                parts.append(f"  [{warn.code.value}]: {warn.message}")
        parts.append("")

        # --- Explanation ---
        parts.append("=" * 60)
        parts.append("EXPLANATION")
        parts.append("=" * 60)
        for e in explanation:
            parts.append(f"- {e}")
        parts.append("")

        # --- Addressing table ---
        parts.append("=" * 60)
        parts.append("ADDRESSING TABLE")
        parts.append("=" * 60)
        for dev in plan.devices:
            if dev.interfaces:
                parts.append(f"{dev.name} ({dev.model}):")
                for iface, ip in dev.interfaces.items():
                    parts.append(f"  {iface}: {ip}")
                if dev.gateway:
                    parts.append(f"  Gateway: {dev.gateway}")
            elif dev.gateway:
                parts.append(f"{dev.name}: DHCP (Gateway: {dev.gateway})")
        parts.append("")

        # --- PTBuilder script ---
        parts.append("=" * 60)
        parts.append("PTBUILDER SCRIPT")
        parts.append("=" * 60)
        parts.append(generate_full_script(plan))
        parts.append("")

        # --- CLI configs ---
        configs = generate_all_configs(plan)
        parts.append("=" * 60)
        parts.append("CLI CONFIGURATIONS")
        parts.append("=" * 60)
        for device_name, cli_block in configs.items():
            parts.append(f"\n--- {device_name} ---")
            parts.append(cli_block)

        pcs = [d for d in plan.devices if d.category in ("pc", "server", "laptop")]
        if pcs:
            parts.append(f"\n--- Hosts ---")
            use_dhcp = bool(plan.dhcp_pools)
            for pc in pcs:
                parts.append(generate_pc_config(pc, use_dhcp=use_dhcp))

        # --- Suggested validations ---
        if plan.validations:
            parts.append("")
            parts.append("=" * 60)
            parts.append("SUGGESTED CHECKS")
            parts.append("=" * 60)
            for v in plan.validations:
                parts.append(f"  {v.check_type}: {v.from_device} -> {v.to_target} (expected: {v.expected})")

        # --- Deploy ---
        if deploy:
            parts.append("")
            parts.append("=" * 60)
            parts.append("DEPLOYMENT IN PACKET TRACER")
            parts.append("=" * 60)
            # Prefer the live bridge (the only path that works on macOS/Linux);
            # fall back to file export only if PT is not connected.
            dep = _live_deploy_plan(plan, command_delay=1.0)
            if dep["deployed"]:
                parts.append(f"Deployed live via bridge: {dep['sent']}/{dep['total']} commands sent.")
                parts.append(f"   {len(plan.devices)} devices, {len(plan.links)} links.")
                parts.append("   (No copy/paste required - the commands were sent straight to PT.)")
            else:
                deploy_exec = DeployExecutor(output_dir="projects")
                deploy_result = deploy_exec.execute(plan, project_name=f"build_{routers}r_{pcs_per_lan}pc")
                parts.append("PT is not connected to the bridge - exported files for manual load.")
                parts.append(f"   Files in: {deploy_result['project_dir']}")
                if deploy_result["clipboard"]:
                    parts.append("   Script copied to the clipboard (Windows): paste it in PT > Extensions > Scripting.")
                else:
                    parts.append("   Open the Builder Code Editor in PT (auto-connects) and retry, or paste topology.js.")
                parts.append("")
                parts.append(deploy_result["instructions"])

        # --- Plan JSON ---
        parts.append("")
        parts.append("=" * 60)
        parts.append("PLAN JSON (for programmatic use)")
        parts.append("=" * 60)
        parts.append(plan.model_dump_json(indent=2))

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_export(
        plan_json: str,
        project_name: str = "topology",
        output_dir: str = "projects",
    ) -> str:
        """
        Export the plan to files: JS script, CLI configs and JSON.

        Parameters:
        - plan_json: plan JSON
        - project_name: Project name
        - output_dir: Output directory
        """
        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr
        executor = ManualExecutor(output_dir=output_dir)
        result = executor.execute(plan, project_name=project_name)

        lines = [
            f"Files exported in {result['project_dir']}:",
        ]
        for key, path in result["files"].items():
            lines.append(f"  - {key}: {path}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # DEPLOY (clipboard + instructions)
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_deploy(
        plan_json: str,
        project_name: str = "topology",
        output_dir: str = "projects",
    ) -> str:
        """
        Deploy a plan in Packet Tracer: copies the script to the Windows
        clipboard, exports the configuration files, and generates
        step-by-step instructions.

        Usage: after pt_full_build or pt_plan_topology, pass the plan JSON
        here to prepare everything for Packet Tracer.

        Parameters:
        - plan_json: plan JSON (output of pt_plan_topology or pt_full_build)
        - project_name: Project name
        - output_dir: Output directory
        """
        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr

        # Prefer the live bridge (works on macOS/Linux); if PT is not
        # connected, fall back to file export.
        dep = _live_deploy_plan(plan, command_delay=1.0)
        if dep["deployed"]:
            return (
                f"Topology deployed live via bridge.\n"
                f"  Commands sent: {dep['sent']}/{dep['total']}\n"
                f"  Devices: {len(plan.devices)}\n"
                f"  Links: {len(plan.links)}\n"
                f"  (No copy/paste - the commands went straight to PT.)"
            )

        executor = DeployExecutor(output_dir=output_dir)
        result = executor.execute(plan, project_name=project_name)

        parts: list[str] = ["PT is not connected to the bridge - exported files for manual load."]

        if result["clipboard"]:
            parts.append("SCRIPT COPIED TO THE CLIPBOARD")
            parts.append("Paste directly into Packet Tracer > Extensions > Scripting")
        else:
            parts.append("FILES EXPORTED (open the Builder Code Editor in PT - it auto-connects - and retry)")
            parts.append(f"Or open {result['project_dir']}/topology.js and copy its contents")

        parts.append("")
        parts.append(f"Project: {result['project_dir']}")
        parts.append(f"Devices: {result['devices_count']}")
        parts.append(f"Links: {result['links_count']}")
        parts.append("")

        for key, path in result["files"].items():
            parts.append(f"  {key}: {path}")

        parts.append("")
        parts.append(result["instructions"])

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # PROJECTS
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_list_projects(output_dir: str = "projects") -> str:
        """
        List the saved projects.

        Parameters:
        - output_dir: base directory of projects
        """
        repo = ProjectRepository(base_dir=output_dir)
        projects = repo.list_projects()
        if not projects:
            return "No saved projects."
        return json.dumps(projects, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_load_project(project_name: str, output_dir: str = "projects") -> str:
        """
        Return the plan JSON of a saved project.

        NOTE: this does NOT redraw the topology in Packet Tracer - it only
        reads the saved plan.json. To deploy it in PT, pass the returned JSON
        to pt_live_deploy(plan_json=...) (with the bridge connected).

        Parameters:
        - project_name: project name (with or without spaces - it is normalized)
        - output_dir: base directory of projects
        """
        repo = ProjectRepository(base_dir=output_dir)
        try:
            plan = repo.load_plan(project_name)
        except FileNotFoundError:
            available = [p.get("project_name", "?") for p in repo.list_projects()]
            return json.dumps({
                "error": f"Project '{project_name}' not found.",
                "available_projects": available,
            }, indent=2, ensure_ascii=False)
        except (ValueError, ValidationError) as exc:
            return json.dumps({
                "error": f"The plan.json of '{project_name}' is corrupt: {exc}",
            }, indent=2, ensure_ascii=False)
        return plan.model_dump_json(indent=2)

    # ------------------------------------------------------------------
    # LIVE DEPLOY (direct to Packet Tracer)
    # ------------------------------------------------------------------

    _BRIDGE_URL = "http://127.0.0.1:54321"
    _BOOTSTRAP = (
        '/* PT-MCP Bridge */ window.webview.evaluateJavaScriptAsync('
        '"setInterval(function(){var x=new XMLHttpRequest();'
        "x.open('GET','http://127.0.0.1:54321/next',true);"
        'x.onload=function(){if(x.status===200&&x.responseText)'
        "{$se('runCode',x.responseText)}};x.onerror=function(){};"
        'x.send()},500)");'
    )

    # Runtime patches that override the native functions of the PT script engine
    # with versions that have defensive guards. Without these, calling configureIosDevice
    # or addModule on hosts (PC/Server/Laptop) throws TypeError -> popup -> kills the bootstrap.
    # They are injected automatically when a freshly connected PT is detected (idempotent).
    # Important: use this.xxx (not a free assignment) because the functions are native
    # and are only overridden via global binding. Everything on a single line - PT's script
    # engine strips the \n from the JS source code.
    _RUNTIME_PATCHES_JS = (
        'this.addModule = function(deviceName, slot, model) { '
        'var device = ipc.network().getDevice(deviceName); if (!device) { return false; } '
        'var hasPower = typeof device.getPower === "function" && typeof device.setPower === "function"; '
        'var powerState = false; '
        'if (hasPower) { powerState = device.getPower(); device.setPower(false); } '
        'var moduleType = allModuleTypes[model]; '
        'var result = device.addModule(slot, moduleType, model); '
        'if (hasPower && powerState) { device.setPower(true); '
        'if (typeof device.skipBoot === "function") { device.skipBoot(); } } '
        'if (result != true) { return false; } return true; }; '
        # lwAddDevice — crea device en Logical view (canvas item visible sin save+reload).
        # The global addDevice only writes to the model + physical canvas; PT generates an auto-name
        # (Router0, Switch1) which we rename to the requested one via device.setName().
        'this.lwAddDevice = function(name, deviceType, model, x, y) { '
        'var lw = ipc.appWindow().getActiveWorkspace().getLogicalWorkspace(); '
        'var autoName = lw.addDevice(deviceType, model, x, y); '
        'if (autoName && autoName !== name) { '
        'var d = ipc.network().getDevice(autoName); '
        'if (d && typeof d.setName === "function") { d.setName(name); } } '
        'return name; }; '
        # lwAddLink - creates the link in the Logical view. Accepts cable as a string or enum int.
        'this.lwAddLink = function(d1, p1, d2, p2, cable) { '
        'var CT = {straight:8100,cross:8101,crossover:8101,roll:8102,fiber:8103,'
        'phone:8104,cable:8105,serial:8106,auto:8107,console:8108,wireless:8109,'
        'coaxial:8110,octal:8111,cellular:8112,usb:8113,custom_io:8114}; '
        'var t = (typeof cable === "number") ? cable : (CT[(cable || "auto").toLowerCase()] || 8107); '
        'var lw = ipc.appWindow().getActiveWorkspace().getLogicalWorkspace(); '
        'return lw.createLink(d1, p1, d2, p2, t); }; '
        # configurePcIp — fix: ya no hardcodea FastEthernet0. Busca primer port ethernet
        # del device iterando getPorts(). Funciona con PC-PT, Server-PT, Laptop-PT, etc.
        'this.configurePcIp = function(deviceName, dhcpEnabled, ipaddress, subnetMask, defaultGateway, dnsServer) { '
        'var device = ipc.network().getDevice(deviceName); if (!device) { return false; } '
        'var port = null; '
        'if (typeof device.getPorts === "function") { '
        'var ports = device.getPorts(); '
        'for (var i = 0; i < ports.length; i++) { '
        'var pn = ports[i]; if (typeof pn !== "string") continue; '
        'if (pn.indexOf("Ethernet") >= 0 || pn === "Wireless0") { '
        'var p = device.getPort(pn); if (p) { port = p; break; } } } } '
        'if (!port) { port = device.getPort("FastEthernet0"); } '
        'if (!port) { return false; } '
        'if (dhcpEnabled === true || dhcpEnabled === false) { '
        'if (typeof device.setDhcpFlag === "function") { device.setDhcpFlag(dhcpEnabled); } } '
        'if (ipaddress && subnetMask) port.setIpSubnetMask(ipaddress, subnetMask); '
        'if (defaultGateway) { '
        'if (typeof device.setDefaultGateway === "function") { device.setDefaultGateway(defaultGateway); } '
        'else if (typeof port.setDefaultGateway === "function") { port.setDefaultGateway(defaultGateway); } } '
        'if (dnsServer && typeof port.setDnsServerIp === "function") { port.setDnsServerIp(dnsServer); } '
        'return true; }; '
        'this.configureIosDevice = function(deviceName, commands) { '
        'var device = ipc.network().getDevice(deviceName); if (!device) { return false; } '
        'if (typeof device.skipBoot !== "function" || typeof device.enterCommand !== "function") { return false; } '
        'device.skipBoot(); var commandsArray = commands.split("\\n"); '
        'device.enterCommand("!", "global"); '
        'for (var i = 0; i < commandsArray.length; i++) { device.enterCommand(commandsArray[i], ""); } '
        'device.enterCommand("write memory", "enable"); return true; };'
        # --- Query helpers: report their result back via reportResult() (provided by the
        #     Builder extension's runcode.js, routed to /result through the webview bridge). ---
        'this.queryTopology = function() { '
        'var net = ipc.network(); var count = net.getDeviceCount(); var devices = []; '
        'for (var i = 0; i < count; i++) { var d = net.getDeviceAt(i); '
        'var dev = { name: d.getName(), type: d.getType() }; '
        'try { if (typeof d.getModel === "function") dev.model = d.getModel(); } catch (e) {} '
        'try { dev.x = Math.round(d.getXCoordinate()); dev.y = Math.round(d.getYCoordinate()); } catch (e) {} '
        'devices.push(dev); } '
        'reportResult(JSON.stringify({ count: count, devices: devices })); }; '
        'this.renameDevice = function(oldName, newName) { '
        'var d = ipc.network().getDevice(oldName); '
        'if (!d) { reportResult(JSON.stringify({ success: false, error: "device not found" })); return; } '
        'd.setName(newName); reportResult(JSON.stringify({ success: true })); }; '
        'this.deleteDevice = function(name) { '
        'if (!ipc.network().getDevice(name)) { reportResult(JSON.stringify({ success: false, error: "device not found" })); return; } '
        'var ws = ipc.appWindow().getActiveWorkspace().getLogicalWorkspace(); '
        'var ok = ws.removeDevice(name); '
        'reportResult(JSON.stringify({ success: ok === true })); }; '
        'this.moveDevice = function(name, x, y) { '
        'var d = ipc.network().getDevice(name); '
        'if (!d) { reportResult(JSON.stringify({ success: false, error: "device not found" })); return; } '
        'd.moveToLocation(x, y); '
        'reportResult(JSON.stringify({ success: true, x: d.getXCoordinate(), y: d.getYCoordinate() })); }; '
        'this.deleteLink = function(deviceName, portName) { '
        'var d = ipc.network().getDevice(deviceName); '
        'if (!d) { reportResult(JSON.stringify({ success: false, error: "device not found" })); return; } '
        'var p = d.getPort(portName); '
        'if (!p) { reportResult(JSON.stringify({ success: false, error: "port not found" })); return; } '
        'if (typeof p.getLink === "function" && !p.getLink()) { reportResult(JSON.stringify({ success: false, error: "no link on that port" })); return; } '
        'p.deleteLink(); '
        'reportResult(JSON.stringify({ success: true })); };'
    )

    # Internal singleton bridge - started automatically inside the MCP process
    _bridge_instance: PTCommandBridge | None = None
    # Idempotent flag - true if the runtime patches were already sent to this PT session.
    # Reset when PT disconnects so they are reapplied on reconnect.
    _patches_applied: list[bool] = [False]  # list for mutation in closures

    def _http_get(url: str, timeout: float = 2.0):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8")
        except Exception:
            return None, None

    def _http_post(url: str, body: str, timeout: float = 3.0):
        try:
            data = body.encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "text/plain")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8")
        except Exception:
            return None, None

    def _bridge_is_up() -> bool:
        status, _ = _http_get(f"{_BRIDGE_URL}/ping", timeout=1.0)
        return status == 200

    def _bridge_pt_connected() -> bool:
        status, body = _http_get(f"{_BRIDGE_URL}/status", timeout=1.0)
        if status == 200 and body:
            try:
                connected = json.loads(body).get("connected", False)
                if not connected:
                    # PT disconnected - reset flag to reapply patches on reconnect
                    _patches_applied[0] = False
                return connected
            except Exception:
                pass
        return False

    def _ensure_pt_patches() -> None:
        """Inject the runtime patches into PT if they were not yet applied on this connection.

        Idempotent - the _patches_applied flag avoids resending on every operation.
        Reset automatically when _bridge_pt_connected detects a disconnection.
        """
        if _patches_applied[0]:
            return
        if not _bridge_is_up():
            return
        # Queue the patches in the bridge. PT executes them on its next poll.
        status, _ = _http_post(f"{_BRIDGE_URL}/queue", _RUNTIME_PATCHES_JS)
        if status == 200:
            _patches_applied[0] = True

    def _ensure_bridge() -> bool:
        """
        Ensure a bridge is listening on :54321.
        If one already exists (internal or external), do nothing.
        If there is none, start one in-process as a daemon thread.
        Returns True if the bridge is operational.
        """
        nonlocal _bridge_instance
        if _bridge_is_up():
            return True  # one is already active (internal or external start_bridge.ps1)
        if _bridge_instance is None:
            try:
                b = PTCommandBridge()
                b.start()
                _bridge_instance = b
            except OSError:
                return False  # port blocked by an external non-bridge process
        return _bridge_is_up()

    # --- Start the bridge IMMEDIATELY when registering tools ---
    _ensure_bridge()

    def _live_deploy_plan(plan, command_delay: float = 1.0) -> dict:
        """Deploy a plan in PT over the live bridge (if connected).

        Returns {deployed, sent, total}. deployed=False if the bridge is down or
        PT is not connected - the caller must fall back to file export.
        This is the path that DOES work on macOS (the DeployExecutor clipboard
        only works on Windows).
        """
        if command_delay < 1.0:
            command_delay = 1.0
        if not (_ensure_bridge() and _bridge_pt_connected()):
            return {"deployed": False, "sent": 0, "total": 0}
        _ensure_pt_patches()
        script = generate_executable_script(plan)
        commands = [
            line.strip() for line in script.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        sent = 0
        for cmd in commands:
            status, _ = _http_post(f"{_BRIDGE_URL}/queue", cmd)
            if status == 200:
                sent += 1
            time.sleep(command_delay)
        # Only claim a deploy if there was something to send AND every command was
        # accepted; sent=0 (all POSTs failed) or a partial send is NOT success.
        deployed = len(commands) > 0 and sent == len(commands)
        return {"deployed": deployed, "sent": sent, "total": len(commands)}

    @mcp.tool()
    def pt_live_deploy(
        plan_json: str,
        command_delay: float = 1.0,
    ) -> str:
        """
        Send commands directly to Packet Tracer in real time.

        The HTTP bridge starts automatically inside the MCP server -
        you do not need to run start_bridge.ps1 or any external process.
        Just make sure the bootstrap is running in the Builder Code Editor.

        Parameters:
        - plan_json: plan JSON (output of pt_plan_topology or pt_full_build)
        - command_delay: delay between commands in seconds (default 1.0).
          Values below 1.0 may trigger error popups in PT because
          configureIosDevice/configurePcIp run before the device
          finishes initializing. The received value is clamped to a minimum of 1.0.
        """
        if command_delay < 1.0:
            command_delay = 1.0
        if not _ensure_bridge():
            return (
                "Could not start the HTTP bridge on :54321.\n"
                "Port blocked by another process. Free the port and try again."
            )

        if not _bridge_pt_connected():
            return (
                "Bridge active at http://127.0.0.1:54321 but PT is NOT connected.\n\n"
                "Paste this into the Builder Code Editor (Extensions > Builder Code Editor) "
                "and click Run:\n\n"
                + _BOOTSTRAP
                + "\n\nThen call pt_live_deploy again.\n\n"
                "IMPORTANT: XMLHttpRequest does NOT exist in PT's Script Engine.\n"
                "The bootstrap injects a polling loop in the webview (QWebEngine) "
                "which DOES have XMLHttpRequest."
            )

        plan, _perr = _load_plan_or_error(plan_json)
        if _perr:
            return _perr

        dep = _live_deploy_plan(plan, command_delay)
        sent = dep["sent"]

        return (
            f"Topology deployed in Packet Tracer!\n"
            f"  Commands sent: {sent}/{dep['total']}\n"
            f"  Devices: {len(plan.devices)}\n"
            f"  Links: {len(plan.links)}"
        )

    @mcp.tool()
    def pt_bridge_status() -> str:
        """
        Check the status of the HTTP bridge with Packet Tracer.
        The bridge starts automatically if it is not running -
        you do not need to run start_bridge.ps1 manually.
        """
        if not _ensure_bridge():
            return (
                "Could not start the HTTP bridge on :54321.\n"
                "Port blocked by another process. Free the port and try again."
            )

        if _bridge_pt_connected():
            return "Bridge ACTIVE and CONNECTED. Packet Tracer is receiving commands at http://127.0.0.1:54321"

        return (
            "Bridge active at http://127.0.0.1:54321 but PT is NOT connected.\n\n"
            "Paste this into the Builder Code Editor (Extensions > Builder Code Editor) "
            "and click Run:\n\n"
            + _BOOTSTRAP
        )

    # ------------------------------------------------------------------
    # Helpers for bidirectional tools (send command -> wait for result)
    # ------------------------------------------------------------------

    def _js_escape(s: str) -> str:
        """Escape a string for safe insertion into JS string literals.

        Includes newline/CR so a value containing them can't break out of the
        literal and corrupt the whole script (matches build_configure_js)."""
        return (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    def _bridge_send_and_wait(js_call: str, timeout: float = 10.0) -> str | None:
        """
        Send a JS command to the bridge and wait for the response (long-poll GET /result).
        The command must call reportResult(...) internally to send data back.
        Requires the bridge to be active and PT connected.

        The result channel has no per-request correlation, so we (1) drain any
        orphaned result left by an earlier timed-out call before queueing, and
        (2) long-poll up to the caller's full `timeout` - passing it to the
        server (which honors ?timeout) and looping on 204 - so slow operations
        no longer falsely time out and leave their result stranded.
        """
        # Clear stale/orphaned results so we read OUR command's reply, not a
        # previous call's late one.
        _http_get(f"{_BRIDGE_URL}/drain", timeout=2.0)
        status_post, _ = _http_post(f"{_BRIDGE_URL}/queue", js_call)
        if status_post != 200:
            return None
        deadline = time.monotonic() + max(0.1, timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            wait = min(remaining, 28.0)
            status_get, body = _http_get(
                f"{_BRIDGE_URL}/result?timeout={wait:.1f}", timeout=wait + 3.0)
            if status_get == 200:
                return body
            if status_get == 204:
                continue  # server long-poll expired with no result; keep waiting
            # transient network error - brief backoff, then retry within deadline
            time.sleep(0.1)

    def _check_bridge() -> str | None:
        """Check bridge+PT connectivity. Returns error message or None if OK.

        If PT is connected, it also ensures the runtime patches are
        applied (idempotent - only sends the first time per connection).
        """
        if not _ensure_bridge():
            return "Could not start the bridge on :54321."
        if not _bridge_pt_connected():
            return (
                "Bridge active but PT is not connected.\n"
                "Run the bootstrap in the Builder Code Editor."
            )
        _ensure_pt_patches()
        return None

    # ------------------------------------------------------------------
    # QUERY / INTERACT with an existing topology in PT
    # ------------------------------------------------------------------

    @mcp.tool()
    def pt_query_topology() -> str:
        """
        Query which devices are currently in Packet Tracer.
        Returns name, type and model of each device in the active topology.
        Requires a connected bridge (pt_bridge_status to verify).
        """
        err = _check_bridge()
        if err:
            return err

        result = _bridge_send_and_wait("queryTopology()", timeout=10.0)
        if result is None:
            return "No response from PT (timeout). Verify that the bootstrap is running."
        try:
            data = json.loads(result)
        except Exception:
            return f"Unexpected response from PT: {result}"

        devices = data.get("devices", [])
        if not devices:
            return "No devices in the current topology."

        type_labels = {
            0: "Router", 1: "Switch", 7: "AccessPoint", 8: "PC",
            9: "Server", 16: "L3 Switch", 17: "Laptop", 18: "Tablet",
        }
        lines = [f"Devices in Packet Tracer ({data.get('count', len(devices))}):", ""]
        for d in devices:
            type_name = d.get("typeName")
            model_name = d.get("model")
            if not type_name or type_name.lower() == "unknown":
                catalog_model = resolve_model(model_name) if model_name else None
                if catalog_model:
                    type_name = catalog_model.category
                else:
                    type_name = type_labels.get(d.get("type"), f"type={d.get('type')}")
            model = f" [{model_name}]" if model_name else ""
            pos = f"  pos=({d['x']},{d['y']})" if d.get("x") is not None else ""
            lines.append(f"  {d['name']:15}  {type_name}{model}{pos}")
        return "\n".join(lines)

    @mcp.tool()
    def pt_delete_device(device_name: str) -> str:
        """
        Delete a device from the active topology in Packet Tracer.
        Also removes all of its links automatically.

        Parameters:
        - device_name: exact device name (e.g. "R1", "PC3", "Laptop-WAN")
        """
        err = _check_bridge()
        if err:
            return err

        safe_name = _js_escape(device_name)
        js = f'deleteDevice("{safe_name}")'
        result = _bridge_send_and_wait(js, timeout=8.0)
        if result is None:
            return f"No response from PT. The device '{device_name}' may not exist."
        try:
            data = json.loads(result)
            if data.get("success"):
                return f"Device '{device_name}' deleted successfully."
            else:
                return f"Error deleting '{device_name}': {data.get('error', 'unknown')}"
        except Exception:
            return f"Unexpected response: {result}"

    @mcp.tool()
    def pt_rename_device(old_name: str, new_name: str) -> str:
        """
        Rename a device in the active Packet Tracer topology.

        Parameters:
        - old_name: current device name
        - new_name: new name
        """
        err = _check_bridge()
        if err:
            return err

        safe_old = _js_escape(old_name)
        safe_new = _js_escape(new_name)
        js = f'renameDevice("{safe_old}", "{safe_new}")'
        result = _bridge_send_and_wait(js, timeout=8.0)
        if result is None:
            return f"No response from PT."
        try:
            data = json.loads(result)
            if data.get("success"):
                return f"Device renamed: '{old_name}' -> '{new_name}'"
            else:
                return f"Error: {data.get('error', 'unknown')}"
        except Exception:
            return f"Unexpected response: {result}"

    @mcp.tool()
    def pt_move_device(device_name: str, x: int, y: int) -> str:
        """
        Move a device to new coordinates on the Packet Tracer canvas.

        Parameters:
        - device_name: device name
        - x: X coordinate (canvas logical view, e.g. 100-800)
        - y: Y coordinate (canvas logical view, e.g. 100-600)
        """
        err = _check_bridge()
        if err:
            return err

        safe_name = _js_escape(device_name)
        js = f'moveDevice("{safe_name}", {int(x)}, {int(y)})'
        result = _bridge_send_and_wait(js, timeout=8.0)
        if result is None:
            return f"No response from PT."
        try:
            data = json.loads(result)
            if data.get("success"):
                return f"Device '{device_name}' moved to ({x}, {y})."
            else:
                return f"Error: {data.get('error', 'unknown')}"
        except Exception:
            return f"Unexpected response: {result}"

    @mcp.tool()
    def pt_delete_link(device_name: str, interface_name: str) -> str:
        """
        Delete the link connected to a specific interface of a device in PT.

        Parameters:
        - device_name: device name (e.g. "R1")
        - interface_name: interface name (e.g. "GigabitEthernet0/0", "FastEthernet0/1")
        """
        err = _check_bridge()
        if err:
            return err

        safe_dev = _js_escape(device_name)
        safe_iface = _js_escape(interface_name)
        js = f'deleteLink("{safe_dev}", "{safe_iface}")'
        result = _bridge_send_and_wait(js, timeout=8.0)
        if result is None:
            return f"No response from PT."
        try:
            data = json.loads(result)
            if data.get("success"):
                return f"Link on {device_name}/{interface_name} deleted."
            else:
                return f"Error: {data.get('error', 'unknown')}\nNote: if the method does not exist in this version of PT, try pt_delete_device and recreate the links."
        except Exception:
            return f"Unexpected response: {result}"

    @mcp.tool()
    def pt_set_port(
        device: str,
        interface: str,
        bandwidth: int = 0,
        bandwidth_auto: int = -1,
        full_duplex: int = -1,
        duplex_auto: int = -1,
        description: str = "",
        mac_address: str = "",
        power: int = -1,
    ) -> str:
        """
        Configure low-level attributes of a port on a live device in PT.

        Only applies the attributes passed explicitly (parameters with sentinel
        defaults). Useful for tweaks the CLI does not expose easily or that you
        want to apply without entering `configure terminal`.

        Parameters:
        - device: device name in PT (e.g. "R1")
        - interface: interface name (e.g. "GigabitEthernet0/0")
        - bandwidth: bandwidth in kbps (>0 to apply; 0 = no change)
        - bandwidth_auto: 1 enables BW auto-negotiate, 0 disables it, -1 no change
        - full_duplex: 1 full duplex, 0 half duplex, -1 no change
        - duplex_auto: 1 enables duplex auto-negotiate, 0 disables, -1 no change
        - description: descriptive text (empty = no change)
        - mac_address: MAC in "AABB.CCDD.EEFF" format (empty = no change)
        - power: 1 powers the port on, 0 powers it off, -1 no change

        Returns which attributes were applied (those with an available method on
        the port API). If a `setXxx` does not exist on the device model, it is
        silently ignored and only what actually stuck is reported.
        """
        err = _check_bridge()
        if err:
            return err

        parts = [
            'var d=ipc.network().getDevice(' + json.dumps(device) + ');',
            'if(!d){reportResult(JSON.stringify({success:false,error:"device not found: ' + _js_escape(device) + '"}));return;}',
            'var p=d.getPort(' + json.dumps(interface) + ');',
            'if(!p){reportResult(JSON.stringify({success:false,error:"port not found: ' + _js_escape(interface) + '"}));return;}',
            'var applied=[];',
        ]

        if bandwidth and bandwidth > 0:
            parts.append(
                f'if(typeof p.setBandwidth==="function"){{p.setBandwidth({int(bandwidth)});applied.push("bandwidth={int(bandwidth)}");}}'
            )
        if bandwidth_auto in (0, 1):
            v = "true" if bandwidth_auto == 1 else "false"
            parts.append(
                f'if(typeof p.setBandwidthAutoNegotiate==="function"){{p.setBandwidthAutoNegotiate({v});applied.push("bandwidth_auto={v}");}}'
            )
        if full_duplex in (0, 1):
            v = "true" if full_duplex == 1 else "false"
            parts.append(
                f'if(typeof p.setFullDuplex==="function"){{p.setFullDuplex({v});applied.push("full_duplex={v}");}}'
            )
        if duplex_auto in (0, 1):
            v = "true" if duplex_auto == 1 else "false"
            parts.append(
                f'if(typeof p.setDuplexAutoNegotiate==="function"){{p.setDuplexAutoNegotiate({v});applied.push("duplex_auto={v}");}}'
            )
        if description:
            parts.append(
                f'if(typeof p.setDescription==="function"){{p.setDescription({json.dumps(description)});applied.push("description");}}'
            )
        if mac_address:
            parts.append(
                f'if(typeof p.setMacAddress==="function"){{p.setMacAddress({json.dumps(mac_address)});applied.push("mac");}}'
            )
        if power in (0, 1):
            v = "true" if power == 1 else "false"
            parts.append(
                f'if(typeof p.setPower==="function"){{p.setPower({v});applied.push("power={v}");}}'
            )

        parts.append('reportResult(JSON.stringify({success:true,applied:applied}));')

        # IIFE para que los `return` tempranos funcionen en el Script Engine de PT.
        js = '(function(){' + ''.join(parts) + '})()'

        result = _bridge_send_and_wait(js, timeout=8.0)
        if result is None:
            return "Sin respuesta de PT."
        try:
            data = json.loads(result)
            if data.get("success"):
                applied = data.get("applied", [])
                if not applied:
                    return (
                        f"Nothing applied on {device}/{interface}: "
                        "no attributes were passed or no setXxx is available on this model."
                    )
                return f"Aplicado en {device}/{interface}: " + ", ".join(applied)
            return f"Error: {data.get('error', 'desconocido')}"
        except Exception:
            return f"Respuesta inesperada: {result}"

    @mcp.tool()
    def pt_send_raw(js_code: str, wait_result: bool = False) -> str:
        """
        Send arbitrary JavaScript code to Packet Tracer via the bridge.
        Useful to explore the ipc API or run custom commands.

        If wait_result=True, waits for the code to call reportResult(...).
        Example:
          pt_send_raw("reportResult(getDevices('router'))", wait_result=True)
          pt_send_raw("addDevice('TestR','2911',500,300)")

        Parameters:
        - js_code: JavaScript code to run in PT's Script Engine
        - wait_result: if True, waits for a response via reportResult()
        """
        err = _check_bridge()
        if err:
            return err

        if wait_result:
            result = _bridge_send_and_wait(js_code, timeout=10.0)
            if result is None:
                return "No response (timeout). Make sure the code calls reportResult(...)."
            return result
        else:
            status, _ = _http_post(f"{_BRIDGE_URL}/queue", js_code)
            if status == 200:
                return "Command sent to PT."
            return "Error sending command to the bridge."

    # ------------------------------------------------------------------
    # MODULES - install expansion modules on live devices
    # ------------------------------------------------------------------

    @mcp.tool()
    def pt_list_modules(
        router_model: str = "",
        category: str = "",
    ) -> str:
        """
        List available expansion modules from the PT catalog.

        With no filters returns ALL modules. Useful to discover exact names
        before calling pt_add_module.

        Parameters:
        - router_model: if specified (e.g. "2911", "ISR4321"), filters to
          modules compatible with that router. Includes generic modules
          (with no compatible_with list) and those that list that model.
        - category: filters by category (e.g. "router_hwic", "router_nm",
          "router_nim", "router_wic"). Empty = all.

        Returns JSON with: name, description, category, ports_added,
        compatible_with.
        """
        rm = (router_model or "").strip()
        cat = (category or "").strip().lower()

        items = []
        for mod in ALL_MODULES.values():
            if cat and mod.category.lower() != cat:
                continue
            if rm and mod.compatible_with and rm not in mod.compatible_with:
                continue
            items.append({
                "name": mod.name,
                "description": mod.description,
                "category": mod.category,
                "module_type": mod.module_type,
                "ports_added": list(mod.ports_added),
                "compatible_with": list(mod.compatible_with) if mod.compatible_with else "any",
            })

        items.sort(key=lambda x: (x["category"], x["name"]))
        return json.dumps({
            "count": len(items),
            "filter": {"router_model": rm or None, "category": cat or None},
            "modules": items,
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_add_module(
        device_name: str,
        slot: str,
        module_name: str,
        dry_run: bool = False,
    ) -> str:
        """
        Install an expansion module on a device in the active topology.

        The runtime patch already injected in PT powers off the device, installs the
        module and powers it back on (with skipBoot). You do NOT need to power off by hand.

        Parameters:
        - device_name: exact device name in PT (e.g. "R1"). Use
          pt_query_topology to list valid names.
        - slot: slot identifier as a STRING. The format depends on the
          device's slot type:
            * HWIC on 1941/2901/2911 -> "0/0", "0/1", "0/2", "0/3"
              (chassis-slot/hwic-subslot)
            * NM on 2911            -> "1" or "2"
            * NIM on ISR4321/4331   -> "0" or "1"
            * Cloud-PT/Server-PT/PCs -> "0", "1", ... depending on the available slot
          If you pass an integer it is also accepted and converted to a string.
        - module_name: exact module name, e.g. "HWIC-2T", "NM-4A/S",
          "NIM-2T", "HWIC-1GE-SFP". Use pt_list_modules to discover them.
        - dry_run: if True, validates and returns the JS payload without sending it.

        Example: add 2 serial ports to R1 on HWIC slot 0:
          pt_add_module(device_name="R1", slot="0/0", module_name="HWIC-2T")
        """
        # Coerce slot to string (accepts int for compat) and validate non-empty
        if isinstance(slot, bool) or slot is None:
            return f"Error: invalid slot (received: {slot!r})."
        slot_s = str(slot).strip()
        if not slot_s:
            return "Error: slot cannot be empty."

        # Validate module name
        spec = resolve_module(module_name)
        if not spec:
            return (
                f"Error: module '{module_name}' not found in the catalog.\n"
                f"Call pt_list_modules to see the valid names."
            )

        # Build JS payload
        safe_name = _js_escape(device_name)
        safe_module = _js_escape(spec.name)
        safe_slot = _js_escape(slot_s)
        ports_added = ", ".join(spec.ports_added) if spec.ports_added else "(no ports)"

        if dry_run:
            return json.dumps({
                "summary": f"[dry_run] Payload generated to install {spec.name} on {device_name} slot {slot_s}.",
                "device": device_name,
                "slot": slot_s,
                "module": spec.name,
                "description": spec.description,
                "ports_added": list(spec.ports_added),
                "compatible_with": list(spec.compatible_with) if spec.compatible_with else "any",
                "js_payload": f'addModule("{safe_name}", "{safe_slot}", "{safe_module}")',
                "sent": False,
                "dry_run": True,
            }, indent=2, ensure_ascii=False)

        # Check bridge + PT
        err = _check_bridge()
        if err:
            return err

        # Check that the device exists and validate compatibility
        devices = _query_pt_devices()
        if devices:
            target = next((d for d in devices if d.get("name") == device_name), None)
            if target is None:
                names = sorted({d.get("name", "") for d in devices if d.get("name")})
                return (
                    f"Error: device '{device_name}' does not exist in PT.\n"
                    f"Current devices: {', '.join(names) or '(none)'}"
                )
            if spec.compatible_with:
                target_model = target.get("model", "") or ""
                if target_model and target_model not in spec.compatible_with:
                    return (
                        f"Error: module '{spec.name}' is not compatible with model '{target_model}'.\n"
                        f"Compatible with: {', '.join(spec.compatible_with)}"
                    )

        # Send to the bridge - the runtime patch handles the power cycle automatically.
        # We wait for a response to confirm success (the install takes a few seconds).
        js = (
            f'var __ok = addModule("{safe_name}", "{safe_slot}", "{safe_module}"); '
            f'reportResult(JSON.stringify({{success: __ok === true, returned: __ok}}));'
        )
        result = _bridge_send_and_wait(js, timeout=15.0)

        if result is None:
            return (
                f"No response from PT (timeout). Possible causes:\n"
                f"  - The module is still being installed (the power cycle can take a while)\n"
                f"  - The module name does not exist in PT's allModuleTypes\n"
                f"  - The slot '{slot_s}' is already occupied or does not exist\n"
                f"Verify manually with pt_query_topology."
            )

        try:
            data = json.loads(result)
            success = bool(data.get("success"))
        except Exception:
            return f"Unexpected response from PT: {result}"

        if success:
            return (
                f"Module installed on {device_name}.\n"
                f"  Slot: {slot_s}\n"
                f"  Module: {spec.name} - {spec.description}\n"
                f"  Ports added: {ports_added}\n"
                f"  PT powered the device off/on automatically."
            )
        return (
            f"PT rejected the installation of '{spec.name}' on {device_name} slot '{slot_s}'.\n"
            f"Common causes:\n"
            f"  - Slot occupied by another module\n"
            f"  - Module incompatible with the device model\n"
            f"  - Slot out of range or wrong format (HWIC: '0/0', NM: '1', NIM: '0')"
        )

    @mcp.tool()
    def pt_install_modules_batch(
        modules: list[dict],
        dry_run: bool = False,
    ) -> str:
        """
        Install N modules in a single runCode JS - power-off -> addModule x N -> power-on.

        Useful when several serial modules (HWIC-2T, NIM-2T, etc.) must be added on
        several routers at once. PREFER this tool over multiple calls to
        pt_add_module: each individual power-cycle can pause PT's script engine
        > 5s and kill the bridge bootstrap polling.

        Parameters:
        - modules: list of dicts with {device, slot, module}. Example for RTR-4 with
          4 serial ports on a 2911 (which does NOT accept NM-4A/S):
            [
              {"device": "RTR-4", "slot": "0/0", "module": "HWIC-2T"},
              {"device": "RTR-4", "slot": "0/1", "module": "HWIC-2T"}
            ]
          -> generates Serial0/0/0..0/0/1, Serial0/1/0..0/1/1.
        - dry_run: if True, validates and returns the JS payload without sending it.

        Slot rules (string):
          HWIC on 1941/2901/2911 -> "0/0", "0/1", "0/2", "0/3"
          NIM on ISR4321/4331    -> "0", "1"
          Cloud-PT / hosts        -> "0".."7"

        Returns JSON with summary, per-module status and js_payload.
        """
        if not isinstance(modules, list) or not modules:
            return json.dumps({"error": "modules must be a non-empty list of {device, slot, module}."})

        # Validate each entry against the catalog
        validated = []
        errors = []
        for idx, entry in enumerate(modules):
            if not isinstance(entry, dict):
                errors.append(f"[{idx}] is not a dict")
                continue
            dev = entry.get("device")
            slot = entry.get("slot")
            mod = entry.get("module")
            if not dev or not isinstance(dev, str):
                errors.append(f"[{idx}] device required (str)")
                continue
            if slot is None or isinstance(slot, bool):
                errors.append(f"[{idx}] slot required")
                continue
            slot_s = str(slot).strip()
            if not slot_s:
                errors.append(f"[{idx}] empty slot")
                continue
            if not mod or not isinstance(mod, str):
                errors.append(f"[{idx}] module required (str)")
                continue
            spec = resolve_module(mod)
            if not spec:
                errors.append(f"[{idx}] module '{mod}' does not exist (use pt_list_modules)")
                continue
            validated.append({
                "device": dev, "slot": slot_s,
                "module": spec.name,
                "ports_added": list(spec.ports_added),
                "compatible_with": list(spec.compatible_with) if spec.compatible_with else None,
            })

        if errors:
            return json.dumps({
                "error": "Validation failed",
                "details": errors,
            }, indent=2, ensure_ascii=False)

        # Build a single JS one-liner: power-off of unique devices -> addModule x N -> power-on
        unique_devs = []
        seen = set()
        for v in validated:
            if v["device"] not in seen:
                seen.add(v["device"])
                unique_devs.append(v["device"])

        # JS literal arrays for devices and modules
        devs_js = "[" + ",".join(f'"{_js_escape(d)}"' for d in unique_devs) + "]"
        mods_js = "[" + ",".join(
            f'["{_js_escape(v["device"])}","{_js_escape(v["slot"])}","{_js_escape(v["module"])}"]'
            for v in validated
        ) + "]"

        js = (
            f"var DEVS={devs_js};var MODS={mods_js};"
            "var saved=[];"
            "for(var i=0;i<DEVS.length;i++){"
            "var d=ipc.network().getDevice(DEVS[i]);"
            "if(!d)continue;"
            "var hp=typeof d.getPower===\"function\";"
            "var was=hp?d.getPower():false;"
            "if(hp&&was)d.setPower(false);"
            "saved.push({n:DEVS[i],hp:hp,was:was});"
            "}"
            "for(var j=0;j<MODS.length;j++){"
            "var m=MODS[j];var dd=ipc.network().getDevice(m[0]);"
            "if(!dd)continue;"
            "dd.addModule(m[1],allModuleTypes[m[2]],m[2]);"
            "}"
            "for(var k=0;k<saved.length;k++){"
            "var s=saved[k];if(!s.hp||!s.was)continue;"
            "var dx=ipc.network().getDevice(s.n);if(!dx)continue;"
            "dx.setPower(true);"
            "if(typeof dx.skipBoot===\"function\")dx.skipBoot();"
            "}"
        )

        summary = {
            "total_modules": len(validated),
            "devices_affected": unique_devs,
            "modules": validated,
            "js_payload": js,
            "dry_run": dry_run,
            "sent": False,
        }

        if dry_run:
            summary["summary"] = f"[dry_run] {len(validated)} module(s) on {len(unique_devs)} device(s)."
            return json.dumps(summary, indent=2, ensure_ascii=False)

        err = _check_bridge()
        if err:
            return err

        # Check devices exist + validate module compatibility
        pt_devices = _query_pt_devices()
        if pt_devices:
            by_name = {d.get("name"): d for d in pt_devices}
            for v in validated:
                if v["device"] not in by_name:
                    return f"Error: device '{v['device']}' does not exist in PT."
                if v["compatible_with"]:
                    target_model = by_name[v["device"]].get("model", "") or ""
                    if target_model and target_model not in v["compatible_with"]:
                        return (
                            f"Error: module '{v['module']}' incompatible with model "
                            f"'{target_model}' (device '{v['device']}').\n"
                            f"Compatible with: {', '.join(v['compatible_with'])}"
                        )

        # Fire-and-forget - the batch does everything in one runCode, we do not need to wait.
        # Waiting can time out because the power-on at the end takes time to stabilize.
        if not _bridge_send_payload(js):
            return "Error sending batch to the bridge."

        summary["sent"] = True
        summary["summary"] = (
            f"Batch sent: {len(validated)} module(s) on {len(unique_devs)} device(s).\n"
            f"PT is powering off, installing and powering back on in a single step. "
            f"Verify with pt_query_topology or by querying getPorts() on each router."
        )
        return json.dumps(summary, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # ACL - apply and remove Access Control Lists via the bridge
    # ------------------------------------------------------------------

    def _query_pt_devices() -> list[dict]:
        """Helper: query PT's active topology and return the list of devices."""
        result = _bridge_send_and_wait("queryTopology()", timeout=10.0)
        if result is None:
            return []
        try:
            data = json.loads(result)
            return data.get("devices", []) or []
        except Exception:
            return []

    def _bridge_send_payload(js_call: str) -> bool:
        """Helper: send a JS payload to the bridge (fire-and-forget)."""
        status, _ = _http_post(f"{_BRIDGE_URL}/queue", js_call)
        return status == 200

    @mcp.tool()
    def pt_apply_acl(
        router: str,
        name_or_number: str,
        acl_type: str,
        entries: list[dict],
        binding_interface: str = "",
        binding_direction: str = "in",
        dry_run: bool = False,
    ) -> str:
        """
        Apply an Access Control List (ACL) to a router in PT's active topology.

        Pipeline: build plan -> static validation (ranges, types, IPs/wildcards,
        unreachable rules) -> verify router/interface against PT via the bridge ->
        generate CLI IOS -> send via configureIosDevice.

        Parameters:
        - router: device name in PT (e.g. "CORE-R1"). Call
          pt_query_topology if you are unsure of the exact names.
        - name_or_number: IOS identifier of the ACL.
            * 1-99 or 1300-1999 -> standard
            * 100-199 or 2000-2699 -> extended
            * any alphanumeric string -> named ACL
        - acl_type: "standard" or "extended". Standard only filters by source.
          Extended allows source + destination + protocol + ports.
        - entries: list of rules. Each rule is a dict with:
            * action: "permit" | "deny" (required)
            * protocol: "ip" | "icmp" | "tcp" | "udp" | ... (default "ip")
            * source: "any" | "host A.B.C.D" | "A.B.C.D wildcard" (required)
            * destination: same as source (extended only)
            * source_port_op / source_port: e.g. "eq" / 80 (TCP/UDP, optional)
            * dest_port_op / dest_port / dest_port_end: same (optional)
            * icmp_type: "echo" | "echo-reply" | ... (ICMP only)
            * tcp_flags: ["established"] | ["syn"] (TCP only, optional)
            * log: bool (optional)
            * remark: optional comment
        - binding_interface: if specified, applies the ACL to that interface
          (e.g. "GigabitEthernet0/0"). If empty, the ACL is only defined without applying.
        - binding_direction: "in" or "out" (default "in"). Only applies if
          binding_interface is defined.
        - dry_run: if True, does NOT send anything to the bridge - only validates and returns
          the CLI/JS payload for inspection.

        Example: block ping from 192.168.1.0/24 to 192.168.0.0/24 on CORE-R1:
          pt_apply_acl(
              router="CORE-R1",
              name_or_number="101",
              acl_type="extended",
              entries=[
                  {"action": "deny", "protocol": "icmp",
                   "source": "192.168.1.0 0.0.0.255",
                   "destination": "192.168.0.0 0.0.0.255",
                   "icmp_type": "echo"},
                  {"action": "permit", "protocol": "ip",
                   "source": "any", "destination": "any"},
              ],
              binding_interface="GigabitEthernet0/0",
              binding_direction="in",
          )
        """
        plan = build_acl_plan(router, name_or_number, acl_type, entries)
        binding = None
        if binding_interface:
            binding = ACLBinding(
                router=router,
                interface=binding_interface,
                acl_id=str(name_or_number),
                direction=binding_direction,
            )

        # Only query PT if the bridge is connected (dynamic validation)
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        query_fn = _query_pt_devices if bridge_ok else None
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None

        result = apply_acl_uc(
            plan=plan,
            binding=binding,
            query_pt_topology=query_fn,
            confirm_send=confirm_fn,
            dry_run=dry_run,
        )

        # Friendly summary
        summary_lines = []
        if result["valid"]:
            summary_lines.append(f"ACL '{plan.name_or_number}' valid ({len(plan.entries)} rules).")
        else:
            summary_lines.append(f"ACL '{plan.name_or_number}' has {len(result['errors'])} error(s).")

        summary_lines.extend(_apply_summary("ACL", plan.name_or_number, router, result, dry_run, bridge_ok))
        if result.get("applied") is True and binding:
            summary_lines.append(f"   Binding: {binding.interface} {binding.direction}")

        return json.dumps({
            "summary": "\n".join(summary_lines),
            "valid": result["valid"],
            "errors": result["errors"],
            "warnings": result["warnings"],
            "cli_lines": result["cli_lines"],
            "js_payload": result["js_payload"],
            "sent": result["sent"],
            "applied": result.get("applied"),
            "dry_run": result["dry_run"],
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_apply_acl_object(
        router: str,
        name_or_number: str,
        acl_type: str,
        entries: list[dict],
        binding_interface: str = "",
        binding_direction: str = "in",
        replace_existing: bool = True,
        dry_run: bool = False,
    ) -> str:
        """
        Apply an ACL using PT's object API (AclProcess.addAcl/addStatement)
        instead of CLI via configureIosDevice.

        Same input as pt_apply_acl. It is faster (no CLI parsing) and less
        prone to triggering modal popups that break the bridge if a line goes wrong.

        Limitation: the binding only works on physical catalog ports (e.g.
        GigabitEthernet0/0). For subinterfaces (G0/0/1.20) use pt_apply_acl (CLI),
        since port.setAclInID only applies to the base port and not the subinterface.

        Pipeline: validar plan → generar statements (sin prefijo "access-list NAME ")
        → ejecutar addAcl + addStatement uno por uno + binding opcional.
        """
        plan = build_acl_plan(router, name_or_number, acl_type, entries)
        binding = None
        if binding_interface:
            binding = ACLBinding(
                router=router,
                interface=binding_interface,
                acl_id=str(name_or_number),
                direction=binding_direction,
            )

        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()

        # Static + topological validation
        query_fn = _query_pt_devices if bridge_ok else None
        result = apply_acl_uc(
            plan=plan,
            binding=binding,
            query_pt_topology=query_fn,
            bridge_send=None,        # no enviamos por CLI — armamos JS propio
            dry_run=True,            # validar sin enviar
        )

        if not result["valid"]:
            return json.dumps({
                "summary": f"❌ ACL '{plan.name_or_number}' tiene {len(result['errors'])} error(es).",
                "valid": False,
                "errors": result["errors"],
                "warnings": result["warnings"],
                "sent": False,
                "dry_run": dry_run,
                "backend": "objects",
            }, indent=2, ensure_ascii=False)

        # Convert CLI lines to statements (without the "access-list NAME " prefix)
        cli_lines = generate_acl_cli(plan)
        prefix = f"access-list {plan.name_or_number} "
        statements = [ln[len(prefix):] for ln in cli_lines if ln.startswith(prefix)]

        # Construir JS para AclProcess.addAcl + addStatement
        name_js = json.dumps(str(plan.name_or_number))
        router_js = json.dumps(router)
        stmts_js = "[" + ",".join(json.dumps(s) for s in statements) + "]"

        js_lines = [
            f"var d=ipc.network().getDevice({router_js});",
            'if(!d){reportResult(JSON.stringify({success:false,error:"router not found"}));return;}',
            'var ap=d.getProcess("AclProcess");',
            'if(!ap){reportResult(JSON.stringify({success:false,error:"AclProcess not available"}));return;}',
        ]
        if replace_existing:
            js_lines.append(f"try{{ap.removeAcl({name_js});}}catch(e){{}}")
        js_lines.extend([
            f"ap.addAcl({name_js});",
            f"var acl=ap.getAcl({name_js});",
            'if(!acl){reportResult(JSON.stringify({success:false,error:"addAcl failed"}));return;}',
            f"var stmts={stmts_js};",
            'var added=0;for(var i=0;i<stmts.length;i++){if(acl.addStatement(stmts[i]))added++;}',
        ])

        bound = "none"
        if binding:
            iface_js = json.dumps(binding.interface)
            setter = "setAclInID" if binding.direction == "in" else "setAclOutID"
            js_lines.extend([
                f"var p=d.getPort({iface_js});",
                f'if(p){{p.{setter}({name_js});}}',
            ])
            bound = f"{binding.interface} {binding.direction}"

        js_lines.append(
            'reportResult(JSON.stringify({success:true,added:added,cmdCount:acl.getCommandCount()}));'
        )

        js = "(function(){" + "".join(js_lines) + "})()"

        payload = {
            "summary": "",
            "valid": True,
            "errors": [],
            "warnings": result["warnings"],
            "cli_lines": cli_lines,
            "statements": statements,
            "js_payload": js,
            "binding": bound,
            "sent": False,
            "dry_run": dry_run,
            "backend": "objects",
        }

        if dry_run:
            payload["summary"] = (
                f"[dry_run] ACL '{plan.name_or_number}' lista: "
                f"{len(statements)} statement(s) + binding={bound}. JS NO enviado."
            )
            return json.dumps(payload, indent=2, ensure_ascii=False)

        if not bridge_ok:
            payload["summary"] = "⚠ Bridge no conectado — payload generado pero NO enviado."
            return json.dumps(payload, indent=2, ensure_ascii=False)

        response = _bridge_send_and_wait(js, timeout=10.0)
        if response is None:
            payload["summary"] = "Sin respuesta de PT."
            return json.dumps(payload, indent=2, ensure_ascii=False)

        try:
            r = json.loads(response)
            if r.get("success"):
                payload["sent"] = True
                payload["added"] = r.get("added")
                payload["cmd_count"] = r.get("cmdCount")
                payload["summary"] = (
                    f"📤 ACL '{plan.name_or_number}' applied on '{router}' via AclProcess "
                    f"({r.get('added')}/{len(statements)} statements). Binding={bound}."
                )
            else:
                payload["summary"] = f"Error PT: {r.get('error', 'desconocido')}"
        except Exception:
            payload["summary"] = f"Respuesta inesperada: {response}"

        return json.dumps(payload, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_remove_acl_object(
        router: str,
        name_or_number: str,
        binding_interface: str = "",
        binding_direction: str = "in",
        dry_run: bool = False,
    ) -> str:
        """
        Remove an ACL using the object API (AclProcess.removeAcl + Port.setAclInID="").

        Alternative to pt_remove_acl (CLI). If binding_interface is specified,
        it first clears the port's AclInID/AclOutID and then removes the ACL.

        Parameters:
        - router: device name in PT
        - name_or_number: identifier of the ACL to remove
        - binding_interface: optional, interface where the binding was
        - binding_direction: "in" or "out" (only if binding_interface)
        - dry_run: si True, devuelve payload sin enviarlo
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()

        name_js = json.dumps(str(name_or_number))
        router_js = json.dumps(router)

        js_lines = [
            f"var d=ipc.network().getDevice({router_js});",
            'if(!d){reportResult(JSON.stringify({success:false,error:"router not found"}));return;}',
            'var ap=d.getProcess("AclProcess");',
            'if(!ap){reportResult(JSON.stringify({success:false,error:"AclProcess not available"}));return;}',
        ]

        bound_label = "none"
        if binding_interface:
            iface_js = json.dumps(binding_interface)
            setter = "setAclInID" if binding_direction == "in" else "setAclOutID"
            js_lines.extend([
                f"var p=d.getPort({iface_js});",
                f'if(p){{p.{setter}("");}}',
            ])
            bound_label = f"{binding_interface} {binding_direction}"

        js_lines.extend([
            f"var removed=ap.removeAcl({name_js});",
            'reportResult(JSON.stringify({success:true,removed:removed}));',
        ])

        js = "(function(){" + "".join(js_lines) + "})()"

        payload = {
            "summary": "",
            "router": router,
            "acl_id": str(name_or_number),
            "binding": bound_label,
            "js_payload": js,
            "sent": False,
            "dry_run": dry_run,
            "backend": "objects",
        }

        if dry_run:
            payload["summary"] = (
                f"[dry_run] payload generado para remover ACL '{name_or_number}' "
                f"en '{router}' (binding={bound_label}). NO enviado."
            )
            return json.dumps(payload, indent=2, ensure_ascii=False)

        if not bridge_ok:
            payload["summary"] = "⚠ Bridge no conectado — payload generado pero NO enviado."
            return json.dumps(payload, indent=2, ensure_ascii=False)

        response = _bridge_send_and_wait(js, timeout=10.0)
        if response is None:
            payload["summary"] = "Sin respuesta de PT."
            return json.dumps(payload, indent=2, ensure_ascii=False)

        try:
            r = json.loads(response)
            if r.get("success"):
                payload["sent"] = True
                payload["removed"] = r.get("removed")
                payload["summary"] = (
                    f"📤 ACL '{name_or_number}' removed on '{router}' via AclProcess "
                    f"(removed={r.get('removed')}, binding={bound_label})."
                )
            else:
                payload["summary"] = f"Error PT: {r.get('error', 'desconocido')}"
        except Exception:
            payload["summary"] = f"Respuesta inesperada: {response}"

        return json.dumps(payload, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_remove_acl(
        router: str,
        name_or_number: str,
        binding_interface: str = "",
        binding_direction: str = "in",
        acl_type: str = "extended",
        dry_run: bool = False,
    ) -> str:
        """
        Remove an ACL applied on a router.

        If binding_interface is specified, first removes the binding from the
        interface (no ip access-group ...) and then deletes the whole ACL
        (no access-list ...).

        Parameters:
        - router: device name in PT
        - name_or_number: identifier of the ACL to remove
        - binding_interface: optional, interface where it was applied
        - binding_direction: "in" or "out" (only if binding_interface)
        - dry_run: if True, returns the payload without sending it
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None

        result = remove_acl_uc(
            router=router,
            name_or_number=name_or_number,
            binding_interface=binding_interface,
            direction=binding_direction,
            acl_type=acl_type,
            confirm_send=confirm_fn,
            dry_run=dry_run,
        )

        summary = _apply_summary("ACL removal", name_or_number, router, result, dry_run, bridge_ok)

        return json.dumps({
            "summary": "\n".join(summary),
            "router": result["router"],
            "acl_id": result["acl_id"],
            "js_payload": result["js_payload"],
            "sent": result["sent"],
            "applied": result.get("applied"),
            "dry_run": result["dry_run"],
        }, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # NAT / PAT - apply and remove address translation via the bridge
    # ------------------------------------------------------------------

    @mcp.tool()
    def pt_apply_nat(
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
        dry_run: bool = False,
    ) -> str:
        """
        Apply NAT or PAT to a router in Packet Tracer's active topology.

        -- WHEN TO USE EACH MODE ----------------------------------------------

        mode="static"  - static NAT (1 to 1, permanent)
          Each private IP is ALWAYS mapped to the same public IP.
          Use when an internal server (web, FTP, mail) must be
          reachable from the Internet with a known fixed public IP.
          Requires: static_mappings = [{"inside_local": "...", "inside_global": "..."}]

        mode="dynamic" - dynamic NAT (pool of public IPs)
          The router assigns IPs from the pool on demand. When the host closes
          the session, the public IP returns to the pool for another host.
          Use when you have MORE public IPs than overload justifies but
          FEWER than simultaneous internal hosts, and per-IP tracking matters.
          Requires: inside_networks + pool_start/end/netmask

        mode="pat"     - PAT / NAT Overload (many to one with ports)
          Multiple internal hosts share ONE single public IP. The router
          differentiates the connections using unique port numbers.
          This is the mode used by almost all home and enterprise routers.
          Use when you have 1 public IP from the ISP and N internal hosts.
          Sub-modes:
            use_interface_overload=True  -> uses the IP of outside_interface directly
            use_interface_overload=False -> uses a pool (typically of 1 IP)
          Requires: inside_networks (+ pool if use_interface_overload=False)

        -- PARAMETERS ---------------------------------------------------------

        - router: device name in PT (e.g. "R1"). Call
          pt_query_topology if you do not know the exact name.
        - mode: "static" | "dynamic" | "pat"
        - inside_interface: interface connected to the private LAN (e.g. "GigabitEthernet0/0")
        - outside_interface: interface connected to the WAN/Internet (e.g. "GigabitEthernet0/1")
        - static_mappings: mode="static" only. List of dicts:
            [{"inside_local": "192.168.1.10", "inside_global": "200.1.1.5"}]
        - inside_networks: dynamic/pat modes. Internal networks to translate in
            "network wildcard" format (e.g. ["192.168.1.0 0.0.0.255"]).
            They are generated as an inline access-list.
        - acl_number: ACL number or name to identify inside hosts (default "1")
        - pool_name: NAT pool name (default "NAT-POOL")
        - pool_start / pool_end: first and last IP of the public pool
        - pool_netmask: pool mask (mask format, e.g. "255.255.255.0")
        - use_interface_overload: PAT only. If True, uses the IP of outside_interface
            instead of a pool. Typical when the ISP assigns 1 IP to the WAN.
        - dry_run: if True, validates and generates the payload without sending it to the bridge.

        PAT example with interface overload (most common case):
          pt_apply_nat(
              router="R1",
              mode="pat",
              inside_interface="GigabitEthernet0/0",
              outside_interface="GigabitEthernet0/1",
              inside_networks=["192.168.1.0 0.0.0.255"],
              use_interface_overload=True,
          )
        """
        config = build_nat_config(
            router=router,
            mode=mode,
            inside_interface=inside_interface,
            outside_interface=outside_interface,
            static_mappings=static_mappings,
            inside_networks=inside_networks,
            acl_number=acl_number,
            pool_name=pool_name,
            pool_start=pool_start,
            pool_end=pool_end,
            pool_netmask=pool_netmask,
            use_interface_overload=use_interface_overload,
        )

        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        query_fn = _query_pt_devices if bridge_ok else None
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None

        result = apply_nat_uc(
            config=config,
            query_pt_topology=query_fn,
            confirm_send=confirm_fn,
            dry_run=dry_run,
        )

        summary_lines = []
        mode_label = {"static": "Static NAT", "dynamic": "Dynamic NAT", "pat": "PAT/Overload"}.get(mode, mode)
        if result["valid"]:
            summary_lines.append(f"{mode_label} valid for router '{router}'.")
        else:
            summary_lines.append(f"{mode_label}: {len(result['errors'])} error(s).")

        summary_lines.extend(_apply_summary(mode_label, router, router, result, dry_run, bridge_ok))

        return json.dumps({
            "summary": "\n".join(summary_lines),
            "mode": mode,
            "valid": result["valid"],
            "errors": result["errors"],
            "warnings": result["warnings"],
            "cli_lines": result["cli_lines"],
            "js_payload": result["js_payload"],
            "sent": result["sent"],
            "applied": result.get("applied"),
            "dry_run": result["dry_run"],
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_remove_nat(
        router: str,
        mode: str,
        inside_interface: str,
        outside_interface: str,
        acl_number: str = "1",
        pool_name: str = "",
        static_mappings: list[dict] | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Remove the NAT/PAT configuration from a router.

        Removes the ip nat inside/outside marks from the interfaces and deletes
        the associated translations, pool and access-list.

        Parameters:
        - router: device name in PT
        - mode: "static" | "dynamic" | "pat"
        - inside_interface: interface marked as ip nat inside
        - outside_interface: interface marked as ip nat outside
        - acl_number: number/name of the access-list used (default "1")
        - pool_name: name of the NAT pool to remove (dynamic/pat with pool only)
        - static_mappings: mode="static" only. List of dicts with inside_local/inside_global
            to generate the "no ip nat inside source static ..." commands
        - dry_run: if True, returns the payload without sending it
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None

        result = remove_nat_uc(
            router=router,
            mode=mode,
            inside_interface=inside_interface,
            outside_interface=outside_interface,
            acl_number=acl_number,
            pool_name=pool_name,
            static_mappings=static_mappings,
            confirm_send=confirm_fn,
            dry_run=dry_run,
        )

        summary = _apply_summary(f"NAT removal '{mode}'", router, router, result, dry_run, bridge_ok)
        summary.extend("[warning] " + w for w in result.get("warnings", []))

        return json.dumps({
            "summary": "\n".join(summary),
            "router": result["router"],
            "mode": result["mode"],
            "js_payload": result["js_payload"],
            "sent": result["sent"],
            "applied": result.get("applied"),
            "warnings": result.get("warnings", []),
            "dry_run": result["dry_run"],
        }, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # SWITCHING / ROUTING FEATURES (apply to existing devices via bridge)
    # ------------------------------------------------------------------

    def _model_of(device_name: str) -> str:
        for d in (_query_pt_devices() or []):
            if d.get("name") == device_name:
                return d.get("model", "") or ""
        return ""

    def _needs_trunk_encapsulation(model: str) -> bool:
        # 3560/3650 multilayer switches require 'switchport trunk encapsulation
        # dot1q'; 2960 is dot1q-only and rejects it.
        return any(m in (model or "") for m in ("3560", "3650"))

    def _feature_response(label: str, ident: str, device: str, result: dict, dry_run: bool, bridge_ok: bool) -> str:
        summary = _apply_summary(label, ident, device, result, dry_run, bridge_ok)
        return json.dumps({
            "summary": "\n".join(summary),
            "cli_lines": result.get("cli_lines"),
            "js_payload": result.get("js_payload"),
            "sent": result.get("sent"),
            "applied": result.get("applied"),
            "dry_run": result.get("dry_run"),
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_apply_svi(
        switch: str,
        vlans: list[dict],
        enable_routing: bool = True,
        dry_run: bool = False,
    ) -> str:
        """
        Configure inter-VLAN routing on a multilayer (L3) switch using SVIs.

        The modern alternative to router-on-a-stick: instead of a router with
        dot1Q subinterfaces, a 3560/3650 switch routes between VLANs with
        switched virtual interfaces. Requires a multilayer switch
        (e.g. 3560-24PS or 3650-24PS); a 2960 is L2-only and will reject
        'ip routing'.

        Parameters:
        - switch: device name in PT (e.g. "CORE-SW"). Use pt_query_topology.
        - vlans: list of dicts, one per routed VLAN:
            {"vlan_id": 10, "ip": "192.168.10.1", "mask": "255.255.255.0",
             "name": "DATA" (optional)}
          The ip is the SVI address = the default gateway for that VLAN.
        - enable_routing: emit 'ip routing' (default True).
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_svi_uc(switch, vlans, enable_routing=enable_routing,
                                  confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid SVI input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("SVI inter-VLAN routing", switch, switch, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_configure_etherchannel(
        device_a: str,
        ports_a: list[str],
        device_b: str,
        ports_b: list[str],
        channel_id: int,
        mode: str = "active",
        layer: str = "l2",
        trunk: bool = True,
        allowed_vlans: list[int] | None = None,
        access_vlan: int | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Bundle parallel links between two devices into an EtherChannel.

        Configures BOTH ends. The member ports get 'channel-group <id> mode
        <mode>' and the logical 'interface Port-channel<id>' gets the L2/L3
        config. 'switchport trunk encapsulation dot1q' is added automatically
        for 3560/3650 switches and omitted for 2960.

        Parameters:
        - device_a / device_b: the two devices (use pt_query_topology).
        - ports_a / ports_b: matching member interfaces on each end, e.g.
            ["GigabitEthernet0/1", "GigabitEthernet0/2"].
        - channel_id: port-channel number (1-48).
        - mode: "active"/"passive" (LACP), "desirable"/"auto" (PAgP), "on" (static).
          Both ends must be compatible (active+active/passive, on+on, etc.).
        - layer: "l2" (switchport) or "l3" ('no switchport', add IP separately).
        - trunk: for l2, True = trunk, False = access.
        - allowed_vlans: l2 trunk only, e.g. [10, 20].
        - access_vlan: l2 access only.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = configure_etherchannel_uc(
                device_a, ports_a, device_b, ports_b, channel_id, mode=mode, layer=layer,
                trunk=trunk, allowed_vlans=allowed_vlans, access_vlan=access_vlan,
                needs_encap_a=_needs_trunk_encapsulation(_model_of(device_a)) if bridge_ok else False,
                needs_encap_b=_needs_trunk_encapsulation(_model_of(device_b)) if bridge_ok else False,
                confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid EtherChannel input: {exc}"}, indent=2, ensure_ascii=False)
        summary = _apply_summary(f"EtherChannel Po{channel_id}", f"{device_a}<->{device_b}", device_a, result, dry_run, bridge_ok)
        return json.dumps({
            "summary": "\n".join(summary),
            "device_a": result["device_a"],
            "device_b": result["device_b"],
            "applied": result.get("applied"),
            "dry_run": result.get("dry_run"),
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_apply_port_security(
        switch: str,
        interface: str,
        max_mac: int = 1,
        sticky: bool = True,
        violation: str = "shutdown",
        dry_run: bool = False,
    ) -> str:
        """
        Enable switchport port-security on an access port.

        Parameters:
        - switch: device name in PT.
        - interface: access port, e.g. "FastEthernet0/1".
        - max_mac: max secure MAC addresses (default 1).
        - sticky: learn addresses with 'mac-address sticky' (default True).
        - violation: "shutdown" (err-disable), "restrict" (drop + log) or
          "protect" (drop silently). Default "shutdown".
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_port_security_uc(switch, interface, max_mac=max_mac, sticky=sticky,
                                            violation=violation, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid port-security input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("port-security", f"{switch}:{interface}", switch, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_hsrp(
        router: str,
        interface: str,
        group: int,
        virtual_ip: str,
        priority: int = 100,
        preempt: bool = True,
        version: int = 2,
        dry_run: bool = False,
    ) -> str:
        """
        Configure HSRP (first-hop redundancy) on a router/L3 interface.

        Configure HSRP on BOTH routers of the pair (same group + virtual_ip);
        give the intended active router a higher priority (e.g. 110 vs 100).

        Parameters:
        - router: device name in PT.
        - interface: the interface facing the LAN, e.g. "GigabitEthernet0/0".
        - group: HSRP group number (0-255 for v1, 0-4095 for v2).
        - virtual_ip: the virtual gateway IP shared by the pair (the hosts'
          default gateway).
        - priority: 1-255, higher wins active (default 100).
        - preempt: reclaim active when priority is higher (default True).
        - version: HSRP version 1 or 2 (default 2).
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_hsrp_uc(router, interface, group, virtual_ip, priority=priority,
                                   preempt=preempt, version=version, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid HSRP input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response(f"HSRP group {group}", f"{router}:{interface}", router, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_add_static_route(
        router: str,
        destination: str,
        mask: str,
        next_hop: str,
        admin_distance: int = 1,
        dry_run: bool = False,
    ) -> str:
        """
        Add a static route (or a default route) to a router.

        For a DEFAULT route toward the WAN/Internet, use destination "0.0.0.0"
        and mask "0.0.0.0" (gateway of last resort).

        Parameters:
        - router: device name in PT.
        - destination: network address, e.g. "192.168.5.0" (or "0.0.0.0").
        - mask: subnet mask, e.g. "255.255.255.0" (or "0.0.0.0").
        - next_hop: next-hop IP, e.g. "10.0.0.2".
        - admin_distance: AD (default 1). Use a higher value (e.g. 254) for a
          floating/backup route.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        route = {"destination": destination, "mask": mask, "next_hop": next_hop, "admin_distance": admin_distance}
        try:
            result = add_static_routes_uc(router, [route], confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid static-route input: {exc}"}, indent=2, ensure_ascii=False)
        kind = "default route" if destination == "0.0.0.0" and mask == "0.0.0.0" else f"static route {destination}/{mask}"
        return _feature_response(kind, router, router, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_dhcp_relay(
        device: str,
        interface: str,
        helper_addresses: list[str],
        dry_run: bool = False,
    ) -> str:
        """
        Configure DHCP relay (ip helper-address) on an interface.

        Use when DHCP clients are on a different segment than the DHCP server:
        the router forwards their broadcasts to the server unicast.

        Parameters:
        - device: router/L3 device name in PT.
        - interface: the interface facing the DHCP CLIENTS (e.g. the LAN SVI or
          subinterface), NOT the one facing the server.
        - helper_addresses: one or more DHCP server IPs, e.g. ["192.168.0.10"].
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_dhcp_relay_uc(device, interface, helper_addresses,
                                         confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid DHCP-relay input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("DHCP relay", f"{device}:{interface}", device, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_ipv6(
        device: str,
        interfaces: list[dict],
        enable_routing: bool = True,
        ospfv3: dict | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Apply IPv6 addressing (dual-stack) and optional OSPFv3 to a device.

        IPv6 coexists with any existing IPv4 (dual-stack).

        Parameters:
        - device: device name in PT.
        - interfaces: list of dicts, one per interface:
            {"interface": "GigabitEthernet0/0",
             "ipv6": "2001:db8:1::1/64",
             "ospf_area": 0 (optional - only if you pass ospfv3)}
        - enable_routing: emit 'ipv6 unicast-routing' (default True; needed on
          routers/L3 switches that route IPv6).
        - ospfv3: optional dict to enable OSPFv3:
            {"process_id": 1, "router_id": "1.1.1.1" (optional)}
          Interfaces that include "ospf_area" get 'ipv6 ospf <pid> area <area>'.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_ipv6_uc(device, interfaces, enable_routing=enable_routing,
                                   ospfv3=ospfv3, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid IPv6 input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("IPv6 dual-stack", device, device, result, dry_run, bridge_ok)

    # ------------------------------------------------------------------
    # UNIVERSAL ESCAPE HATCH + END DEVICES
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_apply_ios(
        device: str,
        config_lines: list[str],
        dry_run: bool = False,
    ) -> str:
        """
        Apply ARBITRARY Cisco IOS configuration to any router or switch.

        The universal tool: anything you can type at a Cisco CLI in global
        config mode is reachable here, even features without a dedicated tool
        (QoS, route-maps, prefix-lists, zone-based firewall, IP SLA, etc.).
        The lines are wrapped with enable / configure terminal / ... / end /
        write memory automatically, sent through the bridge, and the result is
        confirmed (applied=true means PT accepted it).

        Parameters:
        - device: device name in PT (use pt_query_topology).
        - config_lines: IOS commands WITHOUT the enable/conf t/end wrapper.
          Use a single leading space for sub-mode commands and " exit" to leave
          a block, e.g.:
            ["interface GigabitEthernet0/0",
             " ip address 10.0.0.1 255.255.255.0",
             " no shutdown",
             " exit"]
        - dry_run: validate + return the wrapped CLI without sending.

        Prefer a dedicated tool (pt_apply_ospf, pt_apply_device_security, ...)
        when one exists - it validates input. Use this for everything else.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_raw_ios_uc(device, config_lines, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid IOS input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("IOS config", f"{len(result['cli_lines'])} lines", device, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_configure_pc(
        device: str,
        ip: str | None = None,
        mask: str | None = None,
        gateway: str | None = None,
        dns: str | None = None,
        dhcp: bool | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Configure an end device (PC / Laptop / Server) FastEthernet0 interface.

        Sets a static IPv4 address (or turns DHCP on/off) plus the default
        gateway and DNS server - the IP Configuration panel you would normally
        fill in by hand in PT. Applied through the GUI object model (not IOS),
        and confirmed.

        Parameters:
        - device: end-device name in PT (use pt_query_topology).
        - ip / mask: static IPv4 address + dotted-decimal mask. Provide BOTH.
        - gateway: default gateway IP (optional).
        - dns: DNS server IP (optional).
        - dhcp: True = enable DHCP, False = disable (static). When True you
          normally omit ip/mask.
        - dry_run: build the call without sending.

        Provide at least dhcp=True, or both ip and mask.
        """
        if dhcp is not True and not (ip and mask):
            return json.dumps(
                {"error": "Provide dhcp=True, or both ip and mask."}, indent=2, ensure_ascii=False)

        parts = [f"var d = ipc.network().getDevice({json.dumps(device)});"]
        parts.append('if(!d){reportResult(JSON.stringify({ok:false,error:"no device"}));}else{')
        parts.append('var p=d.getPort("FastEthernet0");')
        parts.append('if(!p){reportResult(JSON.stringify({ok:false,error:"no port"}));}else{')
        if dhcp is not None:
            parts.append(
                f'if(typeof d.setDhcpFlag==="function"){{d.setDhcpFlag({"true" if dhcp else "false"});}}')
        if ip and mask:
            parts.append(f'p.setIpSubnetMask({json.dumps(ip)},{json.dumps(mask)});')
        if gateway:
            parts.append(f'p.setDefaultGateway({json.dumps(gateway)});')
        if dns:
            parts.append(f'p.setDnsServerIp({json.dumps(dns)});')
        parts.append('reportResult(JSON.stringify({ok:true}));}}')
        js = "".join(parts)

        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        sent = False
        applied: bool | None = None
        if bridge_ok and not dry_run:
            res = _bridge_send_and_wait(js, timeout=8.0)
            sent = res is not None
            applied = parse_ok(res)
        setting = "DHCP" if dhcp else (ip or "static")
        summary = _apply_summary("PC IP config", setting, device,
                                 {"applied": applied, "sent": sent}, dry_run, bridge_ok)
        return json.dumps({
            "summary": "\n".join(summary),
            "js_payload": js,
            "sent": sent,
            "applied": applied,
            "dry_run": dry_run,
        }, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # ROUTING PROTOCOLS (apply to an existing device)
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_apply_ospf(
        router: str,
        process_id: int,
        networks: list[dict],
        router_id: str | None = None,
        passive_interfaces: list[str] | None = None,
        default_originate: bool = False,
        dry_run: bool = False,
    ) -> str:
        """
        Enable OSPF on an existing router (single or multi-area).

        Parameters:
        - router: device name in PT.
        - process_id: OSPF process id (1-65535).
        - networks: list of dicts, one per advertised network:
            {"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0}
          (use wildcard masks, not subnet masks). Different "area" values give
          you a multi-area design.
        - router_id: optional explicit router-id (e.g. "1.1.1.1").
        - passive_interfaces: interfaces that should not form adjacencies
            (e.g. ["GigabitEthernet0/1"]).
        - default_originate: inject a default route into OSPF.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_ospf_uc(router, process_id, networks, router_id=router_id,
                                   passive_interfaces=passive_interfaces,
                                   default_originate=default_originate,
                                   confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid OSPF input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("OSPF", f"process {process_id}", router, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_rip(
        router: str,
        networks: list[str],
        version: int = 2,
        no_auto_summary: bool = True,
        passive_interfaces: list[str] | None = None,
        default_originate: bool = False,
        dry_run: bool = False,
    ) -> str:
        """
        Enable RIP (default RIPv2) on an existing router.

        Parameters:
        - router: device name in PT.
        - networks: list of classful network strings, e.g. ["10.0.0.0", "192.168.1.0"].
        - version: 1 or 2 (default 2).
        - no_auto_summary: disable classful auto-summarization (default True; the
          usual RIPv2 best practice).
        - passive_interfaces / default_originate: optional, as in OSPF.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_rip_uc(router, networks, version=version,
                                  no_auto_summary=no_auto_summary,
                                  passive_interfaces=passive_interfaces,
                                  default_originate=default_originate,
                                  confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid RIP input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("RIP", f"v{version}", router, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_eigrp(
        router: str,
        as_number: int,
        networks: list,
        no_auto_summary: bool = True,
        router_id: str | None = None,
        passive_interfaces: list[str] | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Enable EIGRP on an existing router.

        Parameters:
        - router: device name in PT.
        - as_number: EIGRP autonomous-system number (1-65535) - must match on
          all neighbors.
        - networks: each item is EITHER a classful string ("10.0.0.0") OR a dict
          with a wildcard {"network": "10.0.0.0", "wildcard": "0.0.0.255"}.
        - no_auto_summary: disable auto-summarization (default True).
        - router_id: optional explicit EIGRP router-id.
        - passive_interfaces: optional.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_eigrp_uc(router, as_number, networks, no_auto_summary=no_auto_summary,
                                    router_id=router_id, passive_interfaces=passive_interfaces,
                                    confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid EIGRP input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("EIGRP", f"AS {as_number}", router, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_bgp(
        router: str,
        as_number: int,
        router_id: str | None = None,
        neighbors: list[dict] | None = None,
        networks: list[dict] | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Enable BGP on an existing router.

        Parameters:
        - router: device name in PT.
        - as_number: local BGP AS (1-65535).
        - router_id: optional explicit BGP router-id.
        - neighbors: list of dicts:
            {"ip": "10.0.0.2", "remote_as": 65002, "description": "ISP" (optional)}
        - networks: list of dicts advertised with the mask keyword:
            {"network": "192.168.1.0", "mask": "255.255.255.0"}
        - dry_run: validate + return the CLI without sending.

        Provide at least one neighbor or one network.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_bgp_uc(router, as_number, router_id=router_id,
                                  neighbors=neighbors, networks=networks,
                                  confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid BGP input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("BGP", f"AS {as_number}", router, result, dry_run, bridge_ok)

    # ------------------------------------------------------------------
    # DEVICE MANAGEMENT / HARDENING
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_apply_device_security(
        device: str,
        hostname: str | None = None,
        enable_secret: str | None = None,
        console_password: str | None = None,
        vty_password: str | None = None,
        ssh: dict | None = None,
        banner_motd: str | None = None,
        service_password_encryption: bool = False,
        domain_name: str | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Harden a device: passwords, SSH, banner, enable secret.

        Parameters (all optional, but provide at least one):
        - hostname: set the device hostname.
        - enable_secret: privileged-EXEC secret.
        - console_password: password on line console 0 (+ login).
        - vty_password: password on the vty lines (+ login). Ignored if `ssh`
          is given (SSH configures the vty lines for login local instead).
        - ssh: enable SSH. Dict:
            {"domain": "lab.local", "username": "admin", "password": "cisco",
             "version": 2 (optional), "modulus": 1024 (optional)}
          Emits ip domain-name, username, crypto key generate rsa, ip ssh
          version, and 'line vty 0 15 / transport input ssh / login local'.
        - banner_motd: message-of-the-day banner text.
        - service_password_encryption: scramble plaintext passwords.
        - domain_name: ip domain-name (when not already set via ssh).
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_device_security_uc(
                device, hostname=hostname, enable_secret=enable_secret,
                console_password=console_password, vty_password=vty_password, ssh=ssh,
                banner_motd=banner_motd, service_password_encryption=service_password_encryption,
                domain_name=domain_name, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid device-security input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("Device hardening", device, device, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_management(
        device: str,
        ntp_servers: list[str] | None = None,
        snmp: dict | None = None,
        logging_hosts: list[str] | None = None,
        clock_timezone: dict | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Configure management services: NTP, SNMP, syslog, clock timezone.

        Parameters (provide at least one):
        - ntp_servers: list of NTP server IPs.
        - snmp: dict {"community": "public", "access": "ro"|"rw",
                       "location": "...", "contact": "..."}.
        - logging_hosts: syslog server IPs (ip logging host ...).
        - clock_timezone: {"name": "PST", "offset": -8}.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_management_uc(device, ntp_servers=ntp_servers, snmp=snmp,
                                         logging_hosts=logging_hosts, clock_timezone=clock_timezone,
                                         confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid management input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("Management services", device, device, result, dry_run, bridge_ok)

    # ------------------------------------------------------------------
    # SWITCHING: STP / VTP / VLANs
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_apply_stp(
        switch: str,
        mode: str | None = None,
        vlan_root: list[dict] | None = None,
        portfast_interfaces: list[str] | None = None,
        bpduguard_interfaces: list[str] | None = None,
        portfast_default: bool = False,
        bpduguard_default: bool = False,
        dry_run: bool = False,
    ) -> str:
        """
        Configure Spanning Tree Protocol on a switch.

        Parameters (provide at least one):
        - mode: "pvst" or "rapid-pvst".
        - vlan_root: list of dicts to set the root bridge / priority per VLAN:
            {"vlan": 10, "role": "primary"|"secondary"} or
            {"vlan": 10, "priority": 4096}  (priority must be a multiple of 4096).
        - portfast_interfaces: access ports to put into PortFast.
        - bpduguard_interfaces: ports to protect with BPDU Guard.
        - portfast_default: enable PortFast on all access ports globally.
        - bpduguard_default: enable BPDU Guard on all PortFast ports globally.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_stp_uc(switch, mode=mode, vlan_root=vlan_root,
                                  portfast_interfaces=portfast_interfaces,
                                  bpduguard_interfaces=bpduguard_interfaces,
                                  portfast_default=portfast_default,
                                  bpduguard_default=bpduguard_default,
                                  confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid STP input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("Spanning Tree", switch, switch, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_vtp(
        switch: str,
        mode: str,
        domain: str | None = None,
        password: str | None = None,
        version: int | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Configure VTP (VLAN Trunking Protocol) on a switch.

        Parameters:
        - switch: device name in PT.
        - mode: "server", "client", "transparent" or "off".
        - domain: VTP domain name (must match across the VTP domain).
        - password: optional VTP password.
        - version: optional VTP version (1, 2 or 3).
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_vtp_uc(switch, mode, domain=domain, password=password,
                                  version=version, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid VTP input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("VTP", mode, switch, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_create_vlans(
        switch: str,
        vlans: list[dict],
        dry_run: bool = False,
    ) -> str:
        """
        Create VLANs in a switch's VLAN database (with optional names).

        Standalone VLAN creation - separate from SVIs/trunks. For inter-VLAN
        routing use pt_apply_svi; for trunk allowed-lists use
        pt_configure_etherchannel or pt_apply_ios.

        Parameters:
        - switch: device name in PT.
        - vlans: list of dicts {"vlan_id": 10, "name": "SALES" (optional)}.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = create_vlans_uc(switch, vlans, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid VLAN input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("VLAN database", f"{len(vlans)} vlans", switch, result, dry_run, bridge_ok)

    # ------------------------------------------------------------------
    # INTERFACES / WAN
    # ------------------------------------------------------------------
    @mcp.tool()
    def pt_configure_interface(
        device: str,
        interface: str,
        ip: str | None = None,
        mask: str | None = None,
        description: str | None = None,
        shutdown: bool | None = None,
        speed: str | None = None,
        duplex: str | None = None,
        mtu: int | None = None,
        no_switchport: bool = False,
        dry_run: bool = False,
    ) -> str:
        """
        Configure a generic interface: IP, description, admin state, speed.

        Works on any router/switch interface. For SVIs use pt_apply_svi, for
        EtherChannel use pt_configure_etherchannel, for serial/WAN use
        pt_configure_serial.

        Parameters:
        - device / interface: e.g. "R1" / "GigabitEthernet0/0".
        - ip + mask: provide BOTH to set an IPv4 address.
        - description: interface description text.
        - shutdown: True = shut, False = no shutdown, omit = leave as-is.
        - speed / duplex: e.g. "100" / "full".
        - mtu: interface MTU.
        - no_switchport: turn a switchport into a routed (L3) port first.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = configure_interface_uc(device, interface, ip=ip, mask=mask,
                                            description=description, shutdown=shutdown,
                                            speed=speed, duplex=duplex, mtu=mtu,
                                            no_switchport=no_switchport,
                                            confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid interface input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("Interface config", interface, device, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_loopback(
        device: str,
        number: int,
        ip: str,
        mask: str,
        description: str | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Create a Loopback interface with an IP address.

        Parameters:
        - device: router name in PT.
        - number: loopback number (e.g. 0 -> interface Loopback0).
        - ip + mask: the loopback address (often a /32, e.g. "1.1.1.1" /
          "255.255.255.255" for a router-id).
        - description: optional.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_loopback_uc(device, number, ip, mask, description=description,
                                       confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid loopback input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("Loopback", f"Loopback{number}", device, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_configure_serial(
        device: str,
        interface: str,
        encapsulation: str | None = None,
        clock_rate: int | None = None,
        ip: str | None = None,
        mask: str | None = None,
        ppp_auth: str | None = None,
        username: str | None = None,
        password: str | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Configure a serial / WAN interface (HDLC, PPP, Frame Relay).

        Parameters:
        - device / interface: e.g. "R1" / "Serial0/0/0".
        - encapsulation: "ppp", "hdlc" or "frame-relay".
        - clock_rate: DCE clock rate in bps (e.g. 64000) on the DCE end.
        - ip + mask: IPv4 address (provide both).
        - ppp_auth: "chap" or "pap" (PPP only).
        - username + password: the PEER's credentials for PPP authentication
          (emitted as a global 'username ... password ...').
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = configure_serial_uc(device, interface, encapsulation=encapsulation,
                                         clock_rate=clock_rate, ip=ip, mask=mask,
                                         ppp_auth=ppp_auth, username=username, password=password,
                                         confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid serial input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("Serial/WAN", interface, device, result, dry_run, bridge_ok)

    @mcp.tool()
    def pt_apply_gre_tunnel(
        device: str,
        tunnel_number: int,
        source: str,
        destination: str,
        ip: str,
        mask: str,
        description: str | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Create a GRE tunnel interface.

        Parameters:
        - device: router name in PT.
        - tunnel_number: e.g. 0 -> interface Tunnel0.
        - source: tunnel source (local interface name or IP).
        - destination: tunnel destination (the remote router's public IP).
        - ip + mask: the tunnel's overlay IP address.
        - description: optional.
        - dry_run: validate + return the CLI without sending.
        """
        bridge_ok = _ensure_bridge() and _bridge_pt_connected()
        if bridge_ok:
            _ensure_pt_patches()
        confirm_fn = _bridge_send_and_wait if bridge_ok and not dry_run else None
        try:
            result = apply_gre_tunnel_uc(device, tunnel_number, source, destination, ip, mask,
                                         description=description, confirm_send=confirm_fn, dry_run=dry_run)
        except (ValueError, KeyError, TypeError) as exc:
            return json.dumps({"error": f"Invalid GRE tunnel input: {exc}"}, indent=2, ensure_ascii=False)
        return _feature_response("GRE tunnel", f"Tunnel{tunnel_number}", device, result, dry_run, bridge_ok)

    # ------------------------------------------------------------------
    # CONSOLE / OBSERVABILITY: run exec commands, ping, save, wireless
    # ------------------------------------------------------------------
    def _run_device_exec(device: str, command: str, enable_password: str | None = None,
                         settle: float = 2.0, until: str | None = None,
                         max_wait: float = 14.0) -> dict:
        """Drive a device console via getCommandLine(): step past the initial
        config dialog, optionally enter enable mode, disable paging, run
        `command`, and return only the newly produced output.

        Returns {ok, output, prompt, error}. `until` lets the poller stop early
        once a marker (e.g. "Success rate") appears; otherwise it waits `settle`.
        """
        dev = json.dumps(device)
        clget = f'ipc.network().getDevice({dev}).getCommandLine()'
        # Guard: device exists and is CLI-capable (routers/switches; not PC/server).
        probe = _bridge_send_and_wait(
            f'var d=ipc.network().getDevice({dev}); '
            f'if(!d){{reportResult(JSON.stringify({{err:"no_device"}}));}} '
            f'else if(typeof d.getCommandLine!=="function"){{reportResult(JSON.stringify({{err:"no_cli"}}));}} '
            f'else{{reportResult(JSON.stringify({{ok:true}}));}}', timeout=8.0)
        if probe is None:
            return {"ok": False, "error": "bridge timeout reaching the device console"}
        try:
            pj = json.loads(probe)
        except Exception:
            pj = {}
        if pj.get("err") == "no_device":
            return {"ok": False, "error": f"device '{device}' not found"}
        if pj.get("err") == "no_cli":
            return {"ok": False, "error": f"device '{device}' has no IOS console (not a router/switch)"}

        def _cl(body: str, timeout: float = 8.0):
            return _bridge_send_and_wait(f'var cl={clget}; {body}', timeout=timeout)

        def _prompt() -> str:
            r = _cl('reportResult(JSON.stringify({p:cl.getPrompt()||""}));')
            try:
                return json.loads(r).get("p", "") if r else ""
            except Exception:
                return ""

        # 1. Normalize the console: wake it and clear any modal state until we are
        #    at a real exec prompt (ends with '>' or '#'). PT logs the console out
        #    when idle ("Press RETURN to get started"), so a plain Enter recovers.
        for _ in range(4):
            p = _prompt().strip()
            if p.endswith(">") or p.endswith("#"):
                break
            if "initial configuration" in p:
                _cl('cl.enterCommand("no"); reportResult("");')
            else:
                _cl('cl.enterCommand(""); reportResult("");')
            time.sleep(0.5)

        # 2. Enter enable mode ONLY when a password was supplied and we are not
        #    already privileged. Critically, feed the password only if PT actually
        #    prompts "Password:" - otherwise the password is typed at the exec
        #    prompt as a bogus command and hangs the console on a DNS lookup.
        if enable_password is not None and not _prompt().strip().endswith("#"):
            _cl('cl.enterCommand("enable"); reportResult("");')
            time.sleep(0.6)
            if "assword" in _prompt():
                _cl(f'cl.enterCommand({json.dumps(enable_password)}); reportResult("");')
                time.sleep(0.7)

        # 3. Baseline output length, then run the command.
        base_raw = _cl('reportResult(JSON.stringify({n:(cl.getOutput()||"").length}));')
        try:
            base = int(json.loads(base_raw)["n"])
        except Exception:
            base = 0
        _cl(f'cl.enterCommand({json.dumps(command)}); reportResult("");')

        # 4. Poll for output, paging through "--More--" (PT ignores
        #    'terminal length 0'). Long paged output (full 'show running-config')
        #    is unreliable because PT idle-resets the console between pages - we
        #    flag that. The command's real output often arrives a beat after the
        #    echo, so we must NOT stop on the first quiet tick: stop only when the
        #    exec prompt has returned (command finished), the `until` marker
        #    appears, or the deadline elapses - never just because two reads
        #    matched while the device was still working (which caused false ping
        #    failures and empty 'show' output).
        deadline = time.time() + max_wait
        start = time.time()
        out, prompt, last, paged = "", "", None, False
        while True:
            time.sleep(0.7)
            r = _cl('reportResult(JSON.stringify({o:cl.getOutput()||"", p:cl.getPrompt()}));', timeout=10.0)
            try:
                rj = json.loads(r)
                full = rj.get("o", "")
                out = full[base:] if len(full) >= base else full
                prompt = rj.get("p", "")
            except Exception:
                pass
            if out.rstrip().endswith("--More--"):
                paged = True
                _cl('cl.enterChar(" "); reportResult("");')   # advance one page
                if time.time() >= deadline:
                    break
                continue
            if until:
                # e.g. ping: keep polling until the marker appears or we time out;
                # a quiet interval before the result is NOT a reason to give up.
                if until in out or time.time() >= deadline:
                    break
                last = out
                continue
            if time.time() >= deadline:
                break
            # Non-until command: done when output stopped growing AND the device
            # returned to an exec prompt, after at least `settle` seconds (so
            # wait_seconds actually has an effect).
            prompt_back = prompt.strip().endswith((">", "#"))
            if out and out == last and prompt_back and (time.time() - start) >= settle:
                break
            last = out

        # 5. Strip --More-- / backspace artifacts and isolate the command's output.
        cleaned = re.sub(r'[ \t\x08]*--More--[ \t\x08]*', '', out).replace('\x08', '')
        ci = cleaned.rfind(command)
        if ci != -1:
            cleaned = cleaned[ci:]
        # If PT idle-reset the console mid-capture, everything from the reset
        # banner on is stale backlog (old commands' output) - cut it and flag
        # the result as truncated so it is never mistaken for the full output.
        for marker in ("con0 is now available", "Press RETURN to get started",
                       "% User Access Verification"):
            k = cleaned.find(marker)
            if k != -1:
                cleaned = cleaned[:k]
                paged = True
        return {"ok": True, "output": cleaned.strip("\r\n"), "prompt": prompt, "truncated": paged}

    @mcp.tool()
    def pt_run_command(
        device: str,
        command: str,
        enable_password: str | None = None,
        wait_seconds: float = 2.0,
    ) -> str:
        """
        Run an EXEC (non-config) IOS command on a router/switch and capture the
        terminal output.

        The universal observability tool: any show/ping/traceroute/debug command
        you would type at the device prompt, with the real text output returned.
        Pairs with pt_apply_ios (which configures) so the agent can both change
        and VERIFY device state. Best with TARGETED commands ('show ip route',
        'show ip ospf neighbor', 'show ip interface brief', 'show vlan brief') -
        very long output (full 'show running-config') may be truncated because PT
        idle-resets the console between '--More--' pages; that case sets
        truncated=true in the response.

        Parameters:
        - device: router/switch name in PT (use pt_query_topology). End devices
          (PC/server) have no IOS console - use pt_configure_pc / pt_ping there.
        - command: a single exec command, e.g. "show ip interface brief".
        - enable_password: if the device has an 'enable secret', pass it so the
          console can reach privileged mode. Most show/ping work in user mode
          without it.
        - wait_seconds: how long to let the command produce output (default 2).

        Returns the captured output plus the final prompt (and truncated=true if
        the output was paged and may be incomplete).
        """
        if not command or not command.strip():
            return json.dumps({"error": "command is required"}, indent=2, ensure_ascii=False)
        if not (_ensure_bridge() and _bridge_pt_connected()):
            return json.dumps({"error": "Bridge/PT not connected - cannot reach the device console."},
                              indent=2, ensure_ascii=False)
        _ensure_pt_patches()
        res = _run_device_exec(device, command.strip(), enable_password=enable_password,
                               settle=max(0.5, wait_seconds))
        if not res.get("ok"):
            return json.dumps({"error": res.get("error", "command failed")}, indent=2, ensure_ascii=False)
        payload = {
            "device": device, "command": command, "prompt": res.get("prompt"),
            "output": res.get("output"),
        }
        if res.get("truncated"):
            payload["truncated"] = True
            payload["note"] = ("Output was paged ('--More--') and PT idle-resets the console "
                               "between pages, so it may be incomplete. Prefer targeted commands "
                               "(e.g. 'show ip route', 'show ip ospf neighbor') over full "
                               "'show running-config' - or use pt_get_running_config.")
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_get_running_config(device: str) -> str:
        """
        Get the COMPLETE running-config of a router/switch as clean IOS text.

        The reliable way to read a full config: instead of paging
        'show running-config' through the console (which PT idle-resets on long
        output), this reads the device's saved model (serializeToXml) and
        extracts the embedded IOS configuration - always complete, never
        truncated, no enable password needed.

        Parameters:
        - device: router/switch name in PT (use pt_query_topology).

        Returns the running-config text (and its line count).
        """
        if not (_ensure_bridge() and _bridge_pt_connected()):
            return json.dumps({"error": "Bridge/PT not connected."}, indent=2, ensure_ascii=False)
        _ensure_pt_patches()
        dev = json.dumps(device)
        # Extract the <RUNNINGCONFIG> block and its <LINE> elements inside PT, so
        # only the config text (not the whole 25KB device XML) crosses the bridge.
        js = (
            f'var d=ipc.network().getDevice({dev}); '
            f'if(!d){{reportResult(JSON.stringify({{ok:false,error:"no device"}}));}} '
            f'else if(typeof d.serializeToXml!=="function"){{reportResult(JSON.stringify({{ok:false,error:"no config model"}}));}} '
            f'else{{var x=d.serializeToXml()||""; var s=x.indexOf("<RUNNINGCONFIG>"); var e=x.indexOf("</RUNNINGCONFIG>"); '
            f'if(s<0||e<0){{reportResult(JSON.stringify({{ok:false,error:"no running-config in model"}}));}} '
            f'else{{var block=x.substring(s+15,e); var parts=block.split("<LINE>"); var out=[]; '
            f'for(var i=0;i<parts.length;i++){{var j=parts[i].indexOf("</LINE>"); if(j>=0){{out.push(parts[i].substring(0,j));}}}} '
            f'reportResult(JSON.stringify({{ok:true, config: out.join("\\n")}}));}}}}')
        res = _bridge_send_and_wait(js, timeout=12.0)
        if res is None:
            return json.dumps({"error": "PT did not respond (timeout)."}, indent=2, ensure_ascii=False)
        try:
            obj = json.loads(res)
        except Exception:
            return json.dumps({"error": "Could not parse PT response."}, indent=2, ensure_ascii=False)
        if not obj.get("ok"):
            return json.dumps({"error": obj.get("error", "could not read config"),
                               "hint": "End devices (PC/server) have no IOS config; this is for routers/switches."},
                              indent=2, ensure_ascii=False)
        cfg = html.unescape(obj.get("config", "")).strip("\r\n")
        return json.dumps({
            "device": device,
            "line_count": cfg.count("\n") + 1 if cfg else 0,
            "running_config": cfg,
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_ping(
        device: str,
        target: str,
        count: int = 5,
        enable_password: str | None = None,
    ) -> str:
        """
        Ping from a router/switch and report reachability (success rate + RTT).

        Runs 'ping <target>' on the device console and parses the result, so you
        can verify end-to-end connectivity right after building/configuring.

        Parameters:
        - device: source router/switch name in PT.
        - target: destination IP (e.g. "1.1.1.1").
        - count: informational (PT sends 5 ICMP echoes by default).
        - enable_password: only if needed to reach the console (usually not).

        Returns success_rate (0-100), reachable (bool) and the raw ping output.
        For pings FROM a PC/server use the device's Desktop in PT; this tool
        targets IOS devices.
        """
        if not (_ensure_bridge() and _bridge_pt_connected()):
            return json.dumps({"error": "Bridge/PT not connected."}, indent=2, ensure_ascii=False)
        _ensure_pt_patches()
        res = _run_device_exec(device, f"ping {target}", enable_password=enable_password,
                               until="Success rate", max_wait=16.0)
        if not res.get("ok"):
            return json.dumps({"error": res.get("error", "ping failed")}, indent=2, ensure_ascii=False)
        out = res.get("output", "")
        rate = None
        rates = re.findall(r"Success rate is (\d+) percent", out)
        if rates:
            rate = int(rates[-1])
        return json.dumps({
            "device": device, "target": target,
            "success_rate": rate,
            "reachable": (rate is not None and rate > 0),
            "output": out,
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_save_project(path: str | None = None) -> str:
        """
        Save the current Packet Tracer project (.pkt).

        Parameters:
        - path: absolute path to save a copy (fileSaveAsNoPrompt). If omitted,
          saves the currently-open file in place (fileSave). A never-saved file
          REQUIRES a path (otherwise PT would pop a blocking Save-As dialog).

        Returns the saved filename reported by PT.
        """
        if not (_ensure_bridge() and _bridge_pt_connected()):
            return json.dumps({"error": "Bridge/PT not connected."}, indent=2, ensure_ascii=False)
        pre = _bridge_send_and_wait(
            'var f=ipc.appWindow().getActiveFile(); '
            'reportResult(JSON.stringify({n:(f&&f.getSavedFilename)?f.getSavedFilename():""}));', timeout=8.0)
        try:
            saved_name = json.loads(pre).get("n", "") if pre else ""
        except Exception:
            saved_name = ""
        if not path and not saved_name:
            return json.dumps(
                {"error": "This project was never saved; provide an absolute 'path' to save it."},
                indent=2, ensure_ascii=False)
        if path:
            # fileSaveAsNoPrompt(fileName, bAddToRecent) - the 2nd bool arg is
            # mandatory; a single-arg call throws "Invalid arguments". It writes
            # a copy to `path` without necessarily renaming the active file, so
            # report the requested path.
            js = (f'ipc.appWindow().fileSaveAsNoPrompt({json.dumps(path)}, true); '
                  f'reportResult(JSON.stringify({{saved:{json.dumps(path)}}}));')
        else:
            js = ('ipc.appWindow().fileSave(); var f=ipc.appWindow().getActiveFile(); '
                  'reportResult(JSON.stringify({saved:(f&&f.getSavedFilename)?f.getSavedFilename():""}));')
        res = _bridge_send_and_wait(js, timeout=20.0)
        if res is None:
            return json.dumps({"error": "Save sent but PT did not confirm (timeout)."}, indent=2, ensure_ascii=False)
        try:
            saved = json.loads(res).get("saved", "")
        except Exception:
            saved = ""
        return json.dumps({"saved": saved, "summary": f"Project saved: {saved or '(in place)'}"},
                          indent=2, ensure_ascii=False)

    @mcp.tool()
    def pt_configure_wireless(
        device: str,
        port_index: int = 0,
        channel: int | None = None,
        bandwidth: float | None = None,
        ssid: str | None = None,
    ) -> str:
        """
        Configure a wireless radio port on an Access Point / wireless device.

        Sets the RF channel and/or data-rate (bandwidth) on the radio port via
        the PT object model.

        Parameters:
        - device: AP / wireless device name in PT.
        - port_index: radio port index (default 0).
        - channel: RF channel number.
        - bandwidth: radio data rate (Mbps).
        - ssid: NOTE - PT does NOT expose SSID/authentication on the scripting
          API (no port setter exists), so an ssid value is reported as
          unsupported. Set SSID/security in the PT GUI (AP Config > Port).

        Returns what was applied and confirms via readback.
        """
        # ssid is not settable via the PT scripting API, so it can't satisfy the
        # "something actionable" requirement - require channel or bandwidth.
        if channel is None and bandwidth is None:
            return json.dumps(
                {"error": "Provide at least channel or bandwidth (ssid is not settable via the PT scripting API)."},
                indent=2, ensure_ascii=False)
        if not (_ensure_bridge() and _bridge_pt_connected()):
            return json.dumps({"error": "Bridge/PT not connected."}, indent=2, ensure_ascii=False)
        _ensure_pt_patches()
        dev = json.dumps(device)
        # Each setter flips `changed` only if it actually exists on the port, so
        # ok reflects a REAL mutation instead of being hard-coded true.
        sets = []
        if channel is not None:
            sets.append(f'if(typeof p.setChannel==="function"){{p.setChannel({int(channel)});changed=true;}}')
        if bandwidth is not None:
            sets.append(f'if(typeof p.setBandwidth==="function"){{p.setBandwidth({float(bandwidth)});changed=true;}}')
        # Auto-locate the radio port (isWirelessPort), falling back to port_index.
        js = (f'var d=ipc.network().getDevice({dev}); '
              f'if(!d){{reportResult(JSON.stringify({{ok:false,error:"no device"}}));}} '
              f'else{{var n=d.getPortCount(); var idx={int(port_index)}; '
              f'for(var i=0;i<n;i++){{var pp=d.getPortAt(i); '
              f'if(pp&&typeof pp.isWirelessPort==="function"&&pp.isWirelessPort()===true){{idx=i;break;}}}} '
              f'var p=d.getPortAt(idx); '
              f'if(!p){{reportResult(JSON.stringify({{ok:false,error:"no port"}}));}} '
              f'else{{var changed=false; {"".join(sets)} '
              f'reportResult(JSON.stringify({{ok:changed,port_index:idx,'
              f'wireless:(typeof p.isWirelessPort==="function")?p.isWirelessPort():null,'
              f'channel:(typeof p.getChannel==="function")?p.getChannel():null}}));}}}}')
        res = _bridge_send_and_wait(js, timeout=10.0)
        applied = parse_ok(res)
        chosen = port_index
        try:
            chosen = json.loads(res).get("port_index", port_index)
        except Exception:
            pass
        note = None
        if applied is False:
            note = ("The located port exposed no setChannel/setBandwidth setter, so nothing "
                    "was applied (this device/port may not be a configurable radio).")
        elif ssid:
            note = "ssid ignored: PT scripting API does not expose SSID/auth on wireless ports (set it in the GUI)."
        out = {"device": device, "port_index": chosen, "applied": applied,
               "readback": res, "note": note}
        return json.dumps(out, indent=2, ensure_ascii=False)
