"""Settings controller.

Owns the apply step after a settings change. Each controller subscribes
to the event bus rather than directly calling one another's methods.
"""
from __future__ import annotations

from typing import Any

from ..core.event_bus import bus
from ..ui.popup_settings import SettingsDialog


class SettingsController:
    """Reactive settings store + UI binding."""

    # ``SETTINGS_CHANGED`` is published as soon as the user clicks
    # "Save" (use it to *react* to the new settings, e.g. re-pick
    # the dump root).
    #
    # The previous version also published a ``SETTINGS_APPLIED``
    # event. A R20-1 audit found zero subscribers for
    # ``settings.applied`` (the only listener was
    # ``app_window`` and it subscribed to ``settings.changed``
    # not ``settings.applied``) — the event was dead. The
    # "post-everything" comment in the original docstring
    # was misleading: no UI element needed a separate
    # "applied" signal because the same handler that
    # reacts to ``SETTINGS_CHANGED`` ALSO runs after the
    # on-disk save (the dialog persists before calling
    # ``save_cb``). Removed in R20-1 to eliminate the
    # drift hazard.
    SETTINGS_CHANGED = "settings.changed"

    def __init__(self, master) -> None:
        self.master = master
        self._dialog = SettingsDialog(master)

    def open(self) -> None:
        self._dialog.open(save_cb=self._on_saved)

    def _on_saved(self, data: dict[str, Any]) -> None:
        bus.publish(self.SETTINGS_CHANGED, data=data)


__all__ = ["SettingsController"]