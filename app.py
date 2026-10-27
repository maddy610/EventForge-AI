"""Streamlit UI entry point for EventForge AI."""

from datetime import date, timedelta
import logging
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from config import (
    APP_ICON,
    APP_TAGLINE,
    APP_TITLE,
    BUDGET_STEP_INR,
    COLORBLIND_SAFE_PALETTE,
    DEFAULT_BUDGET_INR,
    DEFAULT_DAYS_AHEAD,
    DEFAULT_GUEST_COUNT,
    EVENT_TYPE_FOCUS,
    EVENT_TYPES,
    MAX_BUDGET_INR,
    MAX_GUEST_COUNT,
    MAX_INPUT_LENGTH,
    MAX_REFINEMENTS,
    MIN_BUDGET_INR,
    MIN_GUEST_COUNT,
)
from services.gemini_client import generate_event_plan
from services.planner import (
    build_budget_dataframe,
    compute_active_timeline,
    compute_vendor_progress,
    export_plan_to_csv,
    export_plan_to_markdown,
    export_timeline_to_ics,
    summarize_planned_vs_actual,
)
from services.validators import EventPlan, sanitize_input, validate_event_plan_payload

st.set_page_config(
    page_title=f"{APP_TITLE} — GenAI Event Planning Assistant",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def init_session_state() -> None:
    """Initialize required Streamlit session state keys with safe defaults."""
    defaults: dict[str, Any] = {
        "plan_data": None,
        "is_fallback": False,
        "fallback_reason": None,
        "event_date_iso": (date.today() + timedelta(days=DEFAULT_DAYS_AHEAD)).isoformat(),
        "refinement_history": (),
        "refinement_count": 0,
    }
    for key, default_val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val


def render_sidebar() -> None:
    """Render sidebar with 'How to use' guide and session status."""
    with st.sidebar:
        st.header("How to use")
        st.markdown(
            "1. **Select Event Details:** Choose your event type, total INR budget, "
            "guest count, event date, optional city, and a creative Vibe/Theme.\n"
            "2. **Generate Plan:** Click **Generate Event Plan** to build your "
            "structured budget, countdown timeline, vendor checklist, and ideas.\n"
            "3. **Track & Adjust:** Edit actual spend in the **Planned vs Actual** "
            "table and check off vendors as you book them.\n"
            "4. **Refine (up to 5x):** Use the **Refine your plan** assistant box "
            "to tailor the plan further.\n"
            "5. **Export:** Download your plan as CSV, Markdown, or an `.ics` calendar file."
        )
        st.divider()
        st.subheader("Session Refinement Quota")
        used = int(st.session_state.get("refinement_count", 0))
        remaining = max(0, MAX_REFINEMENTS - used)
        st.caption(
            f"Refinements used: {used} / {MAX_REFINEMENTS} ({remaining} remaining)"
        )


def render_input_section() -> None:
    """Render primary event configuration inputs and trigger plan generation."""
    st.subheader("1. Configure Your Event")
    col1, col2, col3 = st.columns(3)

    with col1:
        event_type = st.selectbox(
            label="Event Type",
            options=list(EVENT_TYPES),
            index=0,
            help="Select Wedding, Birthday, or Community Event for tailored domain planning.",
        )
        total_budget = st.number_input(
            label="Total Budget (INR ₹)",
            min_value=MIN_BUDGET_INR,
            max_value=MAX_BUDGET_INR,
            value=DEFAULT_BUDGET_INR,
            step=BUDGET_STEP_INR,
            help="Enter your total target budget in Indian Rupees (INR).",
        )

    with col2:
        guest_count = st.number_input(
            label="Expected Guest Count",
            min_value=MIN_GUEST_COUNT,
            max_value=MAX_GUEST_COUNT,
            value=DEFAULT_GUEST_COUNT,
            step=10,
            help="Approximate number of attendees expected at the event.",
        )
        default_dt = date.today() + timedelta(days=DEFAULT_DAYS_AHEAD)
        event_date = st.date_input(
            label="Event Date",
            value=default_dt,
            help="Target calendar date for the event; used to compute T-minus milestones.",
        )

    with col3:
        city = st.text_input(
            label="City (Optional)",
            value="Chennai",
            max_chars=MAX_INPUT_LENGTH,
            help="Optional city or locality name for regional context (max 100 characters).",
        )
        vibe_theme = st.text_input(
            label="Vibe / Theme",
            value="Traditional Tamil Wedding",
            max_chars=MAX_INPUT_LENGTH,
            help="Describe your theme (e.g. Cyberpunk Birthday, Traditional Tamil Wedding, Neighbourhood Diwali Fair).",
        )

    focus_items = ", ".join(EVENT_TYPE_FOCUS.get(event_type, ()))
    st.caption(f"Event-Type Focus Areas for {event_type}: {focus_items}.")

    if st.button(
        label="Generate Event Plan",
        type="primary",
        help="Generate a complete budget, timeline, vendor checklist, and ideas in one step.",
    ):
        _handle_generate_click(
            event_type=event_type,
            total_budget=float(total_budget),
            guest_count=int(guest_count),
            event_date=event_date,
            city=city,
            vibe_theme=vibe_theme,
        )


def _handle_generate_click(
    event_type: str,
    total_budget: float,
    guest_count: int,
    event_date: date,
    city: str,
    vibe_theme: str,
) -> None:
    """Validate inputs and invoke cached plan generator with spinner feedback."""
    try:
        clean_theme = sanitize_input(vibe_theme, allow_empty=False)
        clean_city = (
            sanitize_input(city, allow_empty=True) if city.strip() else "Not specified"
        ) or "Not specified"
    except ValueError as err:
        st.error(f"Please check your input: {err}")
        return

    with st.spinner("Crafting your personalized event plan..."):
        plan_dict, is_fallback, reason = generate_event_plan(
            event_type=event_type,
            total_budget=total_budget,
            guest_count=guest_count,
            event_date_iso=event_date.isoformat(),
            city=clean_city,
            vibe_theme=clean_theme,
            refinement_history=(),
        )

    st.session_state["plan_data"] = plan_dict
    st.session_state["is_fallback"] = is_fallback
    st.session_state["fallback_reason"] = reason
    st.session_state["event_date_iso"] = event_date.isoformat()
    st.session_state["refinement_history"] = ()


def render_budget_section(plan: EventPlan) -> pd.DataFrame:
    """Render interactive pie chart, accessible table, and Planned vs Actual editor."""
    st.header("2. Budget Breakdown & Planned vs Actual Tracker")
    alloc_tuple = tuple(
        (item.category, item.allocated_amount, item.percentage, item.notes)
        for item in plan.budget_allocations
    )
    base_df, was_normalized, norm_warning = build_budget_dataframe(
        alloc_tuple, plan.total_budget
    )
    if was_normalized and norm_warning:
        st.warning(f"Notice: {norm_warning}")

    chart_col, table_col = st.columns([1, 1])
    with chart_col:
        fig = px.pie(
            base_df,
            names="Category",
            values="Planned (INR)",
            title=f"Planned Budget Allocation (Total: ₹{plan.total_budget:,.2f})",
            color_discrete_sequence=COLORBLIND_SAFE_PALETTE,
            hole=0.35,
        )
        fig.update_traces(textinfo="label+percent", textposition="inside")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Interactive pie chart of planned INR allocations by category using an "
            "Okabe-Ito colorblind-safe palette. Full numerical equivalents are shown "
            "in the adjacent accessible data table."
        )

    with table_col:
        st.subheader("Accessible Budget Allocation Table")
        st.dataframe(
            base_df[["Category", "Planned (INR)", "Share (%)", "Notes"]],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Accessible tabular representation of all planned budget categories, "
            "amounts in INR, percentage shares, and planning notes."
        )

    return _render_planned_vs_actual_editor(base_df, plan.total_budget)


