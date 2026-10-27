"""Unit tests for Gemini client with mocked API, logging, caching, and fallback reasons."""

import json
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.gemini_client import (
    SYSTEM_INSTRUCTION,
    build_user_prompt,
    generate_event_plan,
    get_api_key,
    get_model_name,
)


def test_get_api_key_and_model_name_with_mocked_env() -> None:
    """Verify API key and model name resolution from environment variables."""
    with patch("services.gemini_client.load_dotenv"):
        with patch("services.gemini_client.os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda k, default=None: {
                "GOOGLE_API_KEY": "test-fake-key-123",
                "GEMINI_MODEL": "gemini-3.8-flash",
            }.get(k, default)

            assert get_api_key() == "test-fake-key-123"
            assert get_model_name() == "gemini-3.8-flash"


def test_get_api_key_returns_none_for_placeholder_or_missing() -> None:
    """Verify placeholder or missing GOOGLE_API_KEY returns None safely."""
    with patch("services.gemini_client.load_dotenv"):
        with patch(
            "services.gemini_client.os.getenv",
            return_value="your_gemini_api_key_here",
        ):
            with patch("services.gemini_client.st.secrets", {}):
                assert get_api_key() is None


def test_build_user_prompt_isolates_user_data_from_system_instruction() -> None:
    """Verify user inputs are placed inside <USER_DATA> tags and not in SYSTEM_INSTRUCTION."""
    user_theme = "Traditional Tamil Wedding"
    prompt = build_user_prompt(
        event_type="Wedding",
        total_budget=500000.0,
        guest_count=200,
        event_date_iso="2027-03-15",
        city="Madurai",
        vibe_theme=user_theme,
        refinement_history=("make it cheaper",),
    )
    assert "<USER_DATA>" in prompt
    assert "</USER_DATA>" in prompt
    assert user_theme in prompt
    assert "make it cheaper" in prompt
    assert user_theme not in SYSTEM_INSTRUCTION


def test_generate_event_plan_missing_api_key_uses_fallback() -> None:
    """Verify missing API key returns specific 'No API key found' fallback reason."""
    with patch("services.gemini_client.load_dotenv"):
        with patch("services.gemini_client.os.getenv", return_value=None):
            with patch("services.gemini_client.st.secrets", {}):
                plan_dict, is_fallback, reason = generate_event_plan(
                    event_type="Community Event",
                    total_budget=180000.0,
                    guest_count=250,
                    event_date_iso="2027-01-20",
                    city="Pune",
                    vibe_theme="Neighbourhood Diwali Fair",
                    refinement_history=(),
                )
    assert is_fallback is True
    assert reason == "No API key found"
    assert plan_dict["event_type"] == "Community Event"
    assert plan_dict["total_budget"] == 180000.0


def test_generate_event_plan_success_with_mocked_gemini(
    sample_valid_plan_dict: dict[str, Any],
) -> None:
    """Verify valid JSON response from mocked Gemini client returns non-fallback plan."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(sample_valid_plan_dict)

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response

    with patch("services.gemini_client.load_dotenv"):
        with patch("services.gemini_client.os.getenv", return_value="fake-key"):
            with patch(
                "services.gemini_client.genai.Client",
                return_value=mock_client_instance,
            ):
                plan_dict, is_fallback, reason = generate_event_plan(
                    event_type="Birthday",
                    total_budget=100000.0,
                    guest_count=50,
                    event_date_iso="2027-05-10",
                    city="Bengaluru",
                    vibe_theme="Cyberpunk Birthday",
                    refinement_history=(),
                )

    assert is_fallback is False
    assert reason is None
    assert plan_dict["vibe_theme"] == "Cyberpunk Birthday"
    mock_client_instance.models.generate_content.assert_called_once()


def test_generate_event_plan_timeout_logs_and_returns_ai_request_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify API timeout logs exception type/message and returns 'AI request failed'."""
    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.side_effect = TimeoutError(
        "Request timed out"
    )

    with caplog.at_level(logging.WARNING):
        with patch("services.gemini_client.load_dotenv"):
            with patch("services.gemini_client.os.getenv", return_value="fake-key"):
                with patch(
                    "services.gemini_client.genai.Client",
                    return_value=mock_client_instance,
                ):
                    with patch("services.gemini_client.time.sleep") as mock_sleep:
                        plan_dict, is_fallback, reason = generate_event_plan(
                            event_type="Wedding",
                            total_budget=400000.0,
                            guest_count=300,
                            event_date_iso="2027-08-01",
                            city="Chennai",
                            vibe_theme="Traditional Tamil Wedding",
                            refinement_history=(),
                        )

    assert is_fallback is True
    assert reason == "AI request failed"
    assert plan_dict["event_type"] == "Wedding"
    assert plan_dict["total_budget"] == 400000.0
    assert mock_client_instance.models.generate_content.call_count == 2
    mock_sleep.assert_called_once()
    assert "TimeoutError" in caplog.text
    assert "Request timed out" in caplog.text


