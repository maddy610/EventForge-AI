"""Budget calculations, timeline date math, DataFrames, and export formatters."""

import io
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import streamlit as st

from config import (
    BUDGET_TOLERANCE_RATIO,
    CACHE_TTL_SECONDS,
    STAGE_DAYS_BEFORE_MAP,
)
from services.validators import EventPlan

logger = logging.getLogger(__name__)


def _resolve_days_before(stage_label: str, raw_days: int) -> int:
    """Resolve canonical days_before offset from stage label or raw integer."""
    normalized = stage_label.strip().lower()
    for label, days in STAGE_DAYS_BEFORE_MAP.items():
        if label.lower() == normalized:
            return days
    return max(0, int(raw_days))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def build_budget_dataframe(
    allocations_tuple: tuple[tuple[str, float, float, str], ...],
    total_budget: float,
) -> tuple[pd.DataFrame, bool, str | None]:
    """Validate and normalize budget allocations and return a Planned vs Actual DataFrame.

    Args:
        allocations_tuple: Hashable tuple of (category, amount, percentage, notes).
        total_budget: User's target total budget in INR.

    Returns:
        Tuple of (DataFrame, was_normalized, warning_message).
    """
    target = max(1.0, float(total_budget))
    raw_amounts = [max(0.0, float(row[1])) for row in allocations_tuple]
    raw_sum = sum(raw_amounts)
    diff = abs(raw_sum - target)
    diff_ratio = diff / target

    was_normalized = False
    warning_msg: str | None = None

    if raw_sum <= 0.0:
        equal_share = round(target / max(1, len(allocations_tuple)), 2)
        scaled = [equal_share for _ in allocations_tuple]
        scaled[-1] = round(target - sum(scaled[:-1]), 2)
        was_normalized = True
        warning_msg = "Allocations were zero and have been equally normalized to total budget."
    elif diff > 0.01:
        was_normalized = True
        scaled = [round((amt / raw_sum) * target, 2) for amt in raw_amounts]
        scaled[-1] = round(target - sum(scaled[:-1]), 2)
        if diff_ratio > BUDGET_TOLERANCE_RATIO:
            warning_msg = (
                f"Budget allocations summed to ₹{raw_sum:,.2f} "
                f"({diff_ratio * 100:.1f}% off target ₹{target:,.2f}); "
                "auto-normalized to 100% of total budget."
            )
        else:
            warning_msg = (
                f"Budget allocations were slightly off (₹{raw_sum:,.2f} vs ₹{target:,.2f}) "
                "within 1% tolerance and have been auto-normalized."
            )
    else:
        scaled = [round(amt, 2) for amt in raw_amounts]

    rows = []
    for idx, (category, _, _, notes) in enumerate(allocations_tuple):
        amt = scaled[idx]
        pct = round((amt / target) * 100.0, 2)
        rows.append(
            {
                "Category": category,
                "Planned (INR)": amt,
                "Share (%)": pct,
                "Actual (INR)": amt,
                "Notes": notes,
            }
        )
    return pd.DataFrame(rows), was_normalized, warning_msg


