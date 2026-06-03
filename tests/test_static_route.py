"""Unit tests for the static route + DHCP relay IOS-CLI generators."""

from packet_tracer_mcp.infrastructure.generator.static_route_cli_generator import (
    generate_static_route_cli,
    generate_dhcp_relay_cli,
)


def test_static_route_basic():
    """A plain static route emits a single ip route line, no admin distance."""
    lines = generate_static_route_cli(
        [{"destination": "192.168.1.0", "mask": "255.255.255.0", "next_hop": "10.0.0.2"}]
    )
    assert lines == ["ip route 192.168.1.0 255.255.255.0 10.0.0.2"]


def test_static_route_admin_distance_appended_when_not_one():
    """A non-default admin distance is appended to the line."""
    lines = generate_static_route_cli(
        [
            {
                "destination": "192.168.1.0",
                "mask": "255.255.255.0",
                "next_hop": "10.0.0.2",
                "admin_distance": 5,
            }
        ]
    )
    assert lines == ["ip route 192.168.1.0 255.255.255.0 10.0.0.2 5"]


def test_static_route_admin_distance_one_omitted():
    """The default admin distance of 1 is never emitted."""
    lines = generate_static_route_cli(
        [
            {
                "destination": "192.168.1.0",
                "mask": "255.255.255.0",
                "next_hop": "10.0.0.2",
                "admin_distance": 1,
            }
        ]
    )
    assert lines == ["ip route 192.168.1.0 255.255.255.0 10.0.0.2"]


def test_default_route():
    """A default route uses the 0.0.0.0 0.0.0.0 destination/mask."""
    lines = generate_static_route_cli(
        [{"destination": "0.0.0.0", "mask": "0.0.0.0", "next_hop": "203.0.113.1"}]
    )
    assert lines == ["ip route 0.0.0.0 0.0.0.0 203.0.113.1"]


def test_multiple_routes_order_preserved():
    """Routes are emitted in input order, one line each."""
    lines = generate_static_route_cli(
        [
            {"destination": "0.0.0.0", "mask": "0.0.0.0", "next_hop": "203.0.113.1"},
            {
                "destination": "10.1.0.0",
                "mask": "255.255.0.0",
                "next_hop": "10.0.0.2",
                "admin_distance": 250,
            },
            {"destination": "172.16.0.0", "mask": "255.255.0.0", "next_hop": "10.0.0.3"},
        ]
    )
    assert lines == [
        "ip route 0.0.0.0 0.0.0.0 203.0.113.1",
        "ip route 10.1.0.0 255.255.0.0 10.0.0.2 250",
        "ip route 172.16.0.0 255.255.0.0 10.0.0.3",
    ]


def test_dhcp_relay_single_helper():
    """A single helper produces the interface block bracketed by exit."""
    lines = generate_dhcp_relay_cli("GigabitEthernet0/0", ["10.0.0.10"])
    assert lines == [
        "interface GigabitEthernet0/0",
        " ip helper-address 10.0.0.10",
        " exit",
    ]


def test_dhcp_relay_multiple_helpers_order_and_indent():
    """Multiple helpers are indented, in order, and the block ends with exit."""
    lines = generate_dhcp_relay_cli(
        "Vlan10", ["10.0.0.10", "10.0.0.11", "10.0.0.12"]
    )
    assert lines == [
        "interface Vlan10",
        " ip helper-address 10.0.0.10",
        " ip helper-address 10.0.0.11",
        " ip helper-address 10.0.0.12",
        " exit",
    ]
    # The closing exit is the last line of the block.
    assert lines[-1] == " exit"
    # Sub-commands get exactly one leading space.
    for helper_line in lines[1:-1]:
        assert helper_line.startswith(" ip helper-address ")
        assert not helper_line.startswith("  ")


def test_dhcp_relay_no_helpers():
    """With no helpers the block is just the interface and exit."""
    lines = generate_dhcp_relay_cli("GigabitEthernet0/1", [])
    assert lines == ["interface GigabitEthernet0/1", " exit"]
