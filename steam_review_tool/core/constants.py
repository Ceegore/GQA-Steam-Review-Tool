"""Global constants used across the entire application.

Centralizes every URL, language list[Any], and feature flag in one place so
they can be referenced without import cycles.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Steam API endpoints
# ---------------------------------------------------------------------------

STEAM_API_BASE: str = "https://store.steampowered.com/api"
STEAM_REVIEWS_BASE: str = "https://store.steampowered.com/appreviews"

# All language codes accepted by Steam's reviews API.
# Source: https://partner.steamgames.com/doc/store/localization
STEAM_LANGUAGES: list[str] = [
    "all",
    "arabic", "bulgarian", "schinese", "tchinese", "czech", "danish", "dutch",
    "english", "finnish", "french", "german", "greek", "hungarian",
    "indonesian", "italian", "japanese", "koreana", "norwegian", "polish",
    "portuguese", "brazilian", "romanian", "russian", "spanish", "latam",
    "swedish", "thai", "turkish", "ukrainian", "vietnamese",
]

# Filter dropdown choices for the "Sort order" and "Review type" selectors.
REVIEW_FILTERS: list[str] = ["all", "recent", "updated"]
REVIEW_TYPES: list[str] = ["all", "positive", "negative"]

# ---------------------------------------------------------------------------
# Time-based filter presets
# ---------------------------------------------------------------------------
# Each preset is (label, hours). ``hours == 0`` means "no filter"
# (all-time). ``hours == -1`` triggers "custom date + time" mode,
# in which the caller reads the date+time entries.
SINCE_PRESETS: list[tuple[str, int]] = [
    ("all time",        0),
    ("last 1 hour",     1),
    ("last 2 hours",    2),
    ("last 3 hours",    3),
    ("last 4 hours",    4),
    ("last 5 hours",    5),
    ("last 6 hours",    6),
    ("last 12 hours",  12),
    ("last 24 hours",  24),
    ("last 3 days",    72),
    ("last 7 days",   168),
    ("custom (date + time)", -1),
]
SINCE_PRESET_LABELS: list[str] = [p[0] for p in SINCE_PRESETS]

# ---------------------------------------------------------------------------
# Default storage locations
# ---------------------------------------------------------------------------

# Default location for the per-game dump tree. The user can change this
# from the GUI ("Set dump folder..."). ``~/Documents`` is the most
# discoverable place on Windows; users can find their dumps without
# hunting through ``%APPDATA%``.
DEFAULT_DUMP_ROOT: Path = Path.home() / "Documents" / "SteamReviewDumps"

# Hidden config dir under the user's home (settings, resume cursors).
CONFIG_DIR: Path = Path.home() / ".steam_review_tool"

# ---------------------------------------------------------------------------
# Anti-detection snippet for the Playwright tab
# ---------------------------------------------------------------------------
# Strings injected into the browser context so Steam's storefront does
# not detect Playwright automation.
ANTI_DETECT_JS: str = (
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });\n"
    "window.chrome = window.chrome || { runtime: {}, loadTimes: function(){}, csi: function(){}, app: { isInstalled: false } };\n"
    "Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });\n"
    "Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });\n"
)

# Button labels Steam may show on age-gate / cookie / consent screens.
GATE_BUTTON_TEXTS: list[str] = [
    "View Page",
    "View Community Hub",
    "I am 18 or older",
    "I am 18 years or older",
    "Yes",
    "Continue",
    "OK",
    "I agree",
    "Accept All Cookies",
    "Accept",
]

# Realistic Chrome-on-Windows UA. Steam's review cache for new apps
# is sensitive to suspicious UAs and may return 0 reviews for bots.
DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Sleep between review API page requests to stay under Steam's rate limit.
STEAM_API_PAGE_DELAY_SEC: float = 0.4

# Sleep between Playwright in-page fetches.
PLAYWRIGHT_PAGE_DELAY_SEC: float = 0.4

# Default wait before evaluating scraping JS on a freshly loaded page.
# Tuned for slow Steam storefronts on first cold visit.
PLAYWRIGHT_JS_WAIT_SEC: float = 3.0

# Sleep between watch-mode polls (slightly shorter than page-to-page).
STEAM_POLL_DELAY_SEC: float = 0.3

# Aliases for backwards compat — ``REVIEW_SORT`` was previously a public
# export consumed by tab files. Both names now refer to the same data.
REVIEW_SORT: list[str] = REVIEW_FILTERS
REVIEW_TYPE: list[str] = REVIEW_TYPES


__all__ = [
    "DEFAULT_USER_AGENT",
    "STEAM_API_BASE",
    "STEAM_REVIEWS_BASE",
    "STEAM_LANGUAGES",
    "REVIEW_FILTERS",
    "REVIEW_TYPES",
    "REVIEW_SORT",
    "REVIEW_TYPE",
    "GATE_BUTTON_TEXTS",
    "ANTI_DETECT_JS",
    "STEAM_API_PAGE_DELAY_SEC",
    "PLAYWRIGHT_PAGE_DELAY_SEC",
    "PLAYWRIGHT_JS_WAIT_SEC",
    "STEAM_POLL_DELAY_SEC",
    "SINCE_PRESETS",
    "SINCE_PRESET_LABELS",
    "DEFAULT_DUMP_ROOT",
    "CONFIG_DIR",
]