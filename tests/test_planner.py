"""Unit tests for budget normalization, timeline math, vendor progress, and exports."""

from typing import Any

import pandas as pd
import pytest

from services.planner import (
    build_budget_dataframe,
    compute_active_timeline,
    compute_vendor_progress,
    export_plan_to_csv,
    export_plan_to_markdown,
    export_timeline_to_ics,
    summarize_planned_vs_actual,
)
from services.validators import validate_event_plan_payload


def test_build_budget_dataframe_exact_sum() -> None:
    """Verify allocations matching total budget are not flagged as normalized."""
    allocs = (
        ("Venue", 50000.0, 50.0, "Hall"),
        ("Catering", 30000.0, 30.0, "Food"),
        ("Decor", 20000.0, 20.0, "Flowers"),
    )
    df, was_normalized, warning = build_budget_dataframe(allocs, 100000.0)
    assert not was_normalized
    assert warning is None
    assert df["Planned (INR)"].sum() == pytest.approx(100000.0, abs=0.01)


def test_build_budget_dataframe_normalizes_minor_and_major_drift() -> None:
    """Verify both <1% drift and >1% drift auto-normalize to total budget and warn."""
    minor_drift = (
        ("Venue", 50000.0, 50.0, "Hall"),
        ("Catering", 30000.0, 30.0, "Food"),
        ("Decor", 19500.0, 19.5, "Flowers"),
    )
    df_minor, norm_minor, warn_minor = build_budget_dataframe(minor_drift, 100000.0)
    assert norm_minor is True
    assert warn_minor is not None
    assert "within 1% tolerance" in warn_minor
    assert df_minor["Planned (INR)"].sum() == pytest.approx(100000.0, abs=0.01)

    major_drift = (
        ("Venue", 40000.0, 40.0, "Hall"),
        ("Catering", 20000.0, 20.0, "Food"),
        ("Decor", 20000.0, 20.0, "Flowers"),
    )
    df_major, norm_major, warn_major = build_budget_dataframe(major_drift, 100000.0)
    assert norm_major is True
    assert warn_major is not None
    assert "auto-normalized" in warn_major
    assert df_major["Planned (INR)"].sum() == pytest.approx(100000.0, abs=0.01)


def test_build_budget_dataframe_zero_sum_edge_case() -> None:
    """Verify zero allocations are equally normalized without division by zero."""
    zero_allocs = (
        ("Venue", 0.0, 0.0, ""),
        ("Catering", 0.0, 0.0, ""),
    )
    df, was_normalized, warning = build_budget_dataframe(zero_allocs, 50000.0)
    assert was_normalized is True
    assert warning is not None
    assert df["Planned (INR)"].sum() == pytest.approx(50000.0, abs=0.01)


def test_summarize_planned_vs_actual_detects_over_budget() -> None:
    """Verify Planned vs Actual summary flags over-budget condition accurately."""
    df = pd.DataFrame(
        {
            "Category": ["Venue", "Food"],
            "Planned (INR)": [60000.0, 40000.0],
            "Actual (INR)": [75000.0, 45000.0],
        }
    )
    summary = summarize_planned_vs_actual(df, 100000.0)
    assert summary["is_over_budget"] is True
    assert summary["over_budget_amount"] == 20000.0
    assert summary["remaining_budget"] == -20000.0


def test_compute_active_timeline_skips_past_stages() -> None:
    """Verify stages before reference_date are skipped and remaining stages are sorted."""
    timeline = (
        ("6 months out", 180, ("Book hall",)),
        ("3 months out", 90, ("Confirm menu",)),
        ("1 month out", 30, ("Send invites",)),
        ("1 week out", 7, ("Reconfirm vendors",)),
        ("Event day", 0, ("Host event",)),
    )
    # Event is 45 days after reference date -> 180 and 90 days out are in the past
    active, skipped = compute_active_timeline(
        timeline_tuple=timeline,
        event_date_iso="2026-12-15",
        reference_date_iso="2026-10-31",
    )
    assert skipped == 2
    assert [s["stage"] for s in active] == [
        "1 month out",
        "1 week out",
        "Event day",
    ]
    assert active[0]["target_date"] == "2026-11-15"
    assert active[-1]["target_date"] == "2026-12-15"


def test_compute_vendor_progress_metrics() -> None:
    """Verify vendor completion counts, ratio, and booked cost calculation."""
    vendors = [
        {"id": "v1", "estimated_cost": 30000.0},
        {"id": "v2", "estimated_cost": 20000.0},
    ]
    metrics = compute_vendor_progress(vendors, {"v1": True, "v2": False})
    assert metrics["completed_count"] == 1
    assert metrics["total_count"] == 2
    assert metrics["progress_ratio"] == 0.5
    assert metrics["booked_cost"] == 30000.0
    assert metrics["total_estimated_cost"] == 50000.0

    empty_metrics = compute_vendor_progress([], {})
    assert empty_metrics["total_count"] == 0


def test_exports_csv_markdown_and_ics(sample_valid_plan_dict: dict[str, Any]) -> None:
    """Verify CSV, Markdown, and RFC 5545 ICS calendar export outputs."""
    plan = validate_event_plan_payload(sample_valid_plan_dict)
    allocs = tuple(
        (b.category, b.allocated_amount, b.percentage, b.notes)
        for b in plan.budget_allocations
    )
    df, _, _ = build_budget_dataframe(allocs, plan.total_budget)
    timeline_tuple = tuple(
        (t.stage, t.days_before, tuple(t.tasks)) for t in plan.timeline
    )
    active_stages, _ = compute_active_timeline(
        timeline_tuple,
        event_date_iso="2027-06-01",
        reference_date_iso="2026-10-27",
    )
    checked = {"v_venue": True, "v_cake": False, "v_dj": True}

    csv_text = export_plan_to_csv(plan, df, checked)
    assert "Venue & Neon Decor" in csv_text
    assert "Neon Loft Venue" in csv_text
    assert "Booked" in csv_text

    md_text = export_plan_to_markdown(plan, df, active_stages, checked)
    assert "# Birthday Plan: Cyberpunk Birthday" in md_text
    assert "- [x] **Neon Loft Venue**" in md_text
    assert "Jack in to the grid" in md_text

    ics_text = export_timeline_to_ics(plan, active_stages)
    assert "BEGIN:VCALENDAR" in ics_text
    assert "END:VCALENDAR" in ics_text
    assert ics_text.count("BEGIN:VEVENT") == len(active_stages)
    assert "SUMMARY:[Birthday] 6 months out - Cyberpunk Birthday" in ics_text
