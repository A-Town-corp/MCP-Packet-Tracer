"""Unit tests for the interface, loopback, serial, and GRE tunnel CLI generators."""

import pytest

from packet_tracer_mcp.infrastructure.generator.interface_cli_generator import (
    generate_gre_tunnel_cli,
    generate_interface_cli,
    generate_loopback_cli,
    generate_serial_cli,
)


# ---------------------------------------------------------------------------
# generate_interface_cli
# ---------------------------------------------------------------------------

class TestGenerateInterfaceCli:
    def test_basic_ip_and_no_shutdown(self):
        lines = generate_interface_cli(
            "GigabitEthernet0/0",
            ip="10.0.0.1",
            mask="255.255.255.0",
            shutdown=False,
        )
        assert "interface GigabitEthernet0/0" in lines
        assert " ip address 10.0.0.1 255.255.255.0" in lines
        assert " no shutdown" in lines
        assert " exit" in lines

    def test_shutdown_true(self):
        lines = generate_interface_cli("GigabitEthernet0/1", shutdown=True)
        assert " shutdown" in lines
        assert " no shutdown" not in lines

    def test_shutdown_none_emits_nothing(self):
        lines = generate_interface_cli("GigabitEthernet0/2")
        assert " shutdown" not in lines
        assert " no shutdown" not in lines

    def test_description_speed_duplex_mtu(self):
        lines = generate_interface_cli(
            "FastEthernet0/0",
            description="uplink to R1",
            speed="100",
            duplex="full",
            mtu=1500,
        )
        assert " description uplink to R1" in lines
        assert " speed 100" in lines
        assert " duplex full" in lines
        assert " mtu 1500" in lines

    def test_no_switchport_flag(self):
        lines = generate_interface_cli("GigabitEthernet1/0", no_switchport=True)
        assert " no switchport" in lines
        # no switchport must come before any ip address line
        assert lines.index(" no switchport") < lines.index(" exit")

    def test_no_switchport_order_before_ip(self):
        lines = generate_interface_cli(
            "GigabitEthernet1/1",
            ip="192.168.1.1",
            mask="255.255.255.0",
            no_switchport=True,
        )
        assert lines.index(" no switchport") < lines.index(" ip address 192.168.1.1 255.255.255.0")

    def test_block_starts_with_interface_and_ends_with_exit(self):
        lines = generate_interface_cli("GigabitEthernet0/0")
        assert lines[0] == "interface GigabitEthernet0/0"
        assert lines[-1] == " exit"

    def test_ip_without_mask_raises(self):
        with pytest.raises(ValueError):
            generate_interface_cli("GigabitEthernet0/0", ip="10.0.0.1")

    def test_mask_without_ip_raises(self):
        with pytest.raises(ValueError):
            generate_interface_cli("GigabitEthernet0/0", mask="255.255.255.0")

    def test_empty_interface_raises(self):
        with pytest.raises(ValueError):
            generate_interface_cli("")

    def test_no_extra_lines_when_all_optional_omitted(self):
        lines = generate_interface_cli("GigabitEthernet0/0")
        assert lines == ["interface GigabitEthernet0/0", " exit"]

    def test_subcommands_have_single_leading_space(self):
        lines = generate_interface_cli(
            "GigabitEthernet0/0",
            ip="10.1.1.1",
            mask="255.255.255.0",
            description="test",
            speed="1000",
            duplex="full",
            mtu=9000,
            shutdown=False,
        )
        # All lines except the first (interface) and last (exit with space) are
        # sub-commands that must start with exactly one space.
        for line in lines[1:]:
            assert line.startswith(" "), f"sub-command missing leading space: {line!r}"
            assert not line.startswith("  "), f"sub-command has extra space: {line!r}"


# ---------------------------------------------------------------------------
# generate_loopback_cli
# ---------------------------------------------------------------------------

class TestGenerateLoopbackCli:
    def test_basic(self):
        lines = generate_loopback_cli(0, "1.1.1.1", "255.255.255.255")
        assert "interface Loopback0" in lines
        assert " ip address 1.1.1.1 255.255.255.255" in lines
        assert lines[0] == "interface Loopback0"
        assert lines[-1] == " exit"

    def test_with_description(self):
        lines = generate_loopback_cli(1, "10.0.0.1", "255.255.255.0", description="mgmt")
        assert " description mgmt" in lines
        assert lines.index(" description mgmt") < lines.index(" ip address 10.0.0.1 255.255.255.0")

    def test_negative_number_raises(self):
        with pytest.raises(ValueError):
            generate_loopback_cli(-1, "1.1.1.1", "255.255.255.255")

    def test_empty_ip_raises(self):
        with pytest.raises(ValueError):
            generate_loopback_cli(0, "", "255.255.255.255")

    def test_empty_mask_raises(self):
        with pytest.raises(ValueError):
            generate_loopback_cli(0, "1.1.1.1", "")

    def test_loopback_number_in_name(self):
        lines = generate_loopback_cli(99, "172.16.0.1", "255.255.255.0")
        assert lines[0] == "interface Loopback99"


# ---------------------------------------------------------------------------
# generate_serial_cli
# ---------------------------------------------------------------------------

