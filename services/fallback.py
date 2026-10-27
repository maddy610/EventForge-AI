"""Offline fallback plan loader and budget scaler for EventForge AI."""

import json
import logging
from pathlib import Path
from typing import Any

from config import EVENT_TYPES, TEMPLATE_FILE_MAP, TEMPLATES_DIR
from services.validators import EventPlan, validate_event_plan_payload

logger = logging.getLogger(__name__)


def _read_template_file(event_type: str, templates_dir: Path = TEMPLATES_DIR) -> dict[str, Any]:
    """Read raw template JSON dictionary for the specified event type."""
    resolved_type = event_type if event_type in EVENT_TYPES else "Wedding"
    filename = TEMPLATE_FILE_MAP[resolved_type]
    file_path = templates_dir / filename

    with file_path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def _scale_allocations_and_vendors(
    data: dict[str, Any], target_budget: float
) -> None:
    """Scale template budget allocations and vendor costs to target_budget in-place."""
    allocations = data.get("budget_allocations", [])
    running_total = 0.0
    for idx, item in enumerate(allocations):
        pct = float(item.get("percentage", 0.0))
        if idx == len(allocations) - 1:
            amount = round(max(0.0, target_budget - running_total), 2)
        else:
            amount = round(target_budget * (pct / 100.0), 2)
            running_total += amount
        item["allocated_amount"] = amount

    base_budget = float(data.get("total_budget", target_budget)) or target_budget
    scale_factor = target_budget / base_budget
    for vendor in data.get("vendor_checklist", []):
        raw_cost = float(vendor.get("estimated_cost", 0.0))
        vendor["estimated_cost"] = round(raw_cost * scale_factor, 2)


def _apply_user_context(
    data: dict[str, Any],
    vibe_theme: str,
    guest_count: int,
    city: str,
    refinement_note: str | None = None,
) -> None:
    """Inject user theme, guest count, city, and optional refinement into template data."""
    clean_city = city.strip() if city and city.strip() else "Not specified"
    data["vibe_theme"] = vibe_theme
    data["guest_count"] = guest_count
    data["city"] = clean_city

    city_clause = f" in {clean_city}" if clean_city != "Not specified" else ""
    base_summary = data.get("event_summary", "")
    refinement_clause = (
        f" Refined for: {refinement_note}." if refinement_note else ""
    )
    data["event_summary"] = (
        f"[{vibe_theme}] Plan for {guest_count} guests{city_clause}. "
        f"{base_summary}{refinement_clause}"
    ).strip()

    ideas = data.get("personalized_ideas", {})
    if isinstance(ideas, dict) and ideas.get("decor"):
        ideas["decor"][0] = f"{vibe_theme} focal centerpiece: {ideas['decor'][0]}"
    if refinement_note and isinstance(ideas, dict) and ideas.get("activities"):
        ideas["activities"].append(
            f"Custom refinement highlight: {refinement_note}"
        )


def load_fallback_plan(
    event_type: str,
    total_budget: float,
    guest_count: int,
    vibe_theme: str,
    city: str = "Not specified",
    refinement_note: str | None = None,
    templates_dir: Path = TEMPLATES_DIR,
) -> EventPlan:
    """Load and scale a built-in template plan when Gemini API is unavailable.

    Args:
        event_type: One of Wedding, Birthday, or Community Event.
        total_budget: Total target budget in INR.
        guest_count: Number of expected guests.
        vibe_theme: Sanitized theme or vibe string.
        city: Sanitized city name or 'Not specified'.
        refinement_note: Optional sanitized refinement instruction.
        templates_dir: Directory path containing JSON template files.

    Returns:
        Validated EventPlan scaled to the user's parameters.
    """
    logger.info(
        "Loading offline fallback template for event_type=%s, budget=%.2f",
        event_type,
        total_budget,
    )
    data = _read_template_file(event_type, templates_dir=templates_dir)
    safe_budget = max(1.0, float(total_budget))
    data["total_budget"] = round(safe_budget, 2)

    _scale_allocations_and_vendors(data, safe_budget)
    _apply_user_context(
        data,
        vibe_theme=vibe_theme,
        guest_count=max(1, int(guest_count)),
        city=city,
        refinement_note=refinement_note,
    )
    return validate_event_plan_payload(data)
