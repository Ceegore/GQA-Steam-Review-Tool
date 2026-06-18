"""JSON exporter — pretty-prints the raw review list."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def reviews_to_json(reviews: list[dict[str, Any]], dest_path: Path) -> int:
    """Write ``reviews`` to a pretty-printed JSON file. Returns count."""
    dest_path.write_text(
        json.dumps(reviews, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(reviews)


__all__ = ["reviews_to_json"]