"""Tests for the IP Planner."""

import pytest
from packet_tracer_mcp.domain.services.ip_planner import IPPlanner


class TestIPPlanner:
    def test_next_lan_subnet(self):
        planner = IPPlanner("192.168.0.0/16", "10.0.0.0/16")
        subnet = planner.next_lan_subnet()
        assert str(subnet) == "192.168.0.0/24"

    def test_sequential_lan_subnets(self):
        planner = IPPlanner("192.168.0.0/16", "10.0.0.0/16")
        s0 = planner.next_lan_subnet()
        s1 = planner.next_lan_subnet()
        assert str(s0) == "192.168.0.0/24"
        assert str(s1) == "192.168.1.0/24"

    def test_next_link_subnet(self):
        planner = IPPlanner("192.168.0.0/16", "10.0.0.0/16")
        subnet = planner.next_link_subnet()
        assert str(subnet) == "10.0.0.0/30"

    def test_multiple_link_subnets(self):
        planner = IPPlanner("192.168.0.0/16", "10.0.0.0/16")
        s0 = planner.next_link_subnet()
        s1 = planner.next_link_subnet()
        assert str(s0) == "10.0.0.0/30"
        assert str(s1) == "10.0.0.4/30"

    def test_link_subnet_hosts(self):
        planner = IPPlanner("192.168.0.0/16", "10.0.0.0/16")
        subnet = planner.next_link_subnet()
        hosts = list(subnet.hosts())
        assert str(hosts[0]) == "10.0.0.1"
        assert str(hosts[1]) == "10.0.0.2"

    def test_lan_subnet_gateway(self):
        planner = IPPlanner("192.168.0.0/16", "10.0.0.0/16")
        subnet = planner.next_lan_subnet()
        hosts = list(subnet.hosts())
        assert str(hosts[0]) == "192.168.0.1"  # gateway
