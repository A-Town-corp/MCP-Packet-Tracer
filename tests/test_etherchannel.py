"""Unit tests for the EtherChannel / Port-channel IOS CLI generator."""

from __future__ import annotations

from packet_tracer_mcp.infrastructure.generator.etherchannel_cli_generator import (
    generate_etherchannel_cli,
)


class TestEtherChannelMembers:
    def test_each_member_joins_channel_group_in_order(self):
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1", "GigabitEthernet0/2"],
            channel_id=1,
            mode="active",
        )
        # First member block.
        assert lines[0] == "interface GigabitEthernet0/1"
        assert lines[1] == " channel-group 1 mode active"
        assert lines[2] == " exit"
        # Second member block.
        assert lines[3] == "interface GigabitEthernet0/2"
        assert lines[4] == " channel-group 1 mode active"
        assert lines[5] == " exit"

    def test_mode_is_emitted_verbatim(self):
        for mode in ("active", "passive", "desirable", "auto", "on"):
            lines = generate_etherchannel_cli(
                interfaces=["GigabitEthernet0/1"],
                channel_id=5,
                mode=mode,
            )
            assert f" channel-group 5 mode {mode}" in lines

    def test_member_blocks_end_with_exit_before_logical_interface(self):
        lines = generate_etherchannel_cli(
            interfaces=["Gig0/1"], channel_id=2, mode="on"
        )
        # The single member block precedes the logical interface.
        assert lines.index(" exit") < lines.index("interface Port-channel2")


class TestEtherChannelL2Trunk:
    def test_l2_trunk_full_block(self):
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=1,
            mode="active",
            layer="l2",
            trunk=True,
            allowed_vlans=[10, 20, 30],
            needs_encap=False,
        )
        assert "interface Port-channel1" in lines
        assert " switchport mode trunk" in lines
        assert " switchport trunk allowed vlan 10,20,30" in lines
        assert lines[-1] == " exit"

    def test_trunk_order_encap_before_mode(self):
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=1,
            trunk=True,
            needs_encap=True,
        )
        encap_i = lines.index(" switchport trunk encapsulation dot1q")
        mode_i = lines.index(" switchport mode trunk")
        assert encap_i < mode_i

    def test_no_allowed_vlans_omits_allowed_line(self):
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=1,
            trunk=True,
            allowed_vlans=None,
        )
        assert not any(l.startswith(" switchport trunk allowed vlan") for l in lines)


class TestEncapsulationBehavior:
    def test_2960_dot1q_only_no_encapsulation(self):
        # needs_encap=False models a 2960 trunk: it must NOT emit the encap line.
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=1,
            trunk=True,
            needs_encap=False,
        )
        assert " switchport trunk encapsulation dot1q" not in lines
        assert " switchport mode trunk" in lines

    def test_3560_multilayer_emits_encapsulation(self):
        # needs_encap=True models a 3560/3650 multilayer trunk.
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=1,
            trunk=True,
            needs_encap=True,
        )
        assert " switchport trunk encapsulation dot1q" in lines
        assert " switchport mode trunk" in lines


class TestEtherChannelL2Access:
    def test_l2_access_block(self):
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=3,
            layer="l2",
            trunk=False,
            access_vlan=99,
        )
        assert "interface Port-channel3" in lines
        assert " switchport mode access" in lines
        assert " switchport access vlan 99" in lines
        # No trunk artifacts on an access port.
        assert " switchport mode trunk" not in lines
        assert " switchport trunk encapsulation dot1q" not in lines

    def test_access_without_vlan_omits_access_vlan_line(self):
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=3,
            trunk=False,
            access_vlan=None,
        )
        assert " switchport mode access" in lines
        assert not any(l.startswith(" switchport access vlan") for l in lines)


class TestEtherChannelL3:
    def test_l3_emits_no_switchport(self):
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1", "GigabitEthernet0/2"],
            channel_id=4,
            mode="active",
            layer="l3",
        )
        assert "interface Port-channel4" in lines
        assert " no switchport" in lines
        # An L3 routed bundle has no switchport mode commands.
        assert " switchport mode trunk" not in lines
        assert " switchport mode access" not in lines
        assert lines[-1] == " exit"

    def test_l3_ignores_trunk_and_encap_flags(self):
        # Even with trunk/needs_encap set, an L3 bundle stays routed.
        lines = generate_etherchannel_cli(
            interfaces=["GigabitEthernet0/1"],
            channel_id=4,
            layer="l3",
            trunk=True,
            needs_encap=True,
        )
        assert " no switchport" in lines
        assert " switchport trunk encapsulation dot1q" not in lines
        assert " switchport mode trunk" not in lines
