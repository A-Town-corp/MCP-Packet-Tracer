"""Use case: generate CLI configurations."""

from __future__ import annotations
from ...domain.models.plans import TopologyPlan
from ...infrastructure.generator.cli_config_generator import generate_all_configs


def generate_configs_uc(plan: TopologyPlan) -> dict[str, str]:
    """Generate CLI configurations per device."""
    return generate_all_configs(plan)
