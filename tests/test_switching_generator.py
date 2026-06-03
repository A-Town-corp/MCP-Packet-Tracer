"""Tests for the switching CLI generator (STP, VTP, VLANs)."""
from __future__ import annotations

import pytest

from packet_tracer_mcp.infrastructure.generator.switching_cli_generator import (
    generate_stp_cli,
    generate_vtp_cli,
    generate_vlans_cli,
)


# ---------------------------------------------------------------------------
# generate_stp_cli
# ---------------------------------------------------------------------------

class TestGenerateStpCli:

    def test_mode_rapid_pvst(self):
        lines = generate_stp_cli(mode="rapid-pvst")
        assert "spanning-tree mode rapid-pvst" in lines

    def test_mode_pvst(self):
        lines = generate_stp_cli(mode="pvst")
        assert "spanning-tree mode pvst" in lines

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid STP mode"):
            generate_stp_cli(mode="mstp")

    def test_vlan_root_primary(self):
        lines = generate_stp_cli(vlan_root=[{"vlan": 10, "role": "primary"}])
        assert "spanning-tree vlan 10 root primary" in lines

    def test_vlan_root_secondary(self):
        lines = generate_stp_cli(vlan_root=[{"vlan": 20, "role": "secondary"}])
        assert "spanning-tree vlan 20 root secondary" in lines

    def test_vlan_priority_takes_precedence_over_role(self):
        # When both priority and role are present, priority wins.
        lines = generate_stp_cli(
            vlan_root=[{"vlan": 10, "role": "primary", "priority": 4096}]
        )
        assert "spanning-tree vlan 10 priority 4096" in lines
        assert "spanning-tree vlan 10 root primary" not in lines

    def test_vlan_priority_only(self):
        lines = generate_stp_cli(vlan_root=[{"vlan": 30, "priority": 8192}])
        assert "spanning-tree vlan 30 priority 8192" in lines

    def test_portfast_default(self):
        lines = generate_stp_cli(portfast_default=True)
        assert "spanning-tree portfast default" in lines

    def test_bpduguard_default(self):
        lines = generate_stp_cli(bpduguard_default=True)
        assert "spanning-tree portfast bpduguard default" in lines

    def test_portfast_interface_block(self):
        lines = generate_stp_cli(portfast_interfaces=["FastEthernet0/1"])
        assert "interface FastEthernet0/1" in lines
        assert " spanning-tree portfast" in lines
        # Block must close with a single-space exit.
        idx = lines.index("interface FastEthernet0/1")
        assert lines[idx + 1] == " spanning-tree portfast"
        assert lines[idx + 2] == " exit"

    def test_bpduguard_interface_block(self):
        lines = generate_stp_cli(bpduguard_interfaces=["GigabitEthernet0/1"])
        assert "interface GigabitEthernet0/1" in lines
        assert " spanning-tree bpduguard enable" in lines
        idx = lines.index("interface GigabitEthernet0/1")
        assert lines[idx + 1] == " spanning-tree bpduguard enable"
        assert lines[idx + 2] == " exit"

    def test_order_mode_first_then_vlan_root_then_defaults_then_ifaces(self):
        lines = generate_stp_cli(
            mode="rapid-pvst",
            vlan_root=[{"vlan": 10, "role": "primary"}],
            portfast_default=True,
            bpduguard_default=True,
            portfast_interfaces=["Fa0/2"],
            bpduguard_interfaces=["Fa0/3"],
        )
        idx_mode = lines.index("spanning-tree mode rapid-pvst")
        idx_root = lines.index("spanning-tree vlan 10 root primary")
        idx_pf = lines.index("spanning-tree portfast default")
        idx_bg = lines.index("spanning-tree portfast bpduguard default")
        idx_iface_pf = lines.index("interface Fa0/2")
        idx_iface_bg = lines.index("interface Fa0/3")
        assert idx_mode < idx_root < idx_pf < idx_bg < idx_iface_pf < idx_iface_bg

    def test_multiple_vlans(self):
        lines = generate_stp_cli(
            vlan_root=[
                {"vlan": 10, "role": "primary"},
                {"vlan": 20, "role": "secondary"},
            ]
        )
        assert "spanning-tree vlan 10 root primary" in lines
        assert "spanning-tree vlan 20 root secondary" in lines

    def test_no_args_raises(self):
        with pytest.raises(ValueError):
            generate_stp_cli()

    def test_global_commands_have_no_leading_space(self):
        lines = generate_stp_cli(
            mode="pvst",
            vlan_root=[{"vlan": 1, "role": "primary"}],
            portfast_default=True,
            bpduguard_default=True,
        )
        for line in lines:
            assert not line.startswith(" "), f"Unexpected leading space: {line!r}"

    def test_interface_subcommands_single_leading_space(self):
        lines = generate_stp_cli(portfast_interfaces=["Fa0/5"])
        sub_lines = [l for l in lines if l.startswith(" ")]
        for line in sub_lines:
            assert not line.startswith("  "), f"Too many leading spaces: {line!r}"


