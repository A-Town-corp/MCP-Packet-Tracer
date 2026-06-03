"""Integration tests for the second wave of feature use cases.

The per-generator tests cover the exact IOS strings; these verify the use-case
wiring (generator -> apply_ios -> confirm path) for routing, device management,
switching and interface/WAN features, plus the universal apply_raw_ios path.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.application.use_cases import apply_features as F

OK = lambda js: '{"ok": true}'
REJECT = lambda js: '{"ok": false}'
TIMEOUT = lambda js: None


class TestRawIos:
    def test_passthrough_and_confirm(self):
        r = F.apply_raw_ios_uc("R1", ["interface Loopback9", " ip address 9.9.9.9 255.255.255.255", " exit"],
                               confirm_send=OK)
        assert r["applied"] is True
        assert "interface Loopback9" in r["cli_lines"]
        # wrapper added around the body
        assert r["ios_payload"].startswith("enable\nconfigure terminal\n")
        assert r["ios_payload"].endswith("\nend\nwrite memory")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            F.apply_raw_ios_uc("R1", ["   ", ""])

    def test_confirm_states(self):
        body = ["hostname R1"]
        assert F.apply_raw_ios_uc("R1", body, confirm_send=REJECT)["applied"] is False
        assert F.apply_raw_ios_uc("R1", body, confirm_send=TIMEOUT)["applied"] is None
        assert F.apply_raw_ios_uc("R1", body, dry_run=True)["sent"] is False


class TestRouting:
    def test_ospf(self):
        r = F.apply_ospf_uc("R1", 1, [{"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0}],
                            router_id="1.1.1.1", confirm_send=OK)
        assert r["applied"] is True
        assert "router ospf 1" in r["cli_lines"]
        assert " network 10.0.0.0 0.0.0.255 area 0" in r["cli_lines"]
        assert " router-id 1.1.1.1" in r["cli_lines"]

    def test_rip(self):
        r = F.apply_rip_uc("R1", ["10.0.0.0", "192.168.1.0"], confirm_send=OK)
        assert r["applied"] is True
        assert "router rip" in r["cli_lines"]
        assert " version 2" in r["cli_lines"]
        assert " no auto-summary" in r["cli_lines"]

    def test_eigrp_mixed_networks(self):
        r = F.apply_eigrp_uc("R1", 100, ["10.0.0.0", {"network": "192.168.1.0", "wildcard": "0.0.0.255"}],
                             confirm_send=OK)
        assert r["applied"] is True
        assert "router eigrp 100" in r["cli_lines"]
        assert " network 10.0.0.0" in r["cli_lines"]
        assert " network 192.168.1.0 0.0.0.255" in r["cli_lines"]

    def test_bgp(self):
        r = F.apply_bgp_uc("R1", 65001, router_id="1.1.1.1",
                           neighbors=[{"ip": "10.0.0.2", "remote_as": 65002, "description": "ISP"}],
                           networks=[{"network": "192.168.1.0", "mask": "255.255.255.0"}], confirm_send=OK)
        assert r["applied"] is True
        assert "router bgp 65001" in r["cli_lines"]
        assert " neighbor 10.0.0.2 remote-as 65002" in r["cli_lines"]
        assert " network 192.168.1.0 mask 255.255.255.0" in r["cli_lines"]


class TestDeviceMgmt:
    def test_security_ssh(self):
        r = F.apply_device_security_uc(
            "R1", hostname="R1", enable_secret="cisco123",
            ssh={"domain": "lab.local", "username": "admin", "password": "cisco"}, confirm_send=OK)
        assert r["applied"] is True
        assert "hostname R1" in r["cli_lines"]
        assert "enable secret cisco123" in r["cli_lines"]
        assert " transport input ssh" in r["cli_lines"]
        assert any("crypto key generate rsa" in l for l in r["cli_lines"])

    def test_management(self):
        r = F.apply_management_uc("R1", ntp_servers=["10.0.0.1"],
                                  snmp={"community": "public", "access": "ro"}, confirm_send=OK)
        assert r["applied"] is True
        assert "ntp server 10.0.0.1" in r["cli_lines"]
        assert "snmp-server community public RO" in r["cli_lines"]


class TestSwitching:
    def test_stp(self):
        r = F.apply_stp_uc("SW1", mode="rapid-pvst",
                           vlan_root=[{"vlan": 10, "role": "primary"}],
                           portfast_interfaces=["FastEthernet0/1"], confirm_send=OK)
        assert r["applied"] is True
        assert "spanning-tree mode rapid-pvst" in r["cli_lines"]
        assert "spanning-tree vlan 10 root primary" in r["cli_lines"]
        assert " spanning-tree portfast" in r["cli_lines"]

    def test_vtp(self):
        r = F.apply_vtp_uc("SW1", "server", domain="CCNA", password="cisco", confirm_send=OK)
        assert r["applied"] is True
        assert "vtp domain CCNA" in r["cli_lines"]
        assert "vtp mode server" in r["cli_lines"]

    def test_create_vlans(self):
        r = F.create_vlans_uc("SW1", [{"vlan_id": 10, "name": "SALES"}, {"vlan_id": 20}], confirm_send=OK)
        assert r["applied"] is True
        assert "vlan 10" in r["cli_lines"]
        assert " name SALES" in r["cli_lines"]
        assert "vlan 20" in r["cli_lines"]


class TestInterfaceWan:
    def test_interface(self):
        r = F.configure_interface_uc("R1", "GigabitEthernet0/0", ip="10.0.0.1", mask="255.255.255.0",
                                     description="LAN", shutdown=False, confirm_send=OK)
        assert r["applied"] is True
        assert "interface GigabitEthernet0/0" in r["cli_lines"]
        assert " ip address 10.0.0.1 255.255.255.0" in r["cli_lines"]
        assert " no shutdown" in r["cli_lines"]

    def test_loopback(self):
        r = F.apply_loopback_uc("R1", 0, "1.1.1.1", "255.255.255.255", confirm_send=OK)
        assert r["applied"] is True
        assert "interface Loopback0" in r["cli_lines"]
        assert " ip address 1.1.1.1 255.255.255.255" in r["cli_lines"]

    def test_serial_ppp(self):
        r = F.configure_serial_uc("R1", "Serial0/0/0", encapsulation="ppp", clock_rate=64000,
                                  ip="10.0.0.1", mask="255.255.255.252", ppp_auth="chap",
                                  username="PEER", password="cisco", confirm_send=OK)
        assert r["applied"] is True
        assert "username PEER password cisco" in r["cli_lines"]
        assert " encapsulation ppp" in r["cli_lines"]
        assert " ppp authentication chap" in r["cli_lines"]

    def test_gre_tunnel(self):
        r = F.apply_gre_tunnel_uc("R1", 0, "GigabitEthernet0/0", "200.0.0.2",
                                  "172.16.0.1", "255.255.255.0", confirm_send=OK)
        assert r["applied"] is True
        assert "interface Tunnel0" in r["cli_lines"]
        assert " tunnel source GigabitEthernet0/0" in r["cli_lines"]
        assert " tunnel destination 200.0.0.2" in r["cli_lines"]
