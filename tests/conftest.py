"""Pytest configuration and shared fixtures for EventForge AI tests."""

from pathlib import Path
import sys
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402


@pytest.fixture(autouse=True)
def clear_streamlit_caches() -> None:
    """Clear Streamlit @st.cache_data caches before each test for isolation."""
    st.cache_data.clear()


@pytest.fixture()
def sample_valid_plan_dict() -> dict[str, Any]:
    """Return a valid EventPlan dictionary for unit testing."""
    return {
        "event_type": "Birthday",
        "vibe_theme": "Cyberpunk Birthday",
        "total_budget": 100000.0,
        "guest_count": 50,
        "city": "Bengaluru",
        "event_summary": "A neon-soaked Cyberpunk Birthday for 50 guests across age groups.",
        "budget_allocations": [
            {
                "category": "Venue & Neon Decor",
                "allocated_amount": 40000.0,
                "percentage": 40.0,
                "notes": "LED backdrops and hall booking",
            },
            {
                "category": "Food & Custom Cake",
                "allocated_amount": 35000.0,
                "percentage": 35.0,
                "notes": "Futuristic cake and buffet",
            },
            {
                "category": "Entertainment & Gaming",
                "allocated_amount": 25000.0,
                "percentage": 25.0,
                "notes": "VR arcade and synthwave DJ",
            },
        ],
        "timeline": [
            {
                "stage": "6 months out",
                "days_before": 180,
                "tasks": ["Book cyberpunk venue", "Draft guest list"],
            },
            {
                "stage": "1 month out",
                "days_before": 30,
                "tasks": ["Order custom neon cake", "Confirm synthwave DJ"],
            },
            {
                "stage": "Event day",
                "days_before": 0,
                "tasks": ["Setup LED lights", "Host cake cutting"],
            },
        ],
        "vendor_checklist": [
            {
                "id": "v_venue",
                "vendor_name": "Neon Loft Venue",
                "category": "Venue",
                "estimated_cost": 40000.0,
                "priority": "High",
                "notes": "Confirm power capacity",
            },
            {
                "id": "v_cake",
                "vendor_name": "Cyber Bakery",
                "category": "Cake",
                "estimated_cost": 35000.0,
                "priority": "High",
                "notes": "Eggless neon glaze",
            },
            {
                "id": "v_dj",
                "vendor_name": "Synthwave DJ & VR Booth",
                "category": "Entertainment",
                "estimated_cost": 25000.0,
                "priority": "Medium",
                "notes": "Bring 4 VR headsets",
            },
        ],
        "personalized_ideas": {
            "decor": ["Holographic signage", "Cyan and magenta LED tubes"],
            "food": ["Glowing tonic mocktails", "Cyberpunk circuit-board cake"],
            "entertainment": ["Synthwave live set", "Retro arcade tournament"],
            "activities": ["LED face-painting station", "Sci-fi trivia challenge"],
            "invitation_wording": "Jack in to the grid and celebrate a Cyberpunk Birthday night!",
        },
    }