# ---------------------------------------------------------------------------
# generate_vtp_cli
# ---------------------------------------------------------------------------

class TestGenerateVtpCli:

    def test_server_with_domain(self):
        lines = generate_vtp_cli(mode="server", domain="CCNA")
        assert "vtp domain CCNA" in lines
        assert "vtp mode server" in lines

    def test_domain_emitted_before_mode(self):
        lines = generate_vtp_cli(mode="server", domain="CCNA")
        assert lines.index("vtp domain CCNA") < lines.index("vtp mode server")

    def test_version_emitted_between_domain_and_mode(self):
        lines = generate_vtp_cli(mode="server", domain="CCNA", version=2)
        assert lines.index("vtp domain CCNA") < lines.index("vtp version 2")
        assert lines.index("vtp version 2") < lines.index("vtp mode server")

    def test_password_emitted_after_mode(self):
        lines = generate_vtp_cli(mode="server", password="secret")
        assert lines.index("vtp mode server") < lines.index("vtp password secret")

    def test_client_mode(self):
        lines = generate_vtp_cli(mode="client")
        assert "vtp mode client" in lines

    def test_transparent_mode(self):
        lines = generate_vtp_cli(mode="transparent")
        assert "vtp mode transparent" in lines

    def test_off_mode(self):
        lines = generate_vtp_cli(mode="off")
        assert "vtp mode off" in lines

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid VTP mode"):
            generate_vtp_cli(mode="master")

    def test_domain_absent_when_not_provided(self):
        lines = generate_vtp_cli(mode="transparent")
        assert not any(l.startswith("vtp domain") for l in lines)

    def test_password_absent_when_not_provided(self):
        lines = generate_vtp_cli(mode="server", domain="LAB")
        assert not any(l.startswith("vtp password") for l in lines)

    def test_full_config_exact_order(self):
        lines = generate_vtp_cli(
            mode="server", domain="CCNA", password="cisco123", version=2
        )
        assert lines == [
            "vtp domain CCNA",
            "vtp version 2",
            "vtp mode server",
            "vtp password cisco123",
        ]


# ---------------------------------------------------------------------------
# generate_vlans_cli
# ---------------------------------------------------------------------------

class TestGenerateVlansCli:

    def test_single_vlan_with_name(self):
        lines = generate_vlans_cli([{"vlan_id": 10, "name": "SALES"}])
        assert "vlan 10" in lines
        assert " name SALES" in lines

    def test_single_vlan_without_name(self):
        lines = generate_vlans_cli([{"vlan_id": 10}])
        assert "vlan 10" in lines
        assert not any(l.startswith(" name") for l in lines)

    def test_vlan_block_ends_with_space_exit(self):
        lines = generate_vlans_cli([{"vlan_id": 10, "name": "SALES"}])
        idx = lines.index("vlan 10")
        assert lines[idx + 1] == " name SALES"
        assert lines[idx + 2] == " exit"

    def test_multiple_vlans(self):
        lines = generate_vlans_cli([
            {"vlan_id": 10, "name": "SALES"},
            {"vlan_id": 20, "name": "HR"},
            {"vlan_id": 99},
        ])
        assert "vlan 10" in lines
        assert " name SALES" in lines
        assert "vlan 20" in lines
        assert " name HR" in lines
        assert "vlan 99" in lines

    def test_empty_vlans_raises(self):
        with pytest.raises(ValueError):
            generate_vlans_cli([])

    def test_vlan_id_boundary_low(self):
        lines = generate_vlans_cli([{"vlan_id": 1}])
        assert "vlan 1" in lines

    def test_vlan_id_boundary_high(self):
        lines = generate_vlans_cli([{"vlan_id": 4094}])
        assert "vlan 4094" in lines

    def test_vlan_id_out_of_range_low(self):
        with pytest.raises(ValueError):
            generate_vlans_cli([{"vlan_id": 0}])

    def test_vlan_id_out_of_range_high(self):
        with pytest.raises(ValueError):
            generate_vlans_cli([{"vlan_id": 4095}])

    def test_vlan_name_subcommand_single_leading_space(self):
        lines = generate_vlans_cli([{"vlan_id": 10, "name": "MGMT"}])
        name_line = next(l for l in lines if "name" in l)
        assert name_line.startswith(" ")
        assert not name_line.startswith("  ")

    def test_vlan_id_line_no_leading_space(self):
        lines = generate_vlans_cli([{"vlan_id": 10, "name": "TEST"}])
        vlan_line = next(l for l in lines if l.startswith("vlan"))
        assert not vlan_line.startswith(" ")
