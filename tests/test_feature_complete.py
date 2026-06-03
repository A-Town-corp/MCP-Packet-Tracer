"""Regression tests for the feature-complete pass.

Covers: named-ACL CLI, NAT None-pool guard, SUBNET_OVERLAP validation,
project name normalization, guarded plan parsing, ACL/NAT confirm path,
and first-class VLAN / router-on-a-stick support.
"""

from __future__ import annotations
import tempfile

import pytest

from packet_tracer_mcp.domain.models.acls import ACLPlan, ACLEntry
from packet_tracer_mcp.domain.models.nat import NATConfig
from packet_tracer_mcp.domain.models.plans import TopologyPlan, DevicePlan
from packet_tracer_mcp.domain.models.requests import TopologyRequest
from packet_tracer_mcp.domain.services.orchestrator import plan_from_request
from packet_tracer_mcp.domain.services.validator import validate_plan
from packet_tracer_mcp.shared.enums import TopologyTemplate
from packet_tracer_mcp.infrastructure.generator.acl_cli_generator import (
    generate_acl_cli, build_remove_payload,
)
from packet_tracer_mcp.infrastructure.generator.nat_cli_generator import generate_nat_body_cli
from packet_tracer_mcp.infrastructure.generator.cli_config_generator import generate_all_configs
from packet_tracer_mcp.infrastructure.generator.ptbuilder_generator import generate_executable_script
from packet_tracer_mcp.infrastructure.persistence.project_repository import ProjectRepository
from packet_tracer_mcp.application.use_cases.apply_acl import apply_acl_uc
from packet_tracer_mcp.application.use_cases.apply_nat import apply_nat_uc


# ---------------------------------------------------------------- ACL named syntax
class TestNamedACL:
    def test_named_acl_uses_ip_access_list_header(self):
        plan = ACLPlan(router="R1", name_or_number="BLOCK_HTTP", acl_type="extended", entries=[
            ACLEntry(action="deny", protocol="tcp", source="any", destination="any", dest_port_op="eq", dest_port=80),
            ACLEntry(action="permit", protocol="ip", source="any", destination="any"),
        ])
        lines = generate_acl_cli(plan)
        assert lines[0] == "ip access-list extended BLOCK_HTTP"
        assert lines[-1] == "exit"
        # entries are indented and have NO 'access-list NAME' prefix
        assert " deny tcp any any eq 80" in lines
        assert " permit ip any any" in lines
        assert not any(l.startswith("access-list BLOCK_HTTP") for l in lines)

    def test_named_acl_remove_uses_named_form(self):
        payload = build_remove_payload("R1", "BLOCK_HTTP", acl_type="standard")
        assert "no ip access-list standard BLOCK_HTTP" in payload
        assert "no access-list BLOCK_HTTP" not in payload

    def test_numbered_acl_unchanged(self):
        plan = ACLPlan(router="R1", name_or_number="101", acl_type="extended",
                       entries=[ACLEntry(action="permit", protocol="ip", source="any", destination="any")])
        lines = generate_acl_cli(plan)
        assert lines == ["access-list 101 permit ip any any"]
        assert "no access-list 101" in build_remove_payload("R1", "101")


# ---------------------------------------------------------------- NAT None-pool guard
class TestNATPoolGuard:
    def test_dynamic_without_pool_does_not_crash(self):
        cfg = NATConfig(router="R1", mode="dynamic", inside_interface="Gig0/0",
                        outside_interface="Gig0/1", inside_networks=["192.168.1.0 0.0.0.255"], pool=None)
        lines = generate_nat_body_cli(cfg)  # must not raise
        assert any("access-list" in l for l in lines)
        assert not any("ip nat pool" in l for l in lines)  # pool skipped, no crash

    def test_dynamic_without_pool_reports_error(self):
        cfg = NATConfig(router="R1", mode="dynamic", inside_interface="Gig0/0",
                        outside_interface="Gig0/1", inside_networks=["192.168.1.0 0.0.0.255"], pool=None)
        res = apply_nat_uc(cfg, dry_run=True)
        assert res["valid"] is False
        assert res["errors"]


