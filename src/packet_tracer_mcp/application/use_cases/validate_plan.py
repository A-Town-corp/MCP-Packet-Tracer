"""Use case: validate plan."""

from __future__ import annotations
from ...domain.models.plans import TopologyPlan
from ...domain.services.validator import validate_plan
from ..dto.responses import ValidationResponse


def validate_plan_uc(plan: TopologyPlan) -> ValidationResponse:
    """Validate a plan and return the result."""
    result = validate_plan(plan)
    return ValidationResponse(
        is_valid=result.is_valid,
        errors=[e.to_dict() for e in result.errors],
        warnings=[w.to_dict() for w in result.warnings],
    )
