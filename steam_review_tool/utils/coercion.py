"""Safe coercion helpers for review-dict fields.

The Steam API normally returns integer fields (votes_up, votes_funny,
comment_count, timestamp_created, ...), but normalised review dicts
(e.g. from the Apify client or a hand-rolled test) can carry ``None``
or non-numeric strings. Without a helper, every call site that does
``int(r.get("votes_up", 0) or 0)`` crashes the whole export on a
single malformed row.

Pattern: ``safe_int(r, "votes_up", default=0)`` returns the int value,
or ``default`` if the value is missing, ``None``, or non-numeric.

This is the single-source-of-truth for the
``int(r.get("KEY", 0) or 0)`` pattern that used to live in
``controllers/filter_controller.py``, ``services/review_analyzer.py``,
``exporters/csv_exporter.py``, ``exporters/export_orchestrator.py``,
``exporters/markdown_helpers.py``, ``exporters/per_language_exporter.py``,
``services/pre_ai_digest.py``, ``services/steam_api_service.py``,
``services/playwright_subprocess_scraper.py``,
``controllers/api_workflow.py``, etc.
"""
from __future__ import annotations

from typing import Any


def safe_int(
    source: Any,
    key: str,
    default: int = 0,
) -> int:
    """Read ``source[key]`` and coerce to ``int``, falling back to
    ``default`` on any failure.

    Accepts dicts and any other object that implements ``__getitem__``
    (e.g. dataclasses, attrs classes). For non-container sources,
    returns ``default``.

    Handles:
    - key missing → ``default``
    - ``None`` value → ``default``
    - ``int`` value → unchanged
    - ``bool`` value → ``int(value)`` (explicit, even though bool
      is a subclass of int in Python)
    - ``float`` value → ``int(value)`` if finite, else ``default``
    - ``str`` value → ``int(s)`` if numeric, else ``default``
    - other types → ``default``
    """
    if source is None:
        return default
    try:
        value = source[key]
    except (KeyError, TypeError, IndexError):
        return default
    return safe_coerce_int(value, default)


def safe_coerce_int(value: Any, default: int = 0) -> int:
    """Coerce a single ``value`` to ``int``, falling back to ``default``.

    Companion to :func:`safe_int` — used directly when the value has
    already been pulled out of a dict (e.g. inside a list comprehension
    that needs to keep the original row reference).
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except (OverflowError, ValueError):
            return default
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except (TypeError, ValueError):
            return default
    return default


__all__ = ["safe_int", "safe_coerce_int"]
