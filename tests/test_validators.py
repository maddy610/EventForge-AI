"""Unit tests for input sanitization and Pydantic schema validation."""

import json
from typing import Any

import pytest

from config import MAX_INPUT_LENGTH
from services.validators import (
    EventPlan,
    TimelineStage,
    sanitize_input,
    validate_event_plan_payload,
)


def test_sanitize_input_strips_script_tags_and_angle_brackets() -> None:
    """Verify script tags and < > characters are completely removed."""
    malicious = "<script>alert('xss')</script>Cyberpunk <Birthday> Party"
    result = sanitize_input(malicious)
    assert "<" not in result
    assert ">" not in result
    assert "script" not in result.lower()
    assert result == "Cyberpunk Birthday Party"


def test_sanitize_input_handles_sql_like_strings_and_control_chars() -> None:
    """Verify SQL comment sequences, semicolons, and ASCII control chars are stripped."""
    sql_like = "Diwali Fair\x00\x07; DROP TABLE events; -- /* comment */"
    result = sanitize_input(sql_like)
    assert ";" not in result
    assert "--" not in result
    assert "/*" not in result
    assert "\x00" not in result
    assert "Diwali Fair" in result


def test_sanitize_input_preserves_unicode_tamil_and_hindi() -> None:
    """Verify Tamil and Hindi script themes including vowel marks are preserved."""
    tamil_theme = "பாரம்பரிய தமிழ் திருமணம் - Traditional Tamil Wedding"
    hindi_theme = "दीवाली मेला उत्सव & Cultural Fair"
    assert sanitize_input(tamil_theme) == tamil_theme
    assert sanitize_input(hindi_theme) == hindi_theme


def test_sanitize_input_enforces_max_length() -> None:
    """Verify inputs exceeding 100 characters are truncated to MAX_INPUT_LENGTH."""
    long_text = "A" * 160
    result = sanitize_input(long_text)
    assert len(result) == MAX_INPUT_LENGTH


def test_sanitize_input_rejects_empty_or_special_only() -> None:
    """Verify empty strings or strings with only disallowed tags raise ValueError."""
    with pytest.raises(ValueError, match="empty"):
        sanitize_input("   ")

    with pytest.raises(ValueError, match="empty"):
        sanitize_input("<script>evil()</script><>;;;")

    with pytest.raises(ValueError, match="valid text string"):
        sanitize_input(12345)  # type: ignore[arg-type]


def test_sanitize_input_allows_empty_when_flag_enabled() -> None:
    """Verify optional fields like city return empty string when allow_empty=True."""
    assert sanitize_input("   ", allow_empty=True) == ""


def test_validate_event_plan_payload_accepts_valid_dict_and_json(
    sample_valid_plan_dict: dict[str, Any],
) -> None:
    """Verify both dict and JSON string payloads validate into EventPlan."""
    plan_from_dict = validate_event_plan_payload(sample_valid_plan_dict)
    assert isinstance(plan_from_dict, EventPlan)
    assert plan_from_dict.event_type == "Birthday"

    raw_json = json.dumps(sample_valid_plan_dict)
    plan_from_json = validate_event_plan_payload(raw_json)
    assert plan_from_json.total_budget == 100000.0


def test_validate_event_plan_payload_rejects_malformed_or_missing_fields(
    sample_valid_plan_dict: dict[str, Any],
) -> None:
    """Verify malformed JSON, missing required fields, or invalid types raise ValueError."""
    with pytest.raises(ValueError, match="Invalid event plan"):
        validate_event_plan_payload("{bad json")

    broken = dict(sample_valid_plan_dict)
    del broken["budget_allocations"]
    with pytest.raises(ValueError, match="Invalid event plan"):
        validate_event_plan_payload(broken)

    bad_type = dict(sample_valid_plan_dict)
    bad_type["event_type"] = "InvalidType"
    with pytest.raises(ValueError, match="Invalid event plan"):
        validate_event_plan_payload(bad_type)


def test_timeline_stage_rejects_blank_tasks() -> None:
    """Verify TimelineStage validator rejects stages with only whitespace tasks."""
    with pytest.raises(ValueError, match="at least one task"):
        TimelineStage(stage="1 week out", days_before=7, tasks=["   ", ""])
