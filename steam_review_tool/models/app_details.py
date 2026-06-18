"""App metadata returned by ``get_app_details``."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class AppDetails:
    """Sub-set of Steam app details that the exporter cares about."""
    app_id: int
    name: str = ""
    developer: str = ""
    publisher: str = ""
    release_date: str = ""
    platforms: dict[str, Any] = field(default_factory=dict[str, Any])
    header_image: str = ""
    short_description: str = ""
    raw: Optional[dict[str, Any]] = None  # the original dict[str, Any] for full-data export


__all__ = ["AppDetails"]