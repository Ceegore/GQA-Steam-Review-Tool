"""The full input passed to an exporter."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any


@dataclass
class ExportContext:
    """Everything an exporter needs to render a document."""
    app_id: int
    app_details: Optional[dict[str, Any]]
    reviews: list[dict[str, Any]]
    language_param: str
    review_filter: str
    review_type: str
    day_range: Optional[int]
    min_date_ts: Optional[int]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    keyword_list: Optional[list[str]] = None


__all__ = ["ExportContext"]