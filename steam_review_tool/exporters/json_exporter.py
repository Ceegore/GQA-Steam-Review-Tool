"""JSON exporter — pretty-prints the raw review list."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.atomic_write import atomic_write_text


def reviews_to_json(reviews: list[dict[str, Any]], dest_path: Path) -> int:
    """Write ``reviews`` to a pretty-printed JSON file. Returns count.

    The write is **atomic** — a crash mid-write cannot leave a
    half-written ``.json`` file behind. The previous
    implementation wrote via ``dest_path.write_text(...)``
    which was non-atomic; a partial ``.json`` would survive
    an unexpected exit and would also be unparseable on the
    next load. The export orchestrator had already worked
    around this by calling ``atomic_write_text`` directly
    (private ``_write_json_atomic``); this R16 fix moves the
    atomic pattern into the public function so any caller
    (including tests) gets the safe behaviour.
    """
    atomic_write_text(
        dest_path,
        json.dumps(reviews, indent=2, ensure_ascii=False),
    )
    return len(reviews)


__all__ = ["reviews_to_json"]
