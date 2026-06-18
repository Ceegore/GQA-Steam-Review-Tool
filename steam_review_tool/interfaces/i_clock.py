"""Clock interface — testable time source."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol


class IClock(Protocol):
    """A pluggable clock.

    Production: returns ``datetime.now(BERLIN)``.
    Tests: returns a fixed value to make time-dependent code
    deterministic.
    """

    def now(self) -> datetime: ...


__all__ = ["IClock"]