class TestGenerateSerialCli:
    def test_basic_ppp_with_chap(self):
        lines = generate_serial_cli(
            "Serial0/0/0",
            ip="192.168.1.1",
            mask="255.255.255.252",
            encapsulation="ppp",
            ppp_auth="chap",
            username="PEER",
            password="cisco",
        )
        assert "username PEER password cisco" in lines
        assert "interface Serial0/0/0" in lines
        assert " ip address 192.168.1.1 255.255.255.252" in lines
        assert " encapsulation ppp" in lines
        assert " ppp authentication chap" in lines
        assert lines[-1] == " exit"

    def test_global_username_before_interface_block(self):
        lines = generate_serial_cli(
            "Serial0/0/0",
            encapsulation="ppp",
            ppp_auth="chap",
            username="PEER",
            password="cisco",
        )
        assert lines.index("username PEER password cisco") < lines.index("interface Serial0/0/0")

    def test_clock_rate(self):
        lines = generate_serial_cli("Serial0/0/0", clock_rate=64000)
        assert " clock rate 64000" in lines

    def test_hdlc_encapsulation(self):
        lines = generate_serial_cli("Serial0/0/1", encapsulation="hdlc")
        assert " encapsulation hdlc" in lines

    def test_frame_relay_encapsulation(self):
        lines = generate_serial_cli("Serial0/0/2", encapsulation="frame-relay")
        assert " encapsulation frame-relay" in lines

    def test_pap_auth(self):
        lines = generate_serial_cli(
            "Serial0/0/0",
            encapsulation="ppp",
            ppp_auth="pap",
            username="USER",
            password="pass",
        )
        assert " ppp authentication pap" in lines

    def test_no_username_no_global_line(self):
        lines = generate_serial_cli("Serial0/0/0")
        for line in lines:
            assert not line.startswith("username ")

    def test_bad_encapsulation_raises(self):
        with pytest.raises(ValueError):
            generate_serial_cli("Serial0/0/0", encapsulation="atm")

    def test_bad_ppp_auth_raises(self):
        with pytest.raises(ValueError):
            generate_serial_cli("Serial0/0/0", encapsulation="ppp", ppp_auth="ms-chap")

    def test_ip_without_mask_raises(self):
        with pytest.raises(ValueError):
            generate_serial_cli("Serial0/0/0", ip="10.0.0.1")

    def test_empty_interface_raises(self):
        with pytest.raises(ValueError):
            generate_serial_cli("")

    def test_minimal_block(self):
        lines = generate_serial_cli("Serial0/0/0")
        assert lines == ["interface Serial0/0/0", " exit"]


# ---------------------------------------------------------------------------
# generate_gre_tunnel_cli
# ---------------------------------------------------------------------------

class TestGenerateGreTunnelCli:
    def test_basic(self):
        lines = generate_gre_tunnel_cli(
            tunnel_number=0,
            source="GigabitEthernet0/0",
            destination="200.0.0.2",
            ip="172.16.0.1",
            mask="255.255.255.0",
        )
        assert "interface Tunnel0" in lines
        assert " ip address 172.16.0.1 255.255.255.0" in lines
        assert " tunnel source GigabitEthernet0/0" in lines
        assert " tunnel destination 200.0.0.2" in lines
        assert " tunnel mode gre ip" in lines
        assert lines[0] == "interface Tunnel0"
        assert lines[-1] == " exit"

    def test_with_description(self):
        lines = generate_gre_tunnel_cli(
            tunnel_number=1,
            source="10.0.0.1",
            destination="10.0.0.2",
            ip="192.168.100.1",
            mask="255.255.255.0",
            description="HQ-to-Branch",
        )
        assert " description HQ-to-Branch" in lines
        assert lines.index(" description HQ-to-Branch") < lines.index(" ip address 192.168.100.1 255.255.255.0")

    def test_tunnel_number_in_name(self):
        lines = generate_gre_tunnel_cli(5, "1.1.1.1", "2.2.2.2", "10.0.0.1", "255.255.255.252")
        assert lines[0] == "interface Tunnel5"

    def test_order_source_before_destination(self):
        lines = generate_gre_tunnel_cli(0, "1.1.1.1", "2.2.2.2", "10.0.0.1", "255.255.255.252")
        assert lines.index(" tunnel source 1.1.1.1") < lines.index(" tunnel destination 2.2.2.2")

    def test_mode_gre_ip_present(self):
        lines = generate_gre_tunnel_cli(0, "1.1.1.1", "2.2.2.2", "10.0.0.1", "255.255.255.252")
        assert " tunnel mode gre ip" in lines

    def test_negative_tunnel_number_raises(self):
        with pytest.raises(ValueError):
            generate_gre_tunnel_cli(-1, "1.1.1.1", "2.2.2.2", "10.0.0.1", "255.255.255.252")

    def test_empty_source_raises(self):
        with pytest.raises(ValueError):
            generate_gre_tunnel_cli(0, "", "2.2.2.2", "10.0.0.1", "255.255.255.252")

    def test_empty_destination_raises(self):
        with pytest.raises(ValueError):
            generate_gre_tunnel_cli(0, "1.1.1.1", "", "10.0.0.1", "255.255.255.252")

    def test_empty_ip_raises(self):
        with pytest.raises(ValueError):
            generate_gre_tunnel_cli(0, "1.1.1.1", "2.2.2.2", "", "255.255.255.252")

    def test_empty_mask_raises(self):
        with pytest.raises(ValueError):
            generate_gre_tunnel_cli(0, "1.1.1.1", "2.2.2.2", "10.0.0.1", "")

    def test_subcommands_single_leading_space(self):
        lines = generate_gre_tunnel_cli(
            0, "1.1.1.1", "2.2.2.2", "10.0.0.1", "255.255.255.252", description="test"
        )
        for line in lines[1:]:
            assert line.startswith(" "), f"missing leading space: {line!r}"
            assert not line.startswith("  "), f"double leading space: {line!r}"
