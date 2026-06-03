"""Regression tests for the reliability-audit fixes (generators + payloads).

Each test pins a confirmed audit finding so the fix cannot silently regress.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.infrastructure.generator.acl_cli_generator import build_remove_payload
from packet_tracer_mcp.infrastructure.generator.nat_cli_generator import build_nat_remove_payload
from packet_tracer_mcp.infrastructure.generator import nat_cli_generator as natg
from packet_tracer_mcp.infrastructure.generator.routing_cli_generator import (
    generate_ospf_cli, generate_eigrp_cli, generate_bgp_cli,
)
from packet_tracer_mcp.infrastructure.generator.etherchannel_cli_generator import generate_etherchannel_cli
from packet_tracer_mcp.infrastructure.generator.hsrp_cli_generator import generate_hsrp_cli
from packet_tracer_mcp.infrastructure.generator.switching_cli_generator import generate_stp_cli
from packet_tracer_mcp.infrastructure.generator.svi_cli_generator import generate_svi_cli
from packet_tracer_mcp.infrastructure.generator.interface_cli_generator import generate_serial_cli


class TestAclRemoval:
    def test_named_removal_emits_both_types(self):
        # #1: removal must not guess 'extended' and silently miss a standard ACL.
        p = build_remove_payload("R1", "FOO")
        assert "no ip access-list standard FOO" in p
        assert "no ip access-list extended FOO" in p

    def test_numbered_removal_unchanged(self):
        assert "no access-list 10" in build_remove_payload("R1", "10")


class TestNatRemoval:
    def test_pat_removal_emits_both_forms(self):
        # #9: PAT-with-pool removed with default pool_name='' must still cover both.
        p = build_nat_remove_payload("R1", "pat", "g0/0", "g0/1", acl_number="1", pool_name="NAT")
        assert "interface g0/1 overload" in p          # interface-overload form
        assert "pool NAT overload" in p                # pool-overload form
        assert "no ip nat pool NAT" in p

    def test_named_acl_in_nat_body(self):
        # #10: a non-numeric acl_number must use the named-ACL block form.
        from packet_tracer_mcp.domain.models.nat import NATConfig
        cfg = NATConfig(router="R1", mode="pat", inside_interface="g0/0", outside_interface="g0/1",
                        acl_number="NAT_ACL", inside_networks=["10.0.0.0 0.0.0.255"],
                        use_interface_overload=True)
        body = natg.generate_nat_body_cli(cfg)
        assert "ip access-list standard NAT_ACL" in body
        assert " permit 10.0.0.0 0.0.0.255" in body
        assert not any(l.startswith("access-list NAT_ACL") for l in body)


class TestRoutingRouterId:
    def test_empty_router_id_skipped(self):
        # #6: empty string must not emit a malformed ' router-id ' line.
        for line in generate_ospf_cli(1, [{"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0}], router_id=""):
            assert line.strip() != "router-id"
        assert not any(l.strip() == "eigrp router-id" for l in generate_eigrp_cli(1, ["10.0.0.0"], router_id=""))
        assert not any(l.strip() == "bgp router-id" for l in generate_bgp_cli(1, router_id="", networks=[{"network": "1.0.0.0", "mask": "255.0.0.0"}]))

    def test_ospf_process_id_upper_bound(self):
        with pytest.raises(ValueError):
            generate_ospf_cli(70000, [{"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0}])


class TestEtherChannelValidation:
    def test_layer_normalized(self):
        lines = generate_etherchannel_cli(["Gi0/1"], 1, layer="L3")
        assert " no switchport" in lines  # 'L3' accepted, routed bundle

    def test_bad_layer_raises(self):
        with pytest.raises(ValueError):
            generate_etherchannel_cli(["Gi0/1"], 1, layer="routed")

    def test_bad_mode_raises(self):
        with pytest.raises(ValueError):
            generate_etherchannel_cli(["Gi0/1"], 1, mode="bogus")

    def test_bad_channel_id_raises(self):
        with pytest.raises(ValueError):
            generate_etherchannel_cli(["Gi0/1"], 99)


class TestHsrpValidation:
    def test_empty_interface_raises(self):
        with pytest.raises(ValueError):
            generate_hsrp_cli("", 1, "10.0.0.1")

    def test_empty_vip_raises(self):
        with pytest.raises(ValueError):
            generate_hsrp_cli("Gi0/0", 1, "")


class TestStpValidation:
    def test_bad_priority_raises(self):
        with pytest.raises(ValueError):
            generate_stp_cli(vlan_root=[{"vlan": 10, "priority": 100}])

    def test_good_priority_ok(self):
        assert "spanning-tree vlan 10 priority 4096" in generate_stp_cli(vlan_root=[{"vlan": 10, "priority": 4096}])

    def test_vlan_root_without_role_or_priority_raises(self):
        with pytest.raises(ValueError):
            generate_stp_cli(vlan_root=[{"vlan": 10}])


class TestSviGuard:
    def test_empty_no_routing_raises(self):
        with pytest.raises(ValueError):
            generate_svi_cli([], enable_routing=False)


class TestSerialValidation:
    def test_ppp_auth_requires_ppp_encap(self):
        with pytest.raises(ValueError):
            generate_serial_cli("Serial0/0/0", encapsulation="hdlc", ppp_auth="chap")

    def test_ppp_auth_with_ppp_ok(self):
        assert " ppp authentication chap" in generate_serial_cli("Serial0/0/0", encapsulation="ppp", ppp_auth="chap")


class TestAutoFixerCapacity:
    def test_fastethernet_router_not_upgraded(self):
        # #5: a 1841 (2 FastEthernet, 0 GigE) using both ports is valid and must
        # NOT be upgraded to 2911 (capacity must compare TOTAL ports, not GigE).
        from packet_tracer_mcp.domain.models.plans import TopologyPlan, DevicePlan, LinkPlan
        from packet_tracer_mcp.domain.services.auto_fixer import _fix_insufficient_ports
        plan = TopologyPlan(name="t", devices=[
            DevicePlan(name="R1", model="1841", category="router"),
            DevicePlan(name="R2", model="1841", category="router"),
            DevicePlan(name="SW1", model="2960", category="switch"),
        ], links=[
            LinkPlan(device_a="R1", port_a="FastEthernet0/0", device_b="R2", port_b="FastEthernet0/0", cable="cross"),
            LinkPlan(device_a="R1", port_a="FastEthernet0/1", device_b="SW1", port_b="FastEthernet0/1", cable="straight"),
        ])
        fixes = _fix_insufficient_ports(plan)
        assert fixes == []
        assert plan.device_by_name("R1").model == "1841"


class TestDhcpSubinterface:
    def test_gateway_on_subinterface_ok(self):
        # #16: router-on-a-stick gateway lives on a subinterface, not in
        # router.interfaces, and must not raise a false DHCP_GATEWAY_MISMATCH.
        from packet_tracer_mcp.domain.models.plans import TopologyPlan, DevicePlan, Subinterface, DHCPPool
        from packet_tracer_mcp.domain.models.errors import ErrorCode
        from packet_tracer_mcp.domain.rules.ip_rules import validate_dhcp
        plan = TopologyPlan(name="t", devices=[
            DevicePlan(name="R1", model="2911", category="router"),
        ], subinterfaces=[
            Subinterface(router="R1", parent_port="GigabitEthernet0/0", vlan_id=10,
                         ip="192.168.10.1", mask="255.255.255.0"),
        ], dhcp_pools=[
            DHCPPool(router="R1", pool_name="VLAN10", network="192.168.10.0",
                     mask="255.255.255.0", gateway="192.168.10.1"),
        ])
        errs = validate_dhcp(plan)
        assert not any(e.code == ErrorCode.DHCP_GATEWAY_MISMATCH for e in errs)


class TestEmptyPlanGuard:
    def test_empty_plan_rejected(self):
        # #18: a structurally-valid but device-less plan must error, not no-op.
        from packet_tracer_mcp.adapters.mcp.tool_registry import _load_plan_or_error
        plan, err = _load_plan_or_error('{"name":"empty","devices":[],"links":[]}')
        assert plan is None
        assert err is not None and "EMPTY_PLAN" in err


class TestProjectListingResilience:
    def test_corrupt_metadata_does_not_crash(self, tmp_path):
        # #20: one corrupt metadata.json must not take down the whole listing.
        from packet_tracer_mcp.infrastructure.persistence.project_repository import ProjectRepository
        (tmp_path / "good").mkdir()
        (tmp_path / "good" / "metadata.json").write_text('{"project_name":"good"}', encoding="utf-8")
        (tmp_path / "bad").mkdir()
        (tmp_path / "bad" / "metadata.json").write_text('{ this is not json', encoding="utf-8")
        repo = ProjectRepository(base_dir=tmp_path)
        names = {p.get("project_name") for p in repo.list_projects()}
        assert "good" in names and "bad" in names


class TestBridgeProtocol:
    def test_drain_and_requested_timeout(self):
        # #3/#4: /drain clears orphaned results; /result honors ?timeout.
        import json as _json
        import urllib.request
        import urllib.error
        from packet_tracer_mcp.infrastructure.execution.live_bridge import PTCommandBridge
        b = PTCommandBridge(port=54387)
        b.start()
        U = "http://127.0.0.1:54387"

        def get(path, t=6):
            try:
                with urllib.request.urlopen(U + path, timeout=t) as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                return e.code, ""

        def post(path, body):
            req = urllib.request.Request(U + path, data=body.encode(), method="POST")
            with urllib.request.urlopen(req, timeout=4) as r:
                return r.status

        try:
            assert _json.loads(get("/drain")[1])["drained"] == 0
            post("/result", "HELLO")
            assert get("/result?timeout=5") == (200, "HELLO")
            assert get("/result?timeout=1", t=4)[0] == 204     # empty -> 204
            post("/result", "A")
            post("/result", "B")
            assert _json.loads(get("/drain")[1])["drained"] == 2
        finally:
            b.stop()