def _render_planned_vs_actual_editor(
    base_df: pd.DataFrame, total_budget: float
) -> pd.DataFrame:
    """Render editable Planned vs Actual table and budget status alerts."""
    st.subheader("Planned vs Actual Spend Editor")
    st.caption(
        "Update the 'Actual (INR)' column below to track real vendor quotes and expenses."
    )
    edited_df = st.data_editor(
        base_df,
        key="planned_vs_actual_editor",
        disabled=["Category", "Planned (INR)", "Share (%)", "Notes"],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Actual (INR)": st.column_config.NumberColumn(
                "Actual (INR)",
                help="Enter your actual or quoted spend in INR for this category.",
                min_value=0.0,
                max_value=MAX_BUDGET_INR,
                step=1000.0,
                format="₹%.2f",
            ),
            "Planned (INR)": st.column_config.NumberColumn(
                "Planned (INR)",
                help="Planned allocation in INR.",
                format="₹%.2f",
            ),
        },
    )

    summary = summarize_planned_vs_actual(edited_df, total_budget)
    m1, m2, m3 = st.columns(3)
    m1.metric("Planned Budget (INR)", f"₹{summary['planned_total']:,.2f}")
    m2.metric("Actual Spend (INR)", f"₹{summary['actual_total']:,.2f}")
    m3.metric("Remaining Budget (INR)", f"₹{summary['remaining_budget']:,.2f}")

    if summary["is_over_budget"]:
        st.error(
            f"Over-Budget Warning: Actual spend exceeds your total budget by "
            f"₹{summary['over_budget_amount']:,.2f}. Consider reducing high-cost "
            "categories or using the Refine assistant below."
        )
    return edited_df


