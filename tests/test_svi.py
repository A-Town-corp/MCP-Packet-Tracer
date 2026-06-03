"""Unit tests for the SVI (L3-switch inter-VLAN routing) CLI generator."""

from __future__ import annotations

from packet_tracer_mcp.infrastructure.generator.svi_cli_generator import (
    generate_svi_cli,
)


class TestSVIGenerator:
    def test_ip_routing_emitted_first_when_enabled(self):
        lines = generate_svi_cli(
            [{"vlan_id": 10, "ip": "10.0.10.1", "mask": "255.255.255.0"}],
            enable_routing=True,
        )
        assert lines[0] == "ip routing"

    def test_ip_routing_omitted_when_disabled(self):
        lines = generate_svi_cli(
            [{"vlan_id": 10, "ip": "10.0.10.1", "mask": "255.255.255.0"}],
            enable_routing=False,
        )
        assert "ip routing" not in lines
        # First line should be the SVI block, not ip routing.
        assert lines[0] == "interface Vlan10"

    def test_svi_block_without_name(self):
        lines = generate_svi_cli(
            [{"vlan_id": 20, "ip": "10.0.20.1", "mask": "255.255.255.0"}],
            enable_routing=False,
        )
        assert lines == [
            "interface Vlan20",
            " ip address 10.0.20.1 255.255.255.0",
            " no shutdown",
            " exit",
        ]

    def test_named_vlan_created_before_svi(self):
        lines = generate_svi_cli(
            [{"vlan_id": 30, "ip": "10.0.30.1", "mask": "255.255.255.0",
              "name": "SALES"}],
            enable_routing=False,
        )
        assert lines == [
            "vlan 30",
            " name SALES",
            " exit",
            "interface Vlan30",
            " ip address 10.0.30.1 255.255.255.0",
            " no shutdown",
            " exit",
        ]

    def test_sub_commands_have_single_leading_space(self):
        lines = generate_svi_cli(
            [{"vlan_id": 10, "ip": "10.0.10.1", "mask": "255.255.255.0",
              "name": "ENG"}],
            enable_routing=True,
        )
        # Every indented sub-command starts with exactly one space.
        for ln in lines:
            if ln.startswith(" "):
                assert not ln.startswith("  "), f"double-indented line: {ln!r}"

    def test_every_block_ends_with_exit(self):
        lines = generate_svi_cli(
            [
                {"vlan_id": 10, "ip": "10.0.10.1", "mask": "255.255.255.0",
                 "name": "ENG"},
                {"vlan_id": 20, "ip": "10.0.20.1", "mask": "255.255.255.0"},
            ],
            enable_routing=True,
        )
        # ip routing, vlan block (3), svi block (4), svi block (4) = 12 lines.
        assert lines[0] == "ip routing"
        # Both interface blocks must terminate with an " exit".
        assert lines.count("interface Vlan10") == 1
        assert lines.count("interface Vlan20") == 1
        assert lines[-1] == " exit"

    def test_multiple_vlans_order_preserved(self):
        lines = generate_svi_cli(
            [
                {"vlan_id": 10, "ip": "10.0.10.1", "mask": "255.255.255.0"},
                {"vlan_id": 20, "ip": "10.0.20.1", "mask": "255.255.255.0"},
                {"vlan_id": 30, "ip": "10.0.30.1", "mask": "255.255.255.0"},
            ],
            enable_routing=True,
        )
        assert lines.index("interface Vlan10") < lines.index("interface Vlan20")
        assert lines.index("interface Vlan20") < lines.index("interface Vlan30")

    def test_no_router_on_a_stick_artifacts(self):
        # SVIs must NEVER emit dot1Q encapsulation; that belongs to
        # router-on-a-stick, not to multilayer-switch SVIs.
        lines = generate_svi_cli(
            [{"vlan_id": 10, "ip": "10.0.10.1", "mask": "255.255.255.0",
              "name": "ENG"}],
            enable_routing=True,
        )
        joined = "\n".join(lines)
        assert "encapsulation dot1Q" not in joined
        assert "switchport trunk encapsulation dot1q" not in joined

    def test_empty_vlans_with_routing(self):
        lines = generate_svi_cli([], enable_routing=True)
        assert lines == ["ip routing"]

    def test_empty_vlans_without_routing(self):
        # A call that would configure nothing (no VLANs, no routing) is a footgun:
        # it used to return [] and report applied=true. It now fails fast.
        import pytest
        with pytest.raises(ValueError):
            generate_svi_cli([], enable_routing=False)

    def test_empty_vlans_with_routing_ok(self):
        assert generate_svi_cli([], enable_routing=True) == ["ip routing"]
