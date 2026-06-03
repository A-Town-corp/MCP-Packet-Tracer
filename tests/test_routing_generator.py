"""Unit tests for the routing protocol IOS-CLI generators (OSPF, RIP, EIGRP, BGP)."""

import pytest

from packet_tracer_mcp.infrastructure.generator.routing_cli_generator import (
    generate_bgp_cli,
    generate_eigrp_cli,
    generate_ospf_cli,
    generate_rip_cli,
)


# ---------------------------------------------------------------------------
# OSPF
# ---------------------------------------------------------------------------

class TestGenerateOspfCli:
    """Tests for generate_ospf_cli."""

    def _single_net(self):
        return [{"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0}]

    def test_basic_block_structure(self):
        """Block starts with router ospf and ends with ' exit'."""
        lines = generate_ospf_cli(1, self._single_net())
        assert lines[0] == "router ospf 1"
        assert lines[-1] == " exit"

    def test_single_network_in_output(self):
        """A single network entry is emitted correctly."""
        lines = generate_ospf_cli(1, self._single_net())
        assert " network 10.0.0.0 0.0.0.255 area 0" in lines

    def test_router_id_emitted_before_networks(self):
        """router-id line appears before the first network line."""
        lines = generate_ospf_cli(1, self._single_net(), router_id="1.1.1.1")
        rid_idx = lines.index(" router-id 1.1.1.1")
        net_idx = lines.index(" network 10.0.0.0 0.0.0.255 area 0")
        assert rid_idx < net_idx

    def test_router_id_omitted_when_none(self):
        """No router-id line when router_id is None."""
        lines = generate_ospf_cli(1, self._single_net())
        assert not any("router-id" in l for l in lines)

    def test_multiple_networks_order_preserved(self):
        """Multiple networks appear in input order."""
        networks = [
            {"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0},
            {"network": "172.16.0.0", "wildcard": "0.0.255.255", "area": 1},
        ]
        lines = generate_ospf_cli(1, networks)
        idx0 = lines.index(" network 10.0.0.0 0.0.0.255 area 0")
        idx1 = lines.index(" network 172.16.0.0 0.0.255.255 area 1")
        assert idx0 < idx1

    def test_passive_interface_emitted(self):
        """passive-interface lines are present when requested."""
        lines = generate_ospf_cli(
            1, self._single_net(), passive_interfaces=["GigabitEthernet0/1"]
        )
        assert " passive-interface GigabitEthernet0/1" in lines

    def test_default_information_originate(self):
        """default-information originate is emitted when requested."""
        lines = generate_ospf_cli(1, self._single_net(), default_originate=True)
        assert " default-information originate" in lines

    def test_default_information_originate_omitted_by_default(self):
        """default-information originate is absent when not requested."""
        lines = generate_ospf_cli(1, self._single_net())
        assert " default-information originate" not in lines

    def test_area_as_string(self):
        """Area can be a string (backbone named area)."""
        networks = [{"network": "192.168.1.0", "wildcard": "0.0.0.255", "area": "10"}]
        lines = generate_ospf_cli(1, networks)
        assert " network 192.168.1.0 0.0.0.255 area 10" in lines

    def test_sub_commands_single_leading_space(self):
        """Every sub-command carries exactly one leading space."""
        lines = generate_ospf_cli(
            1,
            self._single_net(),
            router_id="1.1.1.1",
            passive_interfaces=["Lo0"],
            default_originate=True,
        )
        for line in lines[1:]:
            assert line.startswith(" "), f"Expected leading space: {line!r}"
            assert not line.startswith("  "), f"Unexpected double space: {line!r}"

    def test_invalid_process_id_zero(self):
        """process_id of 0 raises ValueError."""
        with pytest.raises(ValueError):
            generate_ospf_cli(0, self._single_net())

    def test_invalid_process_id_negative(self):
        """Negative process_id raises ValueError."""
        with pytest.raises(ValueError):
            generate_ospf_cli(-1, self._single_net())

    def test_invalid_process_id_string(self):
        """A string process_id raises ValueError."""
        with pytest.raises(ValueError):
            generate_ospf_cli("1", self._single_net())  # type: ignore[arg-type]

    def test_empty_networks_raises(self):
        """Empty networks list raises ValueError."""
        with pytest.raises(ValueError):
            generate_ospf_cli(1, [])

    def test_missing_network_key_raises(self):
        """A network dict missing 'wildcard' raises ValueError."""
        with pytest.raises(ValueError):
            generate_ospf_cli(1, [{"network": "10.0.0.0", "area": 0}])

    def test_missing_area_key_raises(self):
        """A network dict missing 'area' raises ValueError."""
        with pytest.raises(ValueError):
            generate_ospf_cli(1, [{"network": "10.0.0.0", "wildcard": "0.0.0.255"}])

    def test_full_block_exact_output(self):
        """Full block with all options matches expected output exactly."""
        networks = [
            {"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0},
            {"network": "10.1.0.0", "wildcard": "0.0.0.255", "area": 1},
        ]
        lines = generate_ospf_cli(
            10,
            networks,
            router_id="10.10.10.10",
            passive_interfaces=["GigabitEthernet0/2"],
            default_originate=True,
        )
        assert lines == [
            "router ospf 10",
            " router-id 10.10.10.10",
            " network 10.0.0.0 0.0.0.255 area 0",
            " network 10.1.0.0 0.0.0.255 area 1",
            " passive-interface GigabitEthernet0/2",
            " default-information originate",
            " exit",
        ]


# ---------------------------------------------------------------------------
# RIP
# ---------------------------------------------------------------------------

class TestGenerateRipCli:
    """Tests for generate_rip_cli."""

    def test_basic_block_structure(self):
        """Block starts with 'router rip' and ends with ' exit'."""
        lines = generate_rip_cli(["10.0.0.0"])
        assert lines[0] == "router rip"
        assert lines[-1] == " exit"

    def test_version_line_present(self):
        """Version line is emitted as first sub-command."""
        lines = generate_rip_cli(["10.0.0.0"], version=2)
        assert lines[1] == " version 2"

    def test_version_1(self):
        """Version 1 is accepted and emitted."""
        lines = generate_rip_cli(["10.0.0.0"], version=1)
        assert " version 1" in lines

    def test_network_lines_emitted(self):
        """Each network address is emitted as a sub-command."""
        lines = generate_rip_cli(["10.0.0.0", "192.168.1.0"])
        assert " network 10.0.0.0" in lines
        assert " network 192.168.1.0" in lines

    def test_no_auto_summary_default(self):
        """no auto-summary is emitted by default."""
        lines = generate_rip_cli(["10.0.0.0"])
        assert " no auto-summary" in lines

    def test_no_auto_summary_suppressed(self):
        """no auto-summary is absent when no_auto_summary=False."""
        lines = generate_rip_cli(["10.0.0.0"], no_auto_summary=False)
        assert " no auto-summary" not in lines

    def test_passive_interface(self):
        """passive-interface lines are emitted when provided."""
        lines = generate_rip_cli(["10.0.0.0"], passive_interfaces=["Serial0/0/0"])
        assert " passive-interface Serial0/0/0" in lines

    def test_default_information_originate(self):
        """default-information originate is emitted when requested."""
        lines = generate_rip_cli(["10.0.0.0"], default_originate=True)
        assert " default-information originate" in lines

    def test_default_information_originate_absent_by_default(self):
        """default-information originate is absent by default."""
        lines = generate_rip_cli(["10.0.0.0"])
        assert " default-information originate" not in lines

    def test_sub_commands_single_leading_space(self):
        """Every sub-command has exactly one leading space."""
        lines = generate_rip_cli(
            ["10.0.0.0", "172.16.0.0"],
            passive_interfaces=["Lo0"],
            default_originate=True,
        )
        for line in lines[1:]:
            assert line.startswith(" "), f"Expected leading space: {line!r}"
            assert not line.startswith("  "), f"Unexpected double space: {line!r}"

    def test_empty_networks_raises(self):
        """Empty networks list raises ValueError."""
        with pytest.raises(ValueError):
            generate_rip_cli([])

    def test_invalid_version_raises(self):
        """Version 3 raises ValueError."""
        with pytest.raises(ValueError):
            generate_rip_cli(["10.0.0.0"], version=3)

    def test_full_block_exact_output(self):
        """Full block matches expected exact output."""
        lines = generate_rip_cli(
            ["10.0.0.0", "192.168.0.0"],
            version=2,
            no_auto_summary=True,
            passive_interfaces=["GigabitEthernet0/1"],
            default_originate=True,
        )
        assert lines == [
            "router rip",
            " version 2",
            " network 10.0.0.0",
            " network 192.168.0.0",
            " no auto-summary",
            " passive-interface GigabitEthernet0/1",
            " default-information originate",
            " exit",
        ]


# ---------------------------------------------------------------------------
# EIGRP
# ---------------------------------------------------------------------------

class TestGenerateEigrpCli:
    """Tests for generate_eigrp_cli."""

    def test_basic_block_structure(self):
        """Block starts with 'router eigrp' and ends with ' exit'."""
        lines = generate_eigrp_cli(100, ["10.0.0.0"])
        assert lines[0] == "router eigrp 100"
        assert lines[-1] == " exit"

    def test_plain_string_network(self):
        """A plain network string emits 'network {net}'."""
        lines = generate_eigrp_cli(100, ["10.0.0.0"])
        assert " network 10.0.0.0" in lines

    def test_dict_network_with_wildcard(self):
        """A dict network emits 'network {network} {wildcard}'."""
        lines = generate_eigrp_cli(100, [{"network": "10.0.0.0", "wildcard": "0.0.0.255"}])
        assert " network 10.0.0.0 0.0.0.255" in lines

    def test_mixed_network_types(self):
        """Plain strings and dicts can be mixed in the networks list."""
        networks = [
            "192.168.1.0",
            {"network": "10.0.0.0", "wildcard": "0.0.0.255"},
        ]
        lines = generate_eigrp_cli(100, networks)
        assert " network 192.168.1.0" in lines
        assert " network 10.0.0.0 0.0.0.255" in lines

    def test_router_id_emitted(self):
        """eigrp router-id is emitted when provided."""
        lines = generate_eigrp_cli(100, ["10.0.0.0"], router_id="2.2.2.2")
        assert " eigrp router-id 2.2.2.2" in lines

    def test_router_id_omitted_when_none(self):
        """No router-id line when router_id is None."""
        lines = generate_eigrp_cli(100, ["10.0.0.0"])
        assert not any("router-id" in l for l in lines)

    def test_no_auto_summary_default(self):
        """no auto-summary is emitted by default."""
        lines = generate_eigrp_cli(100, ["10.0.0.0"])
        assert " no auto-summary" in lines

    def test_no_auto_summary_suppressed(self):
        """no auto-summary is absent when no_auto_summary=False."""
        lines = generate_eigrp_cli(100, ["10.0.0.0"], no_auto_summary=False)
        assert " no auto-summary" not in lines

    def test_passive_interface(self):
        """passive-interface lines are emitted when provided."""
        lines = generate_eigrp_cli(100, ["10.0.0.0"], passive_interfaces=["Lo0"])
        assert " passive-interface Lo0" in lines

    def test_sub_commands_single_leading_space(self):
        """Every sub-command has exactly one leading space."""
        lines = generate_eigrp_cli(
            100,
            ["10.0.0.0", {"network": "172.16.0.0", "wildcard": "0.0.255.255"}],
            router_id="3.3.3.3",
            passive_interfaces=["Serial0/0/0"],
        )
        for line in lines[1:]:
            assert line.startswith(" "), f"Expected leading space: {line!r}"
            assert not line.startswith("  "), f"Unexpected double space: {line!r}"

    def test_invalid_as_number_zero(self):
        """as_number of 0 raises ValueError."""
        with pytest.raises(ValueError):
            generate_eigrp_cli(0, ["10.0.0.0"])

    def test_invalid_as_number_too_large(self):
        """as_number > 65535 raises ValueError."""
        with pytest.raises(ValueError):
            generate_eigrp_cli(65536, ["10.0.0.0"])

    def test_invalid_as_number_negative(self):
        """Negative as_number raises ValueError."""
        with pytest.raises(ValueError):
            generate_eigrp_cli(-1, ["10.0.0.0"])

    def test_empty_networks_raises(self):
        """Empty networks list raises ValueError."""
        with pytest.raises(ValueError):
            generate_eigrp_cli(100, [])

    def test_full_block_exact_output(self):
        """Full block matches expected exact output."""
        lines = generate_eigrp_cli(
            200,
            [
                {"network": "10.0.0.0", "wildcard": "0.0.0.255"},
                "192.168.1.0",
            ],
            no_auto_summary=True,
            router_id="2.2.2.2",
            passive_interfaces=["GigabitEthernet0/2"],
        )
        assert lines == [
            "router eigrp 200",
            " eigrp router-id 2.2.2.2",
            " network 10.0.0.0 0.0.0.255",
            " network 192.168.1.0",
            " no auto-summary",
            " passive-interface GigabitEthernet0/2",
            " exit",
        ]


# ---------------------------------------------------------------------------
# BGP
# ---------------------------------------------------------------------------

class TestGenerateBgpCli:
    """Tests for generate_bgp_cli."""

    def _neighbor(self, ip="10.0.0.2", remote_as=65002, description=None):
        nbr = {"ip": ip, "remote_as": remote_as}
        if description is not None:
            nbr["description"] = description
        return nbr

    def _network(self, network="192.168.1.0", mask="255.255.255.0"):
        return {"network": network, "mask": mask}

    def test_basic_block_structure_with_neighbor(self):
        """Block starts with 'router bgp' and ends with ' exit'."""
        lines = generate_bgp_cli(65001, neighbors=[self._neighbor()])
        assert lines[0] == "router bgp 65001"
        assert lines[-1] == " exit"

    def test_neighbor_remote_as_emitted(self):
        """neighbor remote-as line is emitted for each neighbor."""
        lines = generate_bgp_cli(65001, neighbors=[self._neighbor()])
        assert " neighbor 10.0.0.2 remote-as 65002" in lines

    def test_neighbor_description_emitted_when_present(self):
        """neighbor description line is emitted when provided."""
        lines = generate_bgp_cli(
            65001,
            neighbors=[self._neighbor(description="ISP_PEER")],
        )
        assert " neighbor 10.0.0.2 description ISP_PEER" in lines

    def test_neighbor_description_omitted_when_absent(self):
        """No description line when description is not provided."""
        lines = generate_bgp_cli(65001, neighbors=[self._neighbor()])
        assert not any("description" in l for l in lines)

    def test_neighbor_description_after_remote_as(self):
        """description line immediately follows the remote-as line."""
        lines = generate_bgp_cli(
            65001,
            neighbors=[self._neighbor(description="PEER")],
        )
        ra_idx = lines.index(" neighbor 10.0.0.2 remote-as 65002")
        desc_idx = lines.index(" neighbor 10.0.0.2 description PEER")
        assert desc_idx == ra_idx + 1

    def test_network_mask_keyword_used(self):
        """BGP network lines use the 'mask' keyword, not 'wildcard'."""
        lines = generate_bgp_cli(65001, networks=[self._network()])
        assert " network 192.168.1.0 mask 255.255.255.0" in lines

    def test_router_id_emitted(self):
        """bgp router-id is emitted when provided."""
        lines = generate_bgp_cli(
            65001, router_id="1.1.1.1", neighbors=[self._neighbor()]
        )
        assert " bgp router-id 1.1.1.1" in lines

    def test_router_id_before_neighbors(self):
        """bgp router-id appears before neighbor lines."""
        lines = generate_bgp_cli(
            65001, router_id="1.1.1.1", neighbors=[self._neighbor()]
        )
        rid_idx = lines.index(" bgp router-id 1.1.1.1")
        nbr_idx = lines.index(" neighbor 10.0.0.2 remote-as 65002")
        assert rid_idx < nbr_idx

    def test_router_id_omitted_when_none(self):
        """No router-id line when router_id is None."""
        lines = generate_bgp_cli(65001, neighbors=[self._neighbor()])
        assert not any("router-id" in l for l in lines)

    def test_multiple_neighbors_order_preserved(self):
        """Multiple neighbors appear in input order."""
        neighbors = [
            self._neighbor("10.0.0.2", 65002),
            self._neighbor("10.0.0.3", 65003),
        ]
        lines = generate_bgp_cli(65001, neighbors=neighbors)
        idx2 = lines.index(" neighbor 10.0.0.2 remote-as 65002")
        idx3 = lines.index(" neighbor 10.0.0.3 remote-as 65003")
        assert idx2 < idx3

    def test_networks_only_no_neighbors(self):
        """Networks-only config (no neighbors) is valid."""
        lines = generate_bgp_cli(65001, networks=[self._network()])
        assert " network 192.168.1.0 mask 255.255.255.0" in lines

    def test_sub_commands_single_leading_space(self):
        """Every sub-command has exactly one leading space."""
        lines = generate_bgp_cli(
            65001,
            router_id="1.1.1.1",
            neighbors=[self._neighbor(description="PEER")],
            networks=[self._network()],
        )
        for line in lines[1:]:
            assert line.startswith(" "), f"Expected leading space: {line!r}"
            assert not line.startswith("  "), f"Unexpected double space: {line!r}"

    def test_invalid_as_number_zero(self):
        """as_number of 0 raises ValueError."""
        with pytest.raises(ValueError):
            generate_bgp_cli(0, neighbors=[self._neighbor()])

    def test_invalid_as_number_too_large(self):
        """as_number > 65535 raises ValueError."""
        with pytest.raises(ValueError):
            generate_bgp_cli(65536, neighbors=[self._neighbor()])

    def test_no_neighbors_no_networks_raises(self):
        """Omitting both neighbors and networks raises ValueError."""
        with pytest.raises(ValueError):
            generate_bgp_cli(65001)

    def test_empty_neighbors_and_empty_networks_raises(self):
        """Passing empty lists for both raises ValueError."""
        with pytest.raises(ValueError):
            generate_bgp_cli(65001, neighbors=[], networks=[])

    def test_full_block_exact_output(self):
        """Full block matches expected exact output."""
        lines = generate_bgp_cli(
            65001,
            router_id="1.1.1.1",
            neighbors=[
                {"ip": "10.0.0.2", "remote_as": 65002, "description": "ISP"},
                {"ip": "10.0.0.3", "remote_as": 65003},
            ],
            networks=[
                {"network": "192.168.1.0", "mask": "255.255.255.0"},
                {"network": "10.0.0.0", "mask": "255.0.0.0"},
            ],
        )
        assert lines == [
            "router bgp 65001",
            " bgp router-id 1.1.1.1",
            " neighbor 10.0.0.2 remote-as 65002",
            " neighbor 10.0.0.2 description ISP",
            " neighbor 10.0.0.3 remote-as 65003",
            " network 192.168.1.0 mask 255.255.255.0",
            " network 10.0.0.0 mask 255.0.0.0",
            " exit",
        ]
