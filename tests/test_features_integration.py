"""Integration tests for the new feature use cases + shared bridge-apply path.

The per-generator tests cover the IOS strings; these verify the use-case wiring
(generator -> apply_ios -> confirm path) and the shared scaffolding.
"""

from __future__ import annotations

from packet_tracer_mcp.application.use_cases._bridge_apply import (
    build_ios_payload, build_configure_js, parse_ok, apply_ios,
)
from packet_tracer_mcp.application.use_cases import apply_features as F

OK = lambda js: '{"ok": true}'
REJECT = lambda js: '{"ok": false}'
TIMEOUT = lambda js: None


class TestBridgeApply:
    def test_payload_wrap(self):
        p = build_ios_payload(["interface Vlan10", " ip address 10.0.0.1 255.255.255.0", " exit"])
        assert p.startswith("enable\nconfigure terminal\n")
        assert p.endswith("\nend\nwrite memory")
        assert "interface Vlan10" in p

    def test_confirm_js_escapes(self):
        js = build_configure_js("R1", "hostname R1\nip routing")
        assert 'configureIosDevice("R1"' in js
        assert "\\n" in js                      # newlines escaped for the JS literal
        assert "reportResult(JSON.stringify({ok:" in js.replace(" ", "")

    def test_parse_ok(self):
        assert parse_ok('{"ok": true}') is True
        assert parse_ok('{"ok": false}') is False
        assert parse_ok(None) is None
        assert parse_ok("not json") is None

    def test_apply_ios_confirm_states(self):
        body = ["ip routing"]
        assert apply_ios("SW", body, confirm_send=OK)["applied"] is True
        assert apply_ios("SW", body, confirm_send=REJECT)["applied"] is False
        assert apply_ios("SW", body, confirm_send=TIMEOUT)["applied"] is None
        assert apply_ios("SW", body, dry_run=True)["sent"] is False


class TestFeatureUseCases:
    def test_svi(self):
        r = F.apply_svi_uc("L3SW", [{"vlan_id": 10, "ip": "192.168.10.1", "mask": "255.255.255.0", "name": "DATA"}], confirm_send=OK)
        assert r["applied"] is True
        assert "ip routing" in r["cli_lines"]
        assert "interface Vlan10" in r["cli_lines"]

    def test_etherchannel_both_ends_and_encap(self):
        r = F.configure_etherchannel_uc(
            "L3SW", ["GigabitEthernet0/1", "GigabitEthernet0/2"],
            "SW1", ["GigabitEthernet0/1", "GigabitEthernet0/2"],
            1, allowed_vlans=[10, 20], needs_encap_a=True, needs_encap_b=False, confirm_send=OK)
        assert r["applied"] is True
        # 3560 end has encapsulation, 2960 end does not
        assert any("encapsulation dot1q" in l for l in r["device_a"]["cli_lines"])
        assert not any("encapsulation dot1q" in l for l in r["device_b"]["cli_lines"])
        assert "interface Port-channel1" in r["device_a"]["cli_lines"]

    def test_port_security(self):
        r = F.apply_port_security_uc("SW1", "FastEthernet0/1", max_mac=2, violation="restrict", confirm_send=OK)
        assert r["applied"] is True
        assert " switchport port-security maximum 2" in r["cli_lines"]
        assert " switchport port-security violation restrict" in r["cli_lines"]

    def test_hsrp(self):
        r = F.apply_hsrp_uc("R1", "GigabitEthernet0/0", 1, "192.168.1.254", priority=110, confirm_send=OK)
        assert r["applied"] is True
        assert " standby 1 ip 192.168.1.254" in r["cli_lines"]
        assert " standby 1 priority 110" in r["cli_lines"]

    def test_static_and_default_routes(self):
        r = F.add_static_routes_uc("R1", [
            {"destination": "0.0.0.0", "mask": "0.0.0.0", "next_hop": "10.0.0.2"},
            {"destination": "192.168.5.0", "mask": "255.255.255.0", "next_hop": "10.0.0.6", "admin_distance": 5},
        ], confirm_send=OK)
        assert r["applied"] is True
        assert "ip route 0.0.0.0 0.0.0.0 10.0.0.2" in r["cli_lines"]
        assert "ip route 192.168.5.0 255.255.255.0 10.0.0.6 5" in r["cli_lines"]

    def test_dhcp_relay(self):
        r = F.apply_dhcp_relay_uc("R1", "GigabitEthernet0/0", ["192.168.0.10", "192.168.0.11"], confirm_send=OK)
        assert r["applied"] is True
        assert " ip helper-address 192.168.0.10" in r["cli_lines"]
        assert " ip helper-address 192.168.0.11" in r["cli_lines"]

    def test_ipv6_dualstack_ospfv3(self):
        r = F.apply_ipv6_uc("R1", [{"interface": "GigabitEthernet0/0", "ipv6": "2001:db8:1::1/64", "ospf_area": 0}],
                            ospfv3={"process_id": 1, "router_id": "1.1.1.1"}, confirm_send=OK)
        assert r["applied"] is True
        assert "ipv6 unicast-routing" in r["cli_lines"]
        assert " ipv6 address 2001:db8:1::1/64" in r["cli_lines"]
        assert " ipv6 ospf 1 area 0" in r["cli_lines"]
        assert "ipv6 router ospf 1" in r["cli_lines"]
