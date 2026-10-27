"""Application-wide constants and configuration for EventForge AI."""

from pathlib import Path
from typing import Final

# Core application metadata & exact problem statement wording
APP_TITLE: Final[str] = "EventForge AI"
APP_ICON: Final[str] = "✨"
PROBLEM_STATEMENT: Final[str] = (
    "Create a GenAI-powered planning assistant that helps users organize "
    "weddings, birthdays, and community events with budgets, timelines, "
    "vendor checklists, and personalized ideas."
)

# Paths
BASE_DIR: Final[Path] = Path(__file__).resolve().parent
TEMPLATES_DIR: Final[Path] = BASE_DIR / "templates"

# Supported event types and domain-specific focus areas
EVENT_TYPES: Final[tuple[str, ...]] = ("Wedding", "Birthday", "Community Event")

EVENT_TYPE_FOCUS: Final[dict[str, tuple[str, ...]]] = {
    "Wedding": ("ceremonies", "venue", "catering", "photography"),
    "Birthday": ("age group", "entertainment", "cake"),
    "Community Event": (
        "volunteers",
        "permits",
        "sponsors",
        "safety",
        "accessibility",
        "cleanup",
    ),
}

TEMPLATE_FILE_MAP: Final[dict[str, str]] = {
    "Wedding": "wedding.json",
    "Birthday": "birthday.json",
    "Community Event": "community_event.json",
}

# Budget & Guest input bounds (INR default)
CURRENCY_SYMBOL: Final[str] = "₹"
CURRENCY_CODE: Final[str] = "INR"
DEFAULT_BUDGET_INR: Final[float] = 250000.0
MIN_BUDGET_INR: Final[float] = 1000.0
MAX_BUDGET_INR: Final[float] = 100000000.0
BUDGET_STEP_INR: Final[float] = 5000.0

DEFAULT_GUEST_COUNT: Final[int] = 100
MIN_GUEST_COUNT: Final[int] = 1
MAX_GUEST_COUNT: Final[int] = 50000
DEFAULT_DAYS_AHEAD: Final[int] = 120

# Security & Validation limits
MAX_INPUT_LENGTH: Final[int] = 100
MAX_REFINEMENTS: Final[int] = 5
BUDGET_TOLERANCE_RATIO: Final[float] = 0.01

# Caching & Gemini API settings
CACHE_TTL_SECONDS: Final[int] = 3600
DEFAULT_GEMINI_MODEL: Final[str] = "gemini-3.5-flash-lite"
API_TIMEOUT_SECONDS: Final[float] = 45.0
API_RETRY_BACKOFF_SECONDS: Final[float] = 1.5
MAX_API_RETRIES: Final[int] = 1

# Short UI tagline (exact problem statement kept in config.py and README.md)
APP_TAGLINE: Final[str] = (
    "Plan weddings, birthdays and community events with budgets, timelines, "
    "vendor checklists and personalized ideas."
)

# Canonical T-minus stage offsets (in days before event date)
STAGE_DAYS_BEFORE_MAP: Final[dict[str, int]] = {
    "6 months out": 180,
    "3 months out": 90,
    "1 month out": 30,
    "2 weeks out": 14,
    "1 week out": 7,
    "1 day out": 1,
    "Event day": 0,
}

# Okabe-Ito colorblind-safe palette for charts
COLORBLIND_SAFE_PALETTE: Final[list[str]] = [
    "#0072B2",  # Blue
    "#E69F00",  # Orange
    "#009E73",  # Bluish green
    "#CC79A7",  # Reddish purple
    "#56B4E9",  # Sky blue
    "#D55E00",  # Vermilion
    "#F0E442",  # Yellow
    "#332288",  # Indigo
]
