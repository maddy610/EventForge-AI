"""Unit tests for offline fallback templates across all three event types."""

import pytest

from config import EVENT_TYPES
from services.fallback import load_fallback_plan


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_load_fallback_plan_all_event_types(event_type: str) -> None:
    """Verify Wedding, Birthday, and Community Event templates load and scale properly."""
    target_budget = 350000.0
    plan = load_fallback_plan(
        event_type=event_type,
        total_budget=target_budget,
        guest_count=150,
        vibe_theme="Custom Festive Theme",
        city="Coimbatore",
        refinement_note="add a kids section",
    )
    assert plan.event_type == event_type
    assert plan.total_budget == target_budget
    assert plan.guest_count == 150
    assert plan.city == "Coimbatore"
    assert "Custom Festive Theme" in plan.vibe_theme
    assert "add a kids section" in plan.event_summary

    allocated_sum = round(
        sum(item.allocated_amount for item in plan.budget_allocations), 2
    )
    assert allocated_sum == pytest.approx(target_budget, abs=0.01)
    assert len(plan.timeline) >= 5
    assert len(plan.vendor_checklist) >= 4


def test_load_fallback_plan_unknown_event_type_defaults_safely() -> None:
    """Verify an unknown event type gracefully falls back to Wedding template."""
    plan = load_fallback_plan(
        event_type="Unknown Event",
        total_budget=120000.0,
        guest_count=80,
        vibe_theme="Classic Gathering",
        city="",
    )
    assert plan.event_type == "Wedding"
    assert plan.city == "Not specified"
    assert plan.total_budget == 120000.0
