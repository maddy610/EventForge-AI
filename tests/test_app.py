"""Unit tests for Streamlit app handlers and session refinement cap enforcement."""

from datetime import date
from typing import Any
from unittest.mock import patch

import streamlit as st

import app
from config import MAX_REFINEMENTS
from services.validators import validate_event_plan_payload


def test_init_session_state_sets_defaults() -> None:
    """Verify init_session_state populates required keys."""
    st.session_state.clear()
    app.init_session_state()
    assert st.session_state["plan_data"] is None
    assert st.session_state["refinement_count"] == 0
    assert st.session_state["refinement_history"] == ()


def test_handle_generate_click_stores_plan_in_session(
    sample_valid_plan_dict: dict[str, Any],
) -> None:
    """Verify _handle_generate_click sanitizes inputs and populates session_state."""
    st.session_state.clear()
    app.init_session_state()

    with patch(
        "app.generate_event_plan",
        return_value=(sample_valid_plan_dict, True, "No API key configured."),
    ):
        app._handle_generate_click(
            event_type="Birthday",
            total_budget=100000.0,
            guest_count=50,
            event_date=date(2027, 5, 10),
            city="Bengaluru",
            vibe_theme="Cyberpunk Birthday",
        )

    assert st.session_state["plan_data"] == sample_valid_plan_dict
    assert st.session_state["is_fallback"] is True


def test_handle_refine_click_enforces_five_refinement_limit(
    sample_valid_plan_dict: dict[str, Any],
) -> None:
    """Verify refinements increment counter up to 5 and block the 6th attempt."""
    st.session_state.clear()
    app.init_session_state()
    plan = validate_event_plan_payload(sample_valid_plan_dict)

    with patch(
        "app.generate_event_plan",
        return_value=(sample_valid_plan_dict, False, None),
    ) as mock_gen:
        with patch("app.st.rerun"):
            app._handle_refine_click(plan, "make it cheaper", used_count=0)
            assert st.session_state["refinement_count"] == 1
            assert st.session_state["refinement_history"] == ("make it cheaper",)
            mock_gen.assert_called_once()

        # Attempt when used_count == MAX_REFINEMENTS (5) should not call API
        mock_gen.reset_mock()
        app._handle_refine_click(plan, "another change", used_count=MAX_REFINEMENTS)
        mock_gen.assert_not_called()


def test_app_end_to_end_offline_mode_without_api_key() -> None:
    """Verify full Streamlit UI flow in offline fallback mode (no API key)."""
    from streamlit.testing.v1 import AppTest

    with patch("services.gemini_client.load_dotenv"):
        with patch("services.gemini_client.os.getenv", return_value=None):
            with patch("services.gemini_client.st.secrets", {}):
                at = AppTest.from_file("app.py", default_timeout=15)
                at.run()
                assert not at.exception
                captions = [c.value for c in at.caption]
                assert any(
                    "Plan weddings, birthdays and community events" in c
                    for c in captions
                )

                # Click 'Generate Event Plan' button
                at.button[0].click().run()
                assert not at.exception
                warnings = [w.value for w in at.warning]
                assert any(
                    "Showing a template plan (No API key found)" in w
                    for w in warnings
                )
                assert len(at.checkbox) >= 4


def test_app_end_to_end_online_mode_with_api_key(
    sample_valid_plan_dict: dict[str, Any],
) -> None:
    """Verify full Streamlit UI flow with API key and mocked Gemini response."""
    import json
    from unittest.mock import MagicMock
    from streamlit.testing.v1 import AppTest

    mock_response = MagicMock()
    mock_response.text = json.dumps(sample_valid_plan_dict)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("services.gemini_client.load_dotenv"):
        with patch("services.gemini_client.os.getenv", return_value="valid-mock-key"):
            with patch(
                "services.gemini_client.genai.Client", return_value=mock_client
            ):
                at = AppTest.from_file("app.py", default_timeout=15)
                at.run()
                assert not at.exception

                # Click 'Generate Event Plan'
                at.button[0].click().run()
                assert not at.exception

                warnings = [w.value for w in at.warning]
                assert not any("Showing a template plan" in w for w in warnings)
                successes = [s.value for s in at.success]
                assert any("Cyberpunk Birthday" in s for s in successes)

                # Toggle a vendor checkbox and ensure no API re-trigger
                call_count_before = mock_client.models.generate_content.call_count
                at.checkbox[0].check().run()
                assert not at.exception
                assert (
                    mock_client.models.generate_content.call_count
                    == call_count_before
                )

