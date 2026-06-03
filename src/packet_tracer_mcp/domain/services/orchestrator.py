"""
Main orchestrator.

Translates a TopologyRequest into a complete TopologyPlan with devices,
links, IPs, DHCP, and routes, all validated.
"""

from __future__ import annotations

from ..models.requests import TopologyRequest
from ..models.plans import (
    TopologyPlan, DevicePlan, LinkPlan, ValidationCheck, VLAN, Subinterface, DHCPPool,
)
from ..models.errors import ValidationResult
from .ip_planner import IPPlanner
from .validator import validate_plan
from ...infrastructure.catalog.devices import (
    resolve_model, get_ports_by_speed,
)
from ...infrastructure.catalog.cables import infer_cable
from ...shared.enums import PortSpeed, DeviceRole, TopologyTemplate
from ...shared.constants import (
    DEFAULT_ROUTER, DEFAULT_SWITCH, DEFAULT_DNS,
    LAYOUT_X_START, LAYOUT_Y_ROUTER, LAYOUT_Y_SWITCH, LAYOUT_Y_PC,
    LAYOUT_X_SPACING, LAYOUT_PC_X_SPACING, LAYOUT_CLOUD_X_OFFSET,
)


def plan_from_request(request: TopologyRequest) -> tuple[TopologyPlan, ValidationResult]:
    """
    Full pipeline. Returns (plan, validation_result).
    """
    plan = TopologyPlan()

    # Router-on-a-stick has its own builder (VLANs + subinterfaces + trunk +
    # inter-VLAN routing), which the generic chain does not model.
    if request.template == TopologyTemplate.ROUTER_ON_A_STICK:
        _build_router_on_a_stick(plan, request)
        result = validate_plan(plan)
        return plan, result

    pcs_list = _normalize_pcs(request)
    laptops_list = _normalize_laptops(request)

    _create_devices(plan, request, pcs_list, laptops_list)
    _create_links(plan, request, pcs_list, laptops_list)

    ip_planner = IPPlanner(
        lan_base=request.base_network,
        link_base=request.inter_router_network,
    )
    ip_planner.plan_addressing(
        plan,
        routing=request.routing,
        dhcp=request.dhcp,
        floating_routes=request.floating_routes,
        ospf_process_id=request.ospf_process_id,
        eigrp_as=request.eigrp_as,
    )

    _create_validations(plan)

    result = validate_plan(plan)
    return plan, result


_VLAN_NAMES = ("DATA", "SALES", "ENG", "VOICE", "GUEST", "MGMT", "IOT", "LAB")


