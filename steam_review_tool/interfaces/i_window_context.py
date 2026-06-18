"""Window context interface — exposes shared widgets/state to controllers.

CustomTkinter widgets must live in a single widget tree, so we pass
the same parent/handle to every controller through a small interface.
"""
from __future__ import annotations

from typing import Callable, Optional, Protocol, Any


class IWindowContext(Protocol):
    """Lightweight facade shared across tabs and controllers."""

    root: object              # the CTk application instance
    status_label: object      # the status-bar label
    info_panels: list[Any]         # the right-hand info panels per tab

    def log(self, msg: str) -> None: ...

    def set_status(self, text: str) -> None: ...

    def set_busy(self, busy: bool) -> None: ...

    def open_store_page(self, app_id: int) -> None: ...


__all__ = ["IWindowContext"]