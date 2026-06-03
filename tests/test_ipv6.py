"""Unit tests for the IPv6 dual-stack + OSPFv3 CLI generator."""

from packet_tracer_mcp.infrastructure.generator.ipv6_cli_generator import (
    generate_ipv6_cli,
)


def test_enable_routing_emits_unicast_routing_first():
    """`ipv6 unicast-routing` is emitted first when routing is enabled."""
    lines = generate_ipv6_cli(
        [{"interface": "GigabitEthernet0/0", "ipv6": "2001:db8:1::1/64"}]
    )
    assert lines[0] == "ipv6 unicast-routing"


def test_disable_routing_omits_unicast_routing():
    """No `ipv6 unicast-routing` line when enable_routing is False."""
    lines = generate_ipv6_cli(
        [{"interface": "GigabitEthernet0/0", "ipv6": "2001:db8:1::1/64"}],
        enable_routing=False,
    )
    assert "ipv6 unicast-routing" not in lines


def test_interface_block_structure_and_order():
    """An interface block emits address, no shutdown, then exit in order."""
    lines = generate_ipv6_cli(
        [{"interface": "GigabitEthernet0/1", "ipv6": "2001:db8:2::1/64"}],
        enable_routing=False,
    )
    assert lines == [
        "interface GigabitEthernet0/1",
        " ipv6 address 2001:db8:2::1/64",
        " no shutdown",
        " exit",
    ]


def test_ospf_area_line_present_when_ospfv3_and_area_given():
    """The per-interface OSPFv3 line appears between address and no shutdown."""
    lines = generate_ipv6_cli(
        [
            {
                "interface": "GigabitEthernet0/0",
                "ipv6": "2001:db8:1::1/64",
                "ospf_area": 0,
            }
        ],
        enable_routing=False,
        ospfv3={"process_id": 1},
    )
    assert lines == [
        "interface GigabitEthernet0/0",
        " ipv6 address 2001:db8:1::1/64",
        " ipv6 ospf 1 area 0",
        " no shutdown",
        " exit",
        "ipv6 router ospf 1",
        " exit",
    ]


def test_ospf_area_skipped_without_ospfv3():
    """No per-interface OSPF line when ospfv3 is None, even with ospf_area."""
    lines = generate_ipv6_cli(
        [
            {
                "interface": "GigabitEthernet0/0",
                "ipv6": "2001:db8:1::1/64",
                "ospf_area": 5,
            }
        ],
        enable_routing=False,
    )
    assert not any(line.startswith(" ipv6 ospf") for line in lines)
    assert "ipv6 router ospf" not in " ".join(lines)


def test_ospf_area_skipped_for_interface_without_area():
    """An interface without ospf_area gets no OSPF line even when ospfv3 set."""
    lines = generate_ipv6_cli(
        [{"interface": "GigabitEthernet0/2", "ipv6": "2001:db8:3::1/64"}],
        enable_routing=False,
        ospfv3={"process_id": 2},
    )
    assert " ipv6 ospf 2 area 0" not in lines
    assert not any(line.startswith(" ipv6 ospf") for line in lines)


def test_router_ospf_block_with_router_id():
    """The OSPFv3 router block emits router-id then exit when router_id given."""
    lines = generate_ipv6_cli(
        [],
        enable_routing=False,
        ospfv3={"process_id": 10, "router_id": "1.1.1.1"},
    )
    assert lines == [
        "ipv6 router ospf 10",
        " router-id 1.1.1.1",
        " exit",
    ]


def test_router_ospf_block_without_router_id():
    """The router-id line is omitted when no router_id is provided."""
    lines = generate_ipv6_cli(
        [],
        enable_routing=False,
        ospfv3={"process_id": 10},
    )
    assert lines == [
        "ipv6 router ospf 10",
        " exit",
    ]


def test_no_router_block_without_ospfv3():
    """No `ipv6 router ospf` block when ospfv3 is None."""
    lines = generate_ipv6_cli(
        [{"interface": "GigabitEthernet0/0", "ipv6": "2001:db8:1::1/64"}],
    )
    assert not any(line.startswith("ipv6 router ospf") for line in lines)


def test_full_dual_stack_with_ospfv3_and_router_id():
    """End-to-end shape: routing + two interfaces + OSPFv3 router block."""
    lines = generate_ipv6_cli(
        [
            {
                "interface": "GigabitEthernet0/0",
                "ipv6": "2001:db8:1::1/64",
                "ospf_area": 0,
            },
            {"interface": "GigabitEthernet0/1", "ipv6": "2001:db8:2::1/64"},
        ],
        enable_routing=True,
        ospfv3={"process_id": 1, "router_id": "2.2.2.2"},
    )
    assert lines == [
        "ipv6 unicast-routing",
        "interface GigabitEthernet0/0",
        " ipv6 address 2001:db8:1::1/64",
        " ipv6 ospf 1 area 0",
        " no shutdown",
        " exit",
        "interface GigabitEthernet0/1",
        " ipv6 address 2001:db8:2::1/64",
        " no shutdown",
        " exit",
        "ipv6 router ospf 1",
        " router-id 2.2.2.2",
        " exit",
    ]
