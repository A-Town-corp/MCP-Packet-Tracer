"""Unit tests for the HSRP CLI generator."""

from packet_tracer_mcp.infrastructure.generator.hsrp_cli_generator import (
    generate_hsrp_cli,
)


def test_hsrp_full_block_exact_lines_and_order():
    """All HSRP lines are emitted in the expected order with correct spacing."""
    lines = generate_hsrp_cli(
        interface="GigabitEthernet0/0",
        group=10,
        virtual_ip="10.0.0.1",
        priority=110,
        preempt=True,
        version=2,
    )
    assert lines == [
        "interface GigabitEthernet0/0",
        " standby version 2",
        " standby 10 ip 10.0.0.1",
        " standby 10 priority 110",
        " standby 10 preempt",
        " exit",
    ]


def test_hsrp_defaults():
    """Defaults: priority 100, preempt enabled, version 2."""
    lines = generate_hsrp_cli("Vlan20", 20, "192.168.20.254")
    assert lines == [
        "interface Vlan20",
        " standby version 2",
        " standby 20 ip 192.168.20.254",
        " standby 20 priority 100",
        " standby 20 preempt",
        " exit",
    ]


def test_hsrp_no_preempt_omits_preempt_line():
    """When preempt is False, the preempt line must NOT be emitted."""
    lines = generate_hsrp_cli(
        "GigabitEthernet0/1", 1, "172.16.0.1", priority=90, preempt=False
    )
    assert " standby 1 preempt" not in lines
    assert lines == [
        "interface GigabitEthernet0/1",
        " standby version 2",
        " standby 1 ip 172.16.0.1",
        " standby 1 priority 90",
        " exit",
    ]


def test_hsrp_block_structure():
    """The block starts with the interface and ends with a single ' exit'."""
    lines = generate_hsrp_cli("Vlan99", 99, "10.99.0.1")
    assert lines[0] == "interface Vlan99"
    assert lines[-1] == " exit"
    # Every sub-command (non-interface, non-empty) carries a single leading space.
    for line in lines[1:]:
        assert line.startswith(" ")
        assert not line.startswith("  ")


def test_hsrp_version_override():
    """An explicit version is reflected in the standby version line."""
    lines = generate_hsrp_cli("Vlan10", 10, "10.0.0.1", version=1)
    assert " standby version 1" in lines