def summarize_planned_vs_actual(
    edited_df: pd.DataFrame,
    total_budget: float,
) -> dict[str, float | bool]:
    """Calculate totals, remaining budget, and over-budget status from edited table."""
    planned_total = (
        float(edited_df["Planned (INR)"].fillna(0.0).sum())
        if "Planned (INR)" in edited_df
        else 0.0
    )
    actual_total = (
        float(edited_df["Actual (INR)"].fillna(0.0).clip(lower=0.0).sum())
        if "Actual (INR)" in edited_df
        else 0.0
    )
    remaining = round(float(total_budget) - actual_total, 2)
    over_amount = round(max(0.0, actual_total - float(total_budget)), 2)
    return {
        "total_budget": round(float(total_budget), 2),
        "planned_total": round(planned_total, 2),
        "actual_total": round(actual_total, 2),
        "remaining_budget": remaining,
        "over_budget_amount": over_amount,
        "is_over_budget": actual_total > float(total_budget) + 0.005,
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def compute_active_timeline(
    timeline_tuple: tuple[tuple[str, int, tuple[str, ...]], ...],
    event_date_iso: str,
    reference_date_iso: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Compute calendar dates for T-minus stages and skip stages already in the past.

    Args:
        timeline_tuple: Hashable tuple of (stage_label, days_before, tasks_tuple).
        event_date_iso: Target event date in YYYY-MM-DD format.
        reference_date_iso: Optional today date in YYYY-MM-DD format for deterministic testing.

    Returns:
        Tuple of (active_stage_dicts_sorted_chronologically, skipped_past_count).
    """
    event_dt = date.fromisoformat(event_date_iso)
    today_dt = (
        date.fromisoformat(reference_date_iso)
        if reference_date_iso
        else date.today()
    )

    active: list[dict[str, Any]] = []
    skipped = 0

    for stage_label, raw_days, tasks in timeline_tuple:
        days_before = _resolve_days_before(stage_label, raw_days)
        stage_date = event_dt - timedelta(days=days_before)
        if stage_date < today_dt:
            skipped += 1
            continue
        days_from_today = (stage_date - today_dt).days
        active.append(
            {
                "stage": stage_label,
                "days_before": days_before,
                "target_date": stage_date.isoformat(),
                "formatted_date": stage_date.strftime("%d %b %Y"),
                "days_from_today": days_from_today,
                "tasks": list(tasks),
            }
        )

    active.sort(key=lambda item: item["days_before"], reverse=True)
    return active, skipped


def compute_vendor_progress(
    vendors: list[dict[str, Any]],
    checked_map: dict[str, bool],
) -> dict[str, float | int]:
    """Compute vendor checklist completion metrics without mutating state."""
    total_count = len(vendors)
    if total_count == 0:
        return {
            "completed_count": 0,
            "total_count": 0,
            "progress_ratio": 0.0,
            "booked_cost": 0.0,
            "total_estimated_cost": 0.0,
        }

    completed_count = 0
    booked_cost = 0.0
    total_cost = 0.0
    for vendor in vendors:
        vid = str(vendor.get("id", ""))
        cost = float(vendor.get("estimated_cost", 0.0))
        total_cost += cost
        if checked_map.get(vid, False):
            completed_count += 1
            booked_cost += cost

    return {
        "completed_count": completed_count,
        "total_count": total_count,
        "progress_ratio": round(completed_count / total_count, 4),
        "booked_cost": round(booked_cost, 2),
        "total_estimated_cost": round(total_cost, 2),
    }


def export_plan_to_csv(
    plan: EventPlan,
    budget_df: pd.DataFrame,
    checked_map: dict[str, bool],
) -> str:
    """Serialize budget allocations and vendor checklist to a unified CSV string."""
    buffer = io.StringIO()
    rows: list[dict[str, Any]] = []

    for _, row in budget_df.iterrows():
        rows.append(
            {
                "Section": "Budget",
                "Item / Category": str(row.get("Category", "")),
                "Planned (INR)": float(row.get("Planned (INR)", 0.0)),
                "Actual (INR)": float(row.get("Actual (INR)", 0.0)),
                "Priority / Share": f"{float(row.get('Share (%)', 0.0)):.1f}%",
                "Status": "Allocated",
                "Notes": str(row.get("Notes", "")),
            }
        )

    for vendor in plan.vendor_checklist:
        is_done = checked_map.get(vendor.id, False)
        rows.append(
            {
                "Section": "Vendor Checklist",
                "Item / Category": f"{vendor.vendor_name} ({vendor.category})",
                "Planned (INR)": vendor.estimated_cost,
                "Actual (INR)": vendor.estimated_cost if is_done else 0.0,
                "Priority / Share": vendor.priority,
                "Status": "Booked" if is_done else "Pending",
                "Notes": vendor.notes,
            }
        )

    pd.DataFrame(rows).to_csv(buffer, index=False)
    return buffer.getvalue()


def export_plan_to_markdown(
    plan: EventPlan,
    budget_df: pd.DataFrame,
    active_timeline: list[dict[str, Any]],
    checked_map: dict[str, bool],
) -> str:
    """Render the complete event plan as a clean Markdown document."""
    lines = [
        f"# {plan.event_type} Plan: {plan.vibe_theme}",
        "",
        f"- **Total Budget:** ₹{plan.total_budget:,.2f}",
        f"- **Guest Count:** {plan.guest_count}",
        f"- **City:** {plan.city}",
        "",
        f"## Summary\n{plan.event_summary}",
        "",
        "## Budget Allocations",
        "| Category | Planned (INR) | Actual (INR) | Share (%) | Notes |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for _, row in budget_df.iterrows():
        lines.append(
            f"| {row['Category']} | ₹{float(row['Planned (INR)']):,.2f} | "
            f"₹{float(row['Actual (INR)']):,.2f} | {float(row['Share (%)']):.1f}% | "
            f"{row['Notes']} |"
        )

    lines.extend(["", "## Timeline Milestones"])
    for stage in active_timeline:
        lines.append(f"### {stage['stage']} ({stage['formatted_date']})")
        for task in stage["tasks"]:
            lines.append(f"- {task}")

    lines.extend(["", "## Vendor Checklist"])
    for vendor in plan.vendor_checklist:
        mark = "x" if checked_map.get(vendor.id, False) else " "
        lines.append(
            f"- [{mark}] **{vendor.vendor_name}** ({vendor.category}) — "
            f"₹{vendor.estimated_cost:,.2f} [{vendor.priority} Priority]: {vendor.notes}"
        )

    ideas = plan.personalized_ideas
    lines.extend(
        [
            "",
            "## Personalized Ideas",
            "### Decor",
            *[f"- {item}" for item in ideas.decor],
            "### Food & Beverage",
            *[f"- {item}" for item in ideas.food],
            "### Entertainment",
            *[f"- {item}" for item in ideas.entertainment],
            "### Guest Activities",
            *[f"- {item}" for item in ideas.activities],
            "### Invitation Wording",
            f"> {ideas.invitation_wording}",
            "",
        ]
    )
    return "\n".join(lines)


def _escape_ics_text(value: str) -> str:
    """Escape special characters according to RFC 5545 iCalendar rules."""
    cleaned = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return cleaned.replace("\r\n", "\\n").replace("\n", "\\n")


def export_timeline_to_ics(
    plan: EventPlan,
    active_timeline: list[dict[str, Any]],
) -> str:
    """Generate an RFC 5545 .ics calendar file containing all active timeline stages."""
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EventForge AI//GenAI Event Planner//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for idx, stage in enumerate(active_timeline):
        start_dt = date.fromisoformat(stage["target_date"])
        end_dt = start_dt + timedelta(days=1)
        summary = _escape_ics_text(
            f"[{plan.event_type}] {stage['stage']} - {plan.vibe_theme}"
        )
        description = _escape_ics_text("Tasks:\n- " + "\n- ".join(stage["tasks"]))
        uid = f"eventforge-{start_dt.strftime('%Y%m%d')}-{idx}@eventforge.ai"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{start_dt.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end_dt.strftime('%Y%m%d')}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