# ---------------------------------------------------------------- SUBNET_OVERLAP
class TestSubnetOverlap:
    def test_overlapping_distinct_subnets_flagged(self):
        plan = TopologyPlan(devices=[
            DevicePlan(name="R1", model="2911", category="router", interfaces={"Gig0/0": "192.168.1.1/24"}),
            DevicePlan(name="R2", model="2911", category="router", interfaces={"Gig0/0": "192.168.1.10/25"}),
        ])
        codes = [e.code.value for e in validate_plan(plan).errors]
        assert "SUBNET_OVERLAP" in codes

    def test_same_lan_not_flagged(self):
        plan = TopologyPlan(devices=[
            DevicePlan(name="R1", model="2911", category="router", interfaces={"Gig0/0": "192.168.1.1/24"}),
            DevicePlan(name="PC1", model="PC-PT", category="pc", interfaces={"FastEthernet0": "192.168.1.2/24"}),
        ])
        codes = [e.code.value for e in validate_plan(plan).errors]
        assert "SUBNET_OVERLAP" not in codes


# ---------------------------------------------------------------- Project name round-trip
class TestProjectNames:
    def test_save_load_delete_with_spaces(self):
        with tempfile.TemporaryDirectory() as d:
            repo = ProjectRepository(base_dir=d)
            plan = TopologyPlan(name="My Lab", devices=[DevicePlan(name="R1", model="2911", category="router")])
            repo.save_plan(plan, "My Lab")
            loaded = repo.load_plan("My Lab")          # used to FileNotFoundError
            assert loaded.devices[0].name == "R1"
            assert repo.delete_project("My Lab") is True


# ---------------------------------------------------------------- ACL/NAT confirm path
class TestConfirmPath:
    def _acl(self):
        return ACLPlan(router="R1", name_or_number="101", acl_type="extended",
                       entries=[ACLEntry(action="permit", protocol="ip", source="any", destination="any")])

    def test_applied_true_when_pt_confirms(self):
        r = apply_acl_uc(self._acl(), confirm_send=lambda js: '{"ok": true}')
        assert r["applied"] is True and r["sent"] is True

    def test_applied_false_when_pt_rejects(self):
        r = apply_acl_uc(self._acl(), confirm_send=lambda js: '{"ok": false}')
        assert r["applied"] is False

    def test_applied_none_on_timeout(self):
        r = apply_acl_uc(self._acl(), confirm_send=lambda js: None)
        assert r["applied"] is None and r["sent"] is False


# ---------------------------------------------------------------- Router-on-a-stick / VLANs
class TestRouterOnAStick:
    def _plan(self, vlans=0, pcs=4, dhcp=False):
        return plan_from_request(TopologyRequest(
            template=TopologyTemplate.ROUTER_ON_A_STICK, dhcp=dhcp, pcs_per_lan=pcs, vlans=vlans))

    def test_default_two_vlans_and_subinterfaces(self):
        plan, res = self._plan()
        assert res.is_valid
        assert [v.vlan_id for v in plan.vlans] == [10, 20]
        assert {s.vlan_id for s in plan.subinterfaces} == {10, 20}
        # each subinterface on the same physical trunk parent
        assert {s.parent_port for s in plan.subinterfaces} == {"GigabitEthernet0/0"}

    def test_one_trunk_link_and_access_links(self):
        plan, _ = self._plan()
        trunks = [l for l in plan.links if l.mode == "trunk"]
        access = [l for l in plan.links if l.mode == "access"]
        assert len(trunks) == 1
        assert trunks[0].trunk_allowed == [10, 20]
        assert len(access) == 4
        assert {l.access_vlan for l in access} == {10, 20}

    def test_pcs_addressed_per_vlan(self):
        plan, _ = self._plan()
        pcs = [d for d in plan.devices if d.category == "pc"]
        # PC gateway must equal its VLAN subinterface IP
        sub_ips = {s.ip for s in plan.subinterfaces}
        for pc in pcs:
            assert pc.gateway in sub_ips
            host_ip = pc.interfaces["FastEthernet0"].split("/")[0]
            # host is in the same /24 as its gateway
            assert host_ip.rsplit(".", 1)[0] == pc.gateway.rsplit(".", 1)[0]

    def test_switch_cli_has_vlans_and_trunk(self):
        plan, _ = self._plan()
        sw = generate_all_configs(plan)["SW1"]
        assert "vlan 10" in sw and "vlan 20" in sw
        assert "switchport mode trunk" in sw
        assert "switchport access vlan 10" in sw
        assert "switchport access vlan 20" in sw
        # 2960 is dot1q-only: must NOT emit encapsulation command
        assert "switchport trunk encapsulation" not in sw

    def test_router_cli_has_subinterfaces_with_exit(self):
        plan, _ = self._plan()
        r = generate_all_configs(plan)["R1"]
        assert "interface GigabitEthernet0/0.10" in r
        assert "encapsulation dot1Q 10" in r
        assert "ip address 192.168.0.1 255.255.255.0" in r
        # physical trunk port brought up with NO ip
        assert "interface GigabitEthernet0/0\n no ip address\n no shutdown" in r
        # exit between subinterface blocks (critical - else subifs collapse)
        assert r.count(" exit") >= 3

    def test_executable_script_links_have_cable_and_vlan_config(self):
        plan, _ = self._plan()
        script = generate_executable_script(plan)
        # every addLink carries the required 5th cable arg
        for line in script.splitlines():
            if line.startswith("addLink("):
                assert line.rstrip(";").rstrip(")").endswith('"straight"')
        assert "switchport access vlan" in script
        assert "encapsulation dot1Q" in script

    def test_vlans_override(self):
        plan, res = self._plan(vlans=3, pcs=6)
        assert res.is_valid
        assert [v.vlan_id for v in plan.vlans] == [10, 20, 30]

    def test_dhcp_pools_per_vlan(self):
        plan, _ = self._plan(dhcp=True)
        assert len(plan.dhcp_pools) == 2
        gws = {p.gateway for p in plan.dhcp_pools}
        sub_ips = {s.ip for s in plan.subinterfaces}
        assert gws == sub_ips