def render_timeline_section(plan: EventPlan, event_date_iso: str) -> list[dict[str, Any]]:
    """Render T-minus countdown expanders with computed dates, skipping past stages."""
    st.header("3. T-Minus Countdown Timeline")
    timeline_tuple = tuple(
        (stage.stage, stage.days_before, tuple(stage.tasks))
        for stage in plan.timeline
    )
    active_stages, skipped_count = compute_active_timeline(
        timeline_tuple=timeline_tuple,
        event_date_iso=event_date_iso,
    )
    if skipped_count > 0:
        st.info(
            f"Note: Skipped {skipped_count} earlier milestone stage(s) whose target "
            "dates have already passed relative to today."
        )
    if not active_stages:
        st.warning(
            "The selected event date is in the past. Please pick today or a future "
            "date to see upcoming countdown stages."
        )
        return []

    for idx, stage in enumerate(active_stages):
        header_label = (
            f"{stage['stage']} — Target Date: {stage['formatted_date']} "
            f"({stage['days_from_today']} days from today)"
        )
        with st.expander(header_label, expanded=(idx == 0)):
            for task in stage["tasks"]:
                st.markdown(f"- {task}")

    return active_stages


def render_vendor_checklist_section(plan: EventPlan) -> dict[str, bool]:
    """Render persistent vendor checkbox grid and completion progress bar."""
    st.header("4. Vendor Checklist")
    vendors_raw = [v.model_dump() for v in plan.vendor_checklist]
    checked_map: dict[str, bool] = {}

    for vendor in plan.vendor_checklist:
        state_key = f"vendor_chk_{plan.event_type}_{vendor.id}"
        if state_key not in st.session_state:
            st.session_state[state_key] = False

    for vendor in plan.vendor_checklist:
        state_key = f"vendor_chk_{plan.event_type}_{vendor.id}"
        label = (
            f"{vendor.vendor_name} | Category: {vendor.category} | "
            f"Est. Cost: ₹{vendor.estimated_cost:,.2f} | Priority: {vendor.priority}"
        )
        checked_map[vendor.id] = st.checkbox(
            label=label,
            key=state_key,
            help=vendor.notes or f"Mark {vendor.vendor_name} as booked or completed.",
        )

    metrics = compute_vendor_progress(vendors_raw, checked_map)
    st.progress(
        float(metrics["progress_ratio"]),
        text=(
            f"Checklist Progress: {metrics['completed_count']} of {metrics['total_count']} "
            f"vendors booked (₹{metrics['booked_cost']:,.2f} / "
            f"₹{metrics['total_estimated_cost']:,.2f})"
        ),
    )
    return checked_map


def render_personalized_ideas_section(plan: EventPlan) -> None:
    """Render personalized creative ideas driven by the user's Vibe/Theme."""
    st.header(f"5. Personalized Ideas — {plan.vibe_theme}")
    ideas = plan.personalized_ideas
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Decor & Ambiance")
        for item in ideas.decor:
            st.markdown(f"- {item}")
        st.subheader("Food & Catering")
        for item in ideas.food:
            st.markdown(f"- {item}")

    with col_b:
        st.subheader("Entertainment")
        for item in ideas.entertainment:
            st.markdown(f"- {item}")
        st.subheader("Guest Activities")
        for item in ideas.activities:
            st.markdown(f"- {item}")

    st.subheader("Sample Invitation Wording")
    st.info(ideas.invitation_wording)


