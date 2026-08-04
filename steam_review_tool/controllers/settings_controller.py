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

    # Two distinct events: ``SETTINGS_CHANGED`` is published as soon
    # as the user clicks "Save" (use it to *react* to the new
    # settings, e.g. re-pick the dump root). ``SETTINGS_APPLIED`` is
    # the post-everything signal that the dialog was dismissed with
    # the values committed to disk — useful for status-bar updates
    # that should not fire on transient in-progress edits.
    SETTINGS_CHANGED = "settings.changed"
    SETTINGS_APPLIED = "settings.applied"

    def __init__(self, master) -> None:
        self.master = master
        self._dialog = SettingsDialog(master)

    def open(self) -> None:
        self._dialog.open(save_cb=self._on_saved)

    def _on_saved(self, data: dict[str, Any]) -> None:
        bus.publish(self.SETTINGS_CHANGED, data=data)
        bus.publish(self.SETTINGS_APPLIED, data=data)


__all__ = ["SettingsController"]