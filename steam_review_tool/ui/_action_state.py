"""Action-button enable / disable state management.

Shared mixin for the API and Playwright tab controllers so both
tabs enable the right buttons at the right times:

* ``Fetch`` (or ``Scrape``) is enabled when a game is loaded.
* ``Resume`` is enabled when the resume store has a cursor for
  the current app.
* ``Fetch new`` is enabled when a game is loaded AND we already
  have reviews (to dedup against).
* ``Export to .md`` is enabled when we have reviews loaded.
* ``Stop`` is enabled while a fetch / scrape is running.
* The currently-running button (``Fetch`` / ``Scrape``) is disabled.

The mixin subscribes to the workflow's bus events
(``FETCH_STARTED`` / ``FETCH_COMPLETED`` / ``FETCH_FAILED`` and the
Playwright equivalents) and updates buttons in response. The
controller just calls :meth:`refresh_action_states` whenever the
underlying state changes (e.g. on ``app.loaded``).
"""
from __future__ import annotations

from typing import Any, Optional

from ..core.event_bus import bus


class ActionStateMixin:
    """Mixin that manages enable/disable state for the action-bar buttons.

    Subclasses must provide the following attributes:

    * ``self.master`` — the App (provides ``app_id``, ``reviews``).
    * ``self._action_refs`` — the ``ApiActionRefs`` /
      ``PwActionRefs`` holding the actual buttons.
    * ``self._log(msg)`` — log callback.

    Optional attributes the mixin consults:

    * ``self._bus_subs_state`` — list of ``(event, callback)`` tuples;
      the mixin populates it on construction and the controller is
      responsible for unsubscribing on close if desired.
    * ``self._scrape_running`` / ``self._watching`` — booleans
      reflecting long-running worker state (Playwright uses the
      first; the API tab uses the second).
    """

    # The constants below are set on the *subclass* instance by the
    # controller's ``__init__``. They name the bus events that mark the
    # start / end of a fetch or scrape. The controller wires the real
    # event strings (which can differ between the API and Playwright
    # workflows) onto ``self._bus_subs_state``.

    def _set_btn(self, attr: str, state: str) -> None:
        """Set ``state`` on a button in ``self._action_refs``.

        Silently no-ops if the widget is missing (e.g. tab not built
        yet) so this is safe to call from ``__init__``.
        """
        btn = getattr(self._action_refs, attr, None)
        if btn is None:
            return
        try:
            btn.configure(state=state)
        except Exception:
            pass

    def _has_saved_cursor(self, source: str) -> bool:
        """``True`` iff a resume cursor exists for ``(source, app_id)``."""
        app_id = getattr(self.master, "app_id", None)
        if app_id is None:
            return False
        try:
            from ..services.resume_store import get as resume_get
            saved = resume_get(source, int(app_id))
            return bool(saved and saved.get("cursor"))
        except Exception:
            return False

    def _refresh_button_states(self, *, source: str) -> None:
        """Re-derive every action button's enable/disable state.

        Called after a game is loaded, after fetch / scrape
        completes, and after a watch toggle. Subclasses with
        additional buttons can call this directly.
        """
        has_app = getattr(self.master, "app_id", None) is not None
        has_reviews = bool(getattr(self.master, "reviews", None))
        watching = bool(getattr(self, "_watching", False))
        scraping = bool(getattr(self, "_scrape_running", False))

        fetch_attr = "fetch_btn" if hasattr(self._action_refs, "fetch_btn") else "scrape_btn"
        self._set_btn(fetch_attr, "normal" if has_app else "disabled")
        self._set_btn("resume_btn",
                      "normal" if has_app and self._has_saved_cursor(source) else "disabled")
        self._set_btn("fetch_new_btn",
                      "normal" if has_app and has_reviews else "disabled")
        self._set_btn("export_btn", "normal" if has_reviews else "disabled")
        # Stop is enabled only while a fetch / scrape / watch is running.
        running = watching or scraping
        self._set_btn("stop_btn", "normal" if running else "disabled")
        # The watch button is API-tab-specific; enable only when not
        # already watching.
        if hasattr(self._action_refs, "watch_btn"):
            self._set_btn(
                "watch_btn",
                "normal" if has_app and not watching else "disabled",
            )

    # ---- bus-handler factories ---------------------------------------

    def install_action_state_bus(
        self,
        *,
        started_event: str,
        completed_event: str,
        failed_event: str,
        source: str,
    ) -> None:
        """Wire ``FETCH_*`` / ``SCRAPE_*`` events to button-state updates.

        ``source`` is the resume-store key (``"api"`` or ``"pw"``).
        """
        self._bus_subs_state: list[tuple[str, Any]] = [
            (started_event,
             lambda **kw: self._on_fetch_started()),
            (completed_event,
             lambda **kw: self._on_fetch_completed(kw, source=source)),
            (failed_event,
             lambda **kw: self._on_fetch_failed(source=source)),
        ]
        for event, cb in self._bus_subs_state:
            bus.subscribe(event, cb)

    def _on_fetch_started(self) -> None:
        """Disable start / resume / fetch-new; enable Stop."""
        for attr in ("fetch_btn", "scrape_btn", "resume_btn",
                     "fetch_new_btn", "watch_btn"):
            self._set_btn(attr, "disabled")
        self._set_btn("stop_btn", "normal")

    def _on_fetch_completed(self, kw: dict, *, source: str) -> None:
        """Restore buttons; enable Export + Fetch-new when reviews arrived."""
        reviews = kw.get("reviews") or []
        self.master.reviews = reviews
        self._refresh_button_states(source=source)
        if reviews:
            self._log(f"Fetch done — {len(reviews)} reviews ready to export.")

    def _on_fetch_failed(self, *, source: str) -> None:
        """Restore buttons; don't force-enable Export (data may be partial)."""
        self._refresh_button_states(source=source)


__all__ = ["ActionStateMixin"]
