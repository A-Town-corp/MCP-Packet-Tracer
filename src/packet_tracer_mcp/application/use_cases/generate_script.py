"""Use case: generate PTBuilder script."""

from __future__ import annotations
from ...domain.models.plans import TopologyPlan
from ...infrastructure.generator.ptbuilder_generator import (
    generate_ptbuilder_script,
    generate_full_script,
)


def generate_script_uc(plan: TopologyPlan, include_configs: bool = True) -> str:
    """Generate the PTBuilder script."""
    if include_configs:
        return generate_full_script(plan)
    return generate_ptbuilder_script(plan)