def render_refine_section(plan: EventPlan) -> None:
    """Render the 'Refine your plan' assistant input capped at 5 refinements."""
    st.header("6. Refine your plan")
    used_count = int(st.session_state.get("refinement_count", 0))
    remaining = max(0, MAX_REFINEMENTS - used_count)
    st.caption(
        f"Ask the assistant to adjust your plan (e.g. 'make it cheaper', "
        f"'add a kids section'). {remaining} of {MAX_REFINEMENTS} refinements remaining."
    )

    refine_text = st.text_input(
        label="Refinement Request",
        placeholder="e.g., make it cheaper, add a kids activity zone, focus on eco-friendly decor",
        max_chars=MAX_INPUT_LENGTH,
        disabled=(used_count >= MAX_REFINEMENTS),
        help="Enter a short refinement instruction (max 100 characters, up to 5 times per session).",
    )
    if st.button(
        label="Apply Plan Refinement",
        disabled=(used_count >= MAX_REFINEMENTS),
        help="Submit your refinement request to update the event plan.",
    ):
        _handle_refine_click(plan, refine_text, used_count)

    if used_count >= MAX_REFINEMENTS:
        st.warning(
            f"Maximum session limit of {MAX_REFINEMENTS} refinements reached."
        )


def _handle_refine_click(
    plan: EventPlan, refine_text: str, used_count: int
) -> None:
    """Sanitize refinement request, enforce cap, and update session plan."""
    if used_count >= MAX_REFINEMENTS:
        st.warning("You have reached the maximum of 5 refinements for this session.")
        return

    try:
        clean_request = sanitize_input(refine_text, allow_empty=False)
    except ValueError as err:
        st.error(f"Invalid refinement request: {err}")
        return

    history: tuple[str, ...] = tuple(st.session_state.get("refinement_history", ())) + (
        clean_request,
    )
    with st.spinner("Refining your event plan..."):
        plan_dict, is_fallback, reason = generate_event_plan(
            event_type=plan.event_type,
            total_budget=plan.total_budget,
            guest_count=plan.guest_count,
            event_date_iso=str(st.session_state.get("event_date_iso")),
            city=plan.city,
            vibe_theme=plan.vibe_theme,
            refinement_history=history,
        )

    st.session_state["plan_data"] = plan_dict
    st.session_state["is_fallback"] = is_fallback
    st.session_state["fallback_reason"] = reason
    st.session_state["refinement_history"] = history
    st.session_state["refinement_count"] = used_count + 1
    st.rerun()


def render_export_section(
    plan: EventPlan,
    edited_df: pd.DataFrame,
    active_timeline: list[dict[str, Any]],
    checked_map: dict[str, bool],
) -> None:
    """Render download buttons for CSV, Markdown, and .ics calendar files."""
    st.header("7. Export Your Plan")
    csv_data = export_plan_to_csv(plan, edited_df, checked_map)
    md_data = export_plan_to_markdown(plan, edited_df, active_timeline, checked_map)
    ics_data = export_timeline_to_ics(plan, active_timeline)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            label="Download Budget & Vendors (CSV)",
            data=csv_data,
            file_name="eventforge_plan.csv",
            mime="text/csv",
            help="Download budget allocations and vendor checklist status as a CSV spreadsheet.",
        )
    with c2:
        st.download_button(
            label="Download Full Event Plan (Markdown)",
            data=md_data,
            file_name="eventforge_plan.md",
            mime="text/markdown",
            help="Download the complete plan including ideas and timeline in Markdown format.",
        )
    with c3:
        st.download_button(
            label="Download Timeline Calendar (.ics)",
            data=ics_data,
            file_name="eventforge_timeline.ics",
            mime="text/calendar",
            help="Download an iCalendar (.ics) file of upcoming milestones for Google/Outlook/Apple Calendar.",
        )


def main() -> None:
    """Main Streamlit UI orchestration function."""
    init_session_state()
    render_sidebar()

    st.title(f"{APP_ICON} {APP_TITLE}")
    st.caption(APP_TAGLINE)
    st.divider()

    render_input_section()

    if st.session_state.get("plan_data") is None:
        st.info(
            "Configure your event parameters above and click **Generate Event Plan** "
            "to get started."
        )
        return

    if st.session_state.get("is_fallback"):
        reason = st.session_state.get("fallback_reason") or "No API key found"
        st.warning(
            f"Showing a template plan ({reason}). Scaled to your ₹"
            f"{float(st.session_state['plan_data']['total_budget']):,.2f} budget."
        )

    plan = validate_event_plan_payload(st.session_state["plan_data"])
    st.success(f"**Plan Summary:** {plan.event_summary}")

    edited_df = render_budget_section(plan)
    active_timeline = render_timeline_section(
        plan, str(st.session_state.get("event_date_iso"))
    )
    checked_map = render_vendor_checklist_section(plan)
    render_personalized_ideas_section(plan)
    render_refine_section(plan)
    render_export_section(plan, edited_df, active_timeline, checked_map)


if __name__ == "__main__":
    main()