# ---------------------------------------------------------------- port capacity / DHCP exclude
class TestPortCapacityAndDHCP:
    def test_insufficient_ports_flagged(self):
        # 1941 has 2 GigE ports; give it 3 router-router links -> over capacity
        from packet_tracer_mcp.domain.models.plans import LinkPlan
        devs = [DevicePlan(name="R1", model="1941", category="router")]
        links = []
        for i in range(3):
            peer = f"RX{i}"
            devs.append(DevicePlan(name=peer, model="2911", category="router"))
            links.append(LinkPlan(device_a="R1", port_a=f"GigabitEthernet0/{i}",
                                   device_b=peer, port_b="GigabitEthernet0/0", cable="straight"))
        plan = TopologyPlan(devices=devs, links=links)
        codes = [e.code.value for e in validate_plan(plan).errors]
        assert "INSUFFICIENT_PORTS" in codes

    def test_acl_nat_accept_subinterface_binding(self):
        # ROAS routers bind ACL/NAT to dot1Q subinterfaces (Gi0/0.10), which
        # aren't in the static catalog - validation must accept them.
        from packet_tracer_mcp.shared.utils import is_port_or_subinterface
        ports = {"GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2"}
        assert is_port_or_subinterface("GigabitEthernet0/0.10", ports) is True
        assert is_port_or_subinterface("GigabitEthernet0/0", ports) is True
        assert is_port_or_subinterface("GigabitEthernet9/9", ports) is False
        assert is_port_or_subinterface("GigabitEthernet9/9.10", ports) is False
        # end-to-end: NAT validation no longer rejects a subinterface
        from packet_tracer_mcp.domain.models.nat import NATConfig
        from packet_tracer_mcp.domain.rules.nat_rules import validate_nat_against_topology
        cfg = NATConfig(router="R1", mode="pat", inside_interface="GigabitEthernet0/0.10",
                        outside_interface="GigabitEthernet0/1", inside_networks=["192.168.0.0 0.0.0.255"],
                        use_interface_overload=True)
        res = validate_nat_against_topology(cfg, [{"name": "R1", "model": "2911"}])
        assert not any(e.code.value == "NAT_INTERFACE_NOT_FOUND" for e in res.errors)

    def test_dhcp_excludes_low_range(self):
        from packet_tracer_mcp.domain.services.ip_planner import IPPlanner
        plan, _ = plan_from_request(TopologyRequest(
            template=TopologyTemplate.SINGLE_LAN, routers=1, dhcp=True, pcs_per_lan=2))
        assert plan.dhcp_pools, "expected a DHCP pool"
        pool = plan.dhcp_pools[0]
        # excluded range spans gateway (.1) through .10, not just the gateway
        assert pool.excluded_start != pool.excluded_end
        assert pool.excluded_end.endswith(".10")
