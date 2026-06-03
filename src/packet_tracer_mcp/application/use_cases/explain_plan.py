"""Use case: explain plan."""

from __future__ import annotations
from ...domain.models.plans import TopologyPlan
from ...domain.services.explainer import explain_plan


def explain_plan_uc(plan: TopologyPlan) -> list[str]:
    """Generate explanations of the plan."""
    return explain_plan(plan)
