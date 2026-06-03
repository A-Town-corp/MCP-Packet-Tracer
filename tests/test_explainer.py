"""Tests for the Explainer."""

from packet_tracer_mcp.domain.models.requests import TopologyRequest
from packet_tracer_mcp.domain.services.orchestrator import plan_from_request
from packet_tracer_mcp.domain.services.explainer import explain_plan


class TestExplainer:
    def test_basic_explanation(self):
        req = TopologyRequest(routers=2, pcs_per_lan=2, dhcp=True)
        plan, _ = plan_from_request(req)
        explanations = explain_plan(plan)
        assert len(explanations) > 0
        assert any("router" in e.lower() for e in explanations)

    def test_dhcp_explained(self):
        req = TopologyRequest(routers=2, pcs_per_lan=2, dhcp=True)
        plan, _ = plan_from_request(req)
        explanations = explain_plan(plan)
        assert any("DHCP" in e for e in explanations)

    def test_wan_explained(self):
        req = TopologyRequest(routers=2, pcs_per_lan=2, has_wan=True)
        plan, _ = plan_from_request(req)
        explanations = explain_plan(plan)
        assert any("WAN" in e for e in explanations)