def _build_router_on_a_stick(plan: TopologyPlan, req: TopologyRequest) -> None:
    """Build a router-on-a-stick: 1 router, 1 switch, N VLANs with PCs,
    an 802.1Q trunk and dot1Q subinterfaces for inter-VLAN routing.
    """
    router_model = req.router_model or DEFAULT_ROUTER
    switch_model = req.switch_model or DEFAULT_SWITCH
    r_model_obj = resolve_model(router_model)
    sw_model_obj = resolve_model(switch_model)

    # Number of VLANs (overridden by req.vlans, default 2, max 8)
    num_vlans = getattr(req, "vlans", 0) or 2
    num_vlans = max(2, min(num_vlans, 8))
    vlan_ids = [10 * (k + 1) for k in range(num_vlans)]  # 10, 20, 30...

    # Total number of PCs (at least 1 per VLAN)
    raw_pcs = req.pcs_per_lan
    total_pcs = raw_pcs if isinstance(raw_pcs, int) else (raw_pcs[0] if raw_pcs else 4)
    total_pcs = max(total_pcs, num_vlans)

    # --- Devices: router + switch ---
    plan.devices.append(DevicePlan(
        name="R1", model=router_model, category="router",
        role=DeviceRole.CORE_ROUTER, x=LAYOUT_X_START, y=LAYOUT_Y_ROUTER,
    ))
    plan.devices.append(DevicePlan(
        name="SW1", model=switch_model, category="switch",
        role=DeviceRole.ACCESS_SWITCH, x=LAYOUT_X_START, y=LAYOUT_Y_SWITCH,
    ))

    # Ports: router trunk (first gig) <-> switch trunk (first gig)
    r_gigs = [p.full_name for p in get_ports_by_speed(r_model_obj, PortSpeed.GIGABIT_ETHERNET)] if r_model_obj else []
    sw_gigs = [p.full_name for p in get_ports_by_speed(sw_model_obj, PortSpeed.GIGABIT_ETHERNET)] if sw_model_obj else []
    sw_fasts = [p.full_name for p in get_ports_by_speed(sw_model_obj, PortSpeed.FAST_ETHERNET)] if sw_model_obj else []
    r_trunk = r_gigs[0] if r_gigs else "GigabitEthernet0/0"
    sw_trunk = sw_gigs[0] if sw_gigs else "GigabitEthernet0/1"

    # Single trunk link router<->switch
    plan.links.append(LinkPlan(
        device_a="R1", port_a=r_trunk, device_b="SW1", port_b=sw_trunk,
        cable=infer_cable("router", "switch"), mode="trunk", trunk_allowed=list(vlan_ids),
    ))

    # Round-robin assignment of PCs to VLANs
    pcs_by_vlan: dict[int, int] = {vid: 0 for vid in vlan_ids}
    for p in range(total_pcs):
        pcs_by_vlan[vlan_ids[p % num_vlans]] += 1

    ip_planner = IPPlanner(lan_base=req.base_network, link_base=req.inter_router_network)
    fast_idx = 0
    pc_global = 0
    pc_x = LAYOUT_X_START - (total_pcs * LAYOUT_PC_X_SPACING // 2)

    for k, vid in enumerate(vlan_ids):
        subnet = ip_planner.next_lan_subnet()
        hosts = list(subnet.hosts())
        gw = str(hosts[0])
        mask = str(subnet.netmask)
        name = _VLAN_NAMES[k % len(_VLAN_NAMES)]

        plan.vlans.append(VLAN(switch="SW1", vlan_id=vid, name=name))
        plan.subinterfaces.append(Subinterface(
            router="R1", parent_port=r_trunk, vlan_id=vid, ip=gw, mask=mask,
        ))

        host_i = 1  # hosts[0] is the gateway (.1); hosts start at .2
        for _ in range(pcs_by_vlan[vid]):
            pc_global += 1
            pc_name = f"PC{pc_global}"
            pc_ip = str(hosts[host_i]); host_i += 1
            plan.devices.append(DevicePlan(
                name=pc_name, model="PC-PT", category="pc", role=DeviceRole.END_HOST,
                x=pc_x, y=LAYOUT_Y_PC,
                interfaces={"FastEthernet0": f"{pc_ip}/{subnet.prefixlen}"},
                gateway=gw,
            ))
            pc_x += LAYOUT_PC_X_SPACING
            sw_port = sw_fasts[fast_idx] if fast_idx < len(sw_fasts) else f"FastEthernet0/{fast_idx + 1}"
            fast_idx += 1
            plan.links.append(LinkPlan(
                device_a="SW1", port_a=sw_port, device_b=pc_name, port_b="FastEthernet0",
                cable=infer_cable("switch", "pc"), mode="access", access_vlan=vid,
            ))

        if req.dhcp:
            excl_end = str(hosts[min(9, len(hosts) - 1)])  # exclude .1-.10
            plan.dhcp_pools.append(DHCPPool(
                router="R1", pool_name=f"VLAN{vid}",
                network=str(subnet.network_address), mask=mask,
                gateway=gw, dns=DEFAULT_DNS,
                excluded_start=gw, excluded_end=excl_end,
            ))

    # Validation: inter-VLAN ping (first PC vs last PC -> different VLANs)
    pcs = plan.devices_by_category("pc")
    if len(pcs) >= 2:
        plan.validations.append(ValidationCheck(
            check_type="ping", from_device=pcs[0].name,
            to_target=pcs[-1].name, expected="Reply",
        ))


def _normalize_pcs(req: TopologyRequest) -> list[int]:
    if isinstance(req.pcs_per_lan, int):
        return [req.pcs_per_lan] * req.routers
    pcs = list(req.pcs_per_lan)
    while len(pcs) < req.routers:
        pcs.append(pcs[-1] if pcs else 3)
    return pcs


def _normalize_laptops(req: TopologyRequest) -> list[int]:
    if isinstance(req.laptops_per_lan, int):
        return [req.laptops_per_lan] * req.routers
    laptops = list(req.laptops_per_lan)
    while len(laptops) < req.routers:
        laptops.append(laptops[-1] if laptops else 0)
    return laptops


def _create_devices(plan: TopologyPlan, req: TopologyRequest, pcs_list: list[int], laptops_list: list[int]):
    router_model = req.router_model or DEFAULT_ROUTER
    switch_model = req.switch_model or DEFAULT_SWITCH

    # Routers
    for i in range(req.routers):
        role = DeviceRole.CORE_ROUTER if req.routers == 1 else (
            DeviceRole.EDGE_ROUTER if (i == 0 or i == req.routers - 1) else DeviceRole.CORE_ROUTER
        )
        plan.devices.append(DevicePlan(
            name=f"R{i + 1}", model=router_model, category="router",
            role=role,
            x=LAYOUT_X_START + i * LAYOUT_X_SPACING, y=LAYOUT_Y_ROUTER,
        ))

    # Switches + PCs + Laptops
    switch_idx = 0
    pc_idx = 0
    laptop_idx = 0
    for i in range(req.routers):
        for s in range(req.switches_per_router):
            switch_idx += 1
            plan.devices.append(DevicePlan(
                name=f"SW{switch_idx}", model=switch_model, category="switch",
                role=DeviceRole.ACCESS_SWITCH,
                x=LAYOUT_X_START + i * LAYOUT_X_SPACING + s * 120, y=LAYOUT_Y_SWITCH,
            ))
            if s == 0:
                n_pcs = pcs_list[i]
                for p in range(n_pcs):
                    pc_idx += 1
                    plan.devices.append(DevicePlan(
                        name=f"PC{pc_idx}", model="PC-PT", category="pc",
                        role=DeviceRole.END_HOST,
                        x=LAYOUT_X_START + i * LAYOUT_X_SPACING - (n_pcs * LAYOUT_PC_X_SPACING // 2) + p * LAYOUT_PC_X_SPACING,
                        y=LAYOUT_Y_PC,
                    ))
                n_laptops = laptops_list[i]
                for l in range(n_laptops):
                    laptop_idx += 1
                    plan.devices.append(DevicePlan(
                        name=f"LT{laptop_idx}", model="Laptop-PT", category="laptop",
                        role=DeviceRole.END_HOST,
                        x=LAYOUT_X_START + i * LAYOUT_X_SPACING - (n_laptops * LAYOUT_PC_X_SPACING // 2) + l * LAYOUT_PC_X_SPACING,
                        y=LAYOUT_Y_PC + 80,
                    ))

    # Access Points - one per primary switch of each router
    if req.access_points > 0:
        switches = plan.devices_by_category("switch")
        spr = req.switches_per_router
        ap_idx = 0
        for i in range(req.routers):
            if ap_idx >= req.access_points:
                break
            primary_sw = switches[i * spr] if i * spr < len(switches) else None
            if primary_sw:
                ap_idx += 1
                plan.devices.append(DevicePlan(
                    name=f"AP{ap_idx}", model="AccessPoint-PT", category="accesspoint",
                    role=DeviceRole.END_HOST,
                    x=primary_sw.x + 120,
                    y=LAYOUT_Y_SWITCH,
                ))

    # Servers
    for i in range(req.servers):
        plan.devices.append(DevicePlan(
            name=f"SRV{i + 1}", model="Server-PT", category="server",
            role=DeviceRole.SERVER_HOST,
            x=LAYOUT_X_START + (req.routers + 1) * LAYOUT_X_SPACING,
            y=LAYOUT_Y_PC + i * 80,
        ))

    # Cloud / WAN
    if req.has_wan:
        plan.devices.append(DevicePlan(
            name="WAN", model="Cloud-PT", category="cloud",
            role=DeviceRole.WAN_CLOUD,
            x=LAYOUT_X_START + req.routers * LAYOUT_X_SPACING + LAYOUT_CLOUD_X_OFFSET,
            y=LAYOUT_Y_ROUTER,
        ))


def _create_links(plan: TopologyPlan, req: TopologyRequest, pcs_list: list[int], laptops_list: list[int]):
    router_model_obj = resolve_model(req.router_model or DEFAULT_ROUTER)
    switch_model_obj = resolve_model(req.switch_model or DEFAULT_SWITCH)
    if not router_model_obj or not switch_model_obj:
        plan.errors.append("Invalid router or switch model")
        return

    routers = plan.devices_by_category("router")
    switches = plan.devices_by_category("switch")
    pcs = plan.devices_by_category("pc")
    laptops = plan.devices_by_category("laptop")
    aps = plan.devices_by_category("accesspoint")
    servers = plan.devices_by_category("server")
    cloud = next((d for d in plan.devices if d.category == "cloud"), None)

    used: dict[str, list[str]] = {d.name: [] for d in plan.devices}

    def _next_port(name: str, model: str, speed: str) -> str | None:
        m = resolve_model(model)
        if not m:
            return None
        for p in get_ports_by_speed(m, speed):
            if p.full_name not in used[name]:
                used[name].append(p.full_name)
                return p.full_name
        return None

    def _gig(name: str, model: str) -> str | None:
        return _next_port(name, model, PortSpeed.GIGABIT_ETHERNET)

    def _fast(name: str, model: str) -> str | None:
        return _next_port(name, model, PortSpeed.FAST_ETHERNET)

    # Router <-> Router (chain)
    for i in range(len(routers) - 1):
        r1, r2 = routers[i], routers[i + 1]
        p1, p2 = _gig(r1.name, r1.model), _gig(r2.name, r2.model)
        if p1 and p2:
            plan.links.append(LinkPlan(
                device_a=r1.name, port_a=p1,
                device_b=r2.name, port_b=p2,
                cable=infer_cable("router", "router"),
            ))

    # Router <-> Switch
    spr = req.switches_per_router
    for i, router in enumerate(routers):
        for sw in switches[i * spr:(i + 1) * spr]:
            rp, sp = _gig(router.name, router.model), _gig(sw.name, sw.model)
            if rp and sp:
                plan.links.append(LinkPlan(
                    device_a=router.name, port_a=rp,
                    device_b=sw.name, port_b=sp,
                    cable=infer_cable("router", "switch"),
                ))

    # Switch <-> PCs
    pc_idx = 0
    for i in range(req.routers):
        primary_sw = switches[i * spr] if i * spr < len(switches) else None
        if not primary_sw:
            continue
        for _ in range(pcs_list[i]):
            if pc_idx >= len(pcs):
                break
            pc = pcs[pc_idx]
            sp, pp = _fast(primary_sw.name, primary_sw.model), _fast(pc.name, pc.model)
            if sp and pp:
                plan.links.append(LinkPlan(
                    device_a=primary_sw.name, port_a=sp,
                    device_b=pc.name, port_b=pp,
                    cable=infer_cable("switch", "pc"),
                ))
            pc_idx += 1

    # Switch <-> Laptops
    laptop_idx = 0
    for i in range(req.routers):
        primary_sw = switches[i * spr] if i * spr < len(switches) else None
        if not primary_sw:
            continue
        for _ in range(laptops_list[i]):
            if laptop_idx >= len(laptops):
                break
            lt = laptops[laptop_idx]
            sp, lp = _fast(primary_sw.name, primary_sw.model), _fast(lt.name, lt.model)
            if sp and lp:
                plan.links.append(LinkPlan(
                    device_a=primary_sw.name, port_a=sp,
                    device_b=lt.name, port_b=lp,
                    cable=infer_cable("switch", "pc"),
                ))
            laptop_idx += 1

    # Switch <-> Access Points
    ap_idx = 0
    for i in range(req.routers):
        primary_sw = switches[i * spr] if i * spr < len(switches) else None
        if not primary_sw or ap_idx >= len(aps):
            continue
        ap = aps[ap_idx]
        sp, ap_port = _fast(primary_sw.name, primary_sw.model), _fast(ap.name, ap.model)
        if sp and ap_port:
            plan.links.append(LinkPlan(
                device_a=primary_sw.name, port_a=sp,
                device_b=ap.name, port_b=ap_port,
                cable=infer_cable("switch", "pc"),
            ))
        ap_idx += 1

    # Switch <-> Servers
    if servers and switches:
        sw = switches[0]
        for srv in servers:
            sp, srp = _fast(sw.name, sw.model), _fast(srv.name, srv.model)
            if sp and srp:
                plan.links.append(LinkPlan(
                    device_a=sw.name, port_a=sp,
                    device_b=srv.name, port_b=srp,
                    cable=infer_cable("switch", "server"),
                ))

    # Router <-> Cloud
    if cloud and routers:
        last = routers[-1]
        rp, cp = _gig(last.name, last.model), _fast(cloud.name, cloud.model)
        if rp and cp:
            plan.links.append(LinkPlan(
                device_a=last.name, port_a=rp,
                device_b=cloud.name, port_b=cp,
                cable=infer_cable("router", "cloud"),
            ))


def _create_validations(plan: TopologyPlan):
    pcs = plan.devices_by_category("pc")
    if len(pcs) >= 2:
        plan.validations.append(ValidationCheck(
            check_type="ping", from_device=pcs[0].name,
            to_target=pcs[-1].name, expected="Reply",
        ))
