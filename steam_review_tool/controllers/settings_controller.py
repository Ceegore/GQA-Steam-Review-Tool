"""Settings controller.

Owns the apply step after a settings change. Each controller subscribes
to the event bus rather than directly calling one another's methods.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional, Any

from ..core.event_bus import bus
from ..services import settings_store
from ..ui.popup_settings import SettingsDialog


class SettingsController:
    """Reactive settings store + UI binding."""

    SETTINGS_CHANGED = "settings.changed"

    def __init__(self, master) -> None:
        self.master = master
        self._dialog = SettingsDialog(master)

    def open(self) -> None:
        self._dialog.open(save_cb=self._on_saved)

    def _on_saved(self, data: dict[str, Any]) -> None:
        bus.publish(self.SETTINGS_CHANGED, data=data)
        bus.publish("settings.applied", data=data)


__all__ = ["SettingsController"]