def test_generate_event_plan_invalid_json_logs_and_returns_ai_returned_invalid_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify malformed JSON from Gemini logs ValueError and returns 'AI returned invalid data'."""
    mock_response = MagicMock()
    mock_response.text = '{"event_type": "Birthday", "broken": true}'

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response

    with caplog.at_level(logging.ERROR):
        with patch("services.gemini_client.load_dotenv"):
            with patch("services.gemini_client.os.getenv", return_value="fake-key"):
                with patch(
                    "services.gemini_client.genai.Client",
                    return_value=mock_client_instance,
                ):
                    plan_dict, is_fallback, reason = generate_event_plan(
                        event_type="Birthday",
                        total_budget=90000.0,
                        guest_count=40,
                        event_date_iso="2027-04-12",
                        city="Delhi",
                        vibe_theme="Retro Arcade Party",
                        refinement_history=(),
                    )

    assert is_fallback is True
    assert reason == "AI returned invalid data"
    assert plan_dict["total_budget"] == 90000.0
    assert "ValueError" in caplog.text


def test_failed_or_fallback_results_are_never_cached(
    sample_valid_plan_dict: dict[str, Any],
) -> None:
    """Verify failed calls are not cached in @st.cache_data so subsequent calls succeed."""
    mock_good_response = MagicMock()
    mock_good_response.text = json.dumps(sample_valid_plan_dict)

    mock_client_instance = MagicMock()
    # First 2 attempts (initial + 1 retry) fail with ConnectionError; 3rd attempt succeeds
    mock_client_instance.models.generate_content.side_effect = [
        ConnectionError("Temporary network drop"),
        ConnectionError("Temporary network drop"),
        mock_good_response,
    ]

    with patch("services.gemini_client.load_dotenv"):
        with patch("services.gemini_client.os.getenv", return_value="fake-key"):
            with patch(
                "services.gemini_client.genai.Client",
                return_value=mock_client_instance,
            ):
                with patch("services.gemini_client.time.sleep"):
                    # Call 1 fails and returns fallback
                    _, is_fallback_1, reason_1 = generate_event_plan(
                        event_type="Birthday",
                        total_budget=100000.0,
                        guest_count=50,
                        event_date_iso="2027-05-10",
                        city="Bengaluru",
                        vibe_theme="Cyberpunk Birthday",
                        refinement_history=(),
                    )
                    assert is_fallback_1 is True
                    assert reason_1 == "AI request failed"

                    # Call 2 with identical arguments must NOT return cached failure
                    plan_2, is_fallback_2, reason_2 = generate_event_plan(
                        event_type="Birthday",
                        total_budget=100000.0,
                        guest_count=50,
                        event_date_iso="2027-05-10",
                        city="Bengaluru",
                        vibe_theme="Cyberpunk Birthday",
                        refinement_history=(),
                    )
                    assert is_fallback_2 is False
                    assert reason_2 is None
                    assert plan_2["vibe_theme"] == "Cyberpunk Birthday"
