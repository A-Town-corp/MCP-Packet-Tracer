"""Unit tests for the switchport port-security IOS CLI generator."""

from __future__ import annotations
import pytest

from packet_tracer_mcp.infrastructure.generator.port_security_cli_generator import (
    generate_port_security_cli,
)


class TestPortSecurityGenerator:
    def test_defaults_emit_sticky_and_shutdown(self):
        lines = generate_port_security_cli("FastEthernet0/1")
        assert lines == [
            "interface FastEthernet0/1",
            " switchport mode access",
            " switchport port-security",
            " switchport port-security maximum 1",
            " switchport port-security mac-address sticky",
            " switchport port-security violation shutdown",
            " exit",
        ]

    def test_block_starts_with_interface_and_ends_with_exit(self):
        lines = generate_port_security_cli("FastEthernet0/2")
        assert lines[0] == "interface FastEthernet0/2"
        assert lines[-1] == " exit"

    def test_sub_commands_have_single_leading_space(self):
        lines = generate_port_security_cli("GigabitEthernet0/1")
        for line in lines[1:]:
            assert line.startswith(" ")
            assert not line.startswith("  ")

    def test_max_mac_is_emitted(self):
        lines = generate_port_security_cli("FastEthernet0/3", max_mac=3)
        assert " switchport port-security maximum 3" in lines

    def test_sticky_false_omits_sticky_line(self):
        lines = generate_port_security_cli("FastEthernet0/4", sticky=False)
        assert " switchport port-security mac-address sticky" not in lines
        # Order is preserved: maximum is immediately followed by violation.
        idx_max = lines.index(" switchport port-security maximum 1")
        assert lines[idx_max + 1] == " switchport port-security violation shutdown"

    def test_sticky_line_position(self):
        lines = generate_port_security_cli("FastEthernet0/5", sticky=True)
        # sticky must come after `maximum` and before `violation`.
        idx_max = lines.index(" switchport port-security maximum 1")
        idx_sticky = lines.index(" switchport port-security mac-address sticky")
        idx_viol = lines.index(" switchport port-security violation shutdown")
        assert idx_max < idx_sticky < idx_viol

    @pytest.mark.parametrize("violation", ["shutdown", "restrict", "protect"])
    def test_valid_violation_modes(self, violation):
        lines = generate_port_security_cli("FastEthernet0/6", violation=violation)
        assert f" switchport port-security violation {violation}" in lines

    def test_invalid_violation_raises(self):
        with pytest.raises(ValueError):
            generate_port_security_cli("FastEthernet0/7", violation="block")

    def test_access_mode_always_first_sub_command(self):
        # port-security requires an access port; mode access must precede it.
        lines = generate_port_security_cli("FastEthernet0/8")
        assert lines[1] == " switchport mode access"
        assert lines[2] == " switchport port-security"
