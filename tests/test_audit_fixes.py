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
