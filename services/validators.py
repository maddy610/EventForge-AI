"""Input sanitization and Pydantic data models for EventForge AI."""

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from config import EVENT_TYPES, MAX_INPUT_LENGTH

logger = logging.getLogger(__name__)

# Regex patterns for security sanitization
_SCRIPT_TAG_PATTERN = re.compile(
    r"<\s*script[^>]*>.*?<\s*/\s*script\s*>|<\s*/?\s*script[^>]*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SQL_COMMENT_PATTERN = re.compile(r"(--|/\*|\*/|;)")
# Allow Unicode word chars (\w), Indic/Unicode combining marks, whitespace, and safe punctuation
_DISALLOWED_CHARS_PATTERN = re.compile(
    r"[^\w\s\u0300-\u036f\u0900-\u0dff,.\-'&()/:!?+]",
    flags=re.UNICODE,
)
_MULTI_SPACE_PATTERN = re.compile(r"\s+")


def sanitize_input(
    raw_text: str,
    max_length: int = MAX_INPUT_LENGTH,
    allow_empty: bool = False,
) -> str:
    """Sanitize free-text user input against XSS, control chars, and injection.

    Args:
        raw_text: Unvalidated string from user input.
        max_length: Maximum allowed character count (default 100).
        allow_empty: Whether an empty string is allowed (e.g. optional city).

    Returns:
        Cleaned and length-bounded string.

    Raises:
        ValueError: If input is not a string, or is empty after cleaning
            when allow_empty is False.
    """
    if not isinstance(raw_text, str):
        raise ValueError("Input must be a valid text string.")

    cleaned = _SCRIPT_TAG_PATTERN.sub(" ", raw_text)
    cleaned = _CONTROL_CHARS_PATTERN.sub(" ", cleaned)
    cleaned = cleaned.replace("<", " ").replace(">", " ")
    cleaned = _SQL_COMMENT_PATTERN.sub(" ", cleaned)
    cleaned = _DISALLOWED_CHARS_PATTERN.sub("", cleaned)
    cleaned = _MULTI_SPACE_PATTERN.sub(" ", cleaned).strip()

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip()

    if not cleaned and not allow_empty:
        raise ValueError(
            "Input cannot be empty or contain only special characters."
        )

    return cleaned


class BudgetItem(BaseModel):
    """Single budget category allocation."""

    category: str = Field(..., min_length=1, description="Expense category name")
    allocated_amount: float = Field(
        ..., ge=0.0, description="Allocated amount in INR"
    )
    percentage: float = Field(
        ..., ge=0.0, le=100.0, description="Percentage of total budget"
    )
    notes: str = Field(
        default="", description="Explanation and tips for this category"
    )


class TimelineStage(BaseModel):
    """Single countdown milestone on the event planning timeline."""

    stage: str = Field(
        ...,
        min_length=1,
        description="T-minus label such as '6 months out' or 'Event day'",
    )
    days_before: int = Field(
        ..., ge=0, description="Number of days prior to the event date"
    )
    tasks: list[str] = Field(
        ..., min_length=1, description="Actionable checklist tasks for this stage"
    )

    @field_validator("tasks")
    @classmethod
    def validate_non_empty_tasks(cls, tasks: list[str]) -> list[str]:
        """Ensure every task item has non-empty text."""
        cleaned = [t.strip() for t in tasks if t and t.strip()]
        if not cleaned:
            raise ValueError("Each timeline stage must contain at least one task.")
        return cleaned


class VendorItem(BaseModel):
    """Single vendor checklist item with cost and priority."""

    id: str = Field(..., min_length=1, description="Stable unique identifier")
    vendor_name: str = Field(
        ..., min_length=1, description="Vendor or service item title"
    )
    category: str = Field(
        ..., min_length=1, description="Domain category for the vendor"
    )
    estimated_cost: float = Field(
        ..., ge=0.0, description="Estimated cost in INR"
    )
    priority: Literal["High", "Medium", "Low"] = Field(
        ..., description="Priority level: High, Medium, or Low"
    )
    notes: str = Field(
        default="", description="Key questions or booking tips"
    )


class PersonalizedIdeas(BaseModel):
    """Creative recommendations tailored to the user's Vibe/Theme."""

    decor: list[str] = Field(
        ..., min_length=1, description="Decor and ambiance concepts"
    )
    food: list[str] = Field(
        ..., min_length=1, description="Menu, catering, or cake ideas"
    )
    entertainment: list[str] = Field(
        ..., min_length=1, description="Music, performances, or show ideas"
    )
    activities: list[str] = Field(
        ..., min_length=1, description="Interactive guest activities or rituals"
    )
    invitation_wording: str = Field(
        ..., min_length=5, description="Sample themed invitation wording"
    )


class EventPlan(BaseModel):
    """Complete structured event plan validated from Gemini or fallback JSON."""

    event_type: Literal["Wedding", "Birthday", "Community Event"]
    vibe_theme: str = Field(..., min_length=1)
    total_budget: float = Field(..., ge=1.0)
    guest_count: int = Field(..., ge=1)
    city: str = Field(default="Not specified")
    event_summary: str = Field(..., min_length=5)
    budget_allocations: list[BudgetItem] = Field(..., min_length=3)
    timeline: list[TimelineStage] = Field(..., min_length=3)
    vendor_checklist: list[VendorItem] = Field(..., min_length=3)
    personalized_ideas: PersonalizedIdeas

    @field_validator("event_type")
    @classmethod
    def check_event_type(cls, value: str) -> str:
        """Verify event_type matches supported event types."""
        if value not in EVENT_TYPES:
            raise ValueError(f"Unsupported event type: {value}")
        return value

    @field_validator("total_budget")
    @classmethod
    def check_positive_budget(cls, value: float) -> float:
        """Ensure total_budget is strictly positive without using exclusiveMinimum."""
        if value <= 0.0:
            raise ValueError("total_budget must be greater than 0.")
        return value

    @field_validator("guest_count")
    @classmethod
    def check_positive_guests(cls, value: int) -> int:
        """Ensure guest_count is strictly positive without using exclusiveMinimum."""
        if value <= 0:
            raise ValueError("guest_count must be greater than 0.")
        return value


def validate_event_plan_payload(payload: dict[str, Any] | str) -> EventPlan:
    """Validate a raw dictionary or JSON string into an EventPlan instance.

    Args:
        payload: Parsed dictionary or raw JSON text.

    Returns:
        Validated EventPlan model.

    Raises:
        ValueError: If validation or JSON parsing fails.
    """
    try:
        if isinstance(payload, str):
            return EventPlan.model_validate_json(payload)
        return EventPlan.model_validate(payload)
    except Exception as exc:
        logger.warning("EventPlan validation failed: %s", exc)
        raise ValueError(f"Invalid event plan structure: {exc}") from exc
