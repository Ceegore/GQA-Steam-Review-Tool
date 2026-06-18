"""Tiny synchronous pub/sub event bus.

Used so the UI tabs can publish events ("review.fetch.completed") and
controllers in another module can subscribe — without either side
importing the other. This is the mechanism that breaks circular
dependencies between UI and Workflow layers.
"""
from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Any, Callable

from .logger import get_logger

_log = get_logger(__name__)


class SimpleEventBus:
    """Thread-safe synchronous event bus.

    Subscribers are called in registration order on the publisher's
    thread. Exceptions in a subscriber are logged but do not stop
    delivery to subsequent subscribers.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., None]]] = defaultdict(list[Any])
        self._lock = Lock()

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        with self._lock:
            self._listeners[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., None]) -> None:
        with self._lock:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass

    def subscribe_once(
        self, event: str, callback: Callable[..., None],
    ) -> None:
        """Subscribe a one-shot callback. Auto-unsubscribes after the
        first invocation. Re-registers itself if the publisher
        publishes multiple times without us being notified.
        """
        def _wrapper(**payload: Any) -> None:
            try:
                callback(**payload)
            finally:
                self.unsubscribe(event, _wrapper)
        self.subscribe(event, _wrapper)

    def publish(self, event: str, **payload: Any) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event, ()))
        for cb in callbacks:
            try:
                cb(**payload)
            except Exception as exc:  # pragma: no cover - defensive
                _log.exception("subscriber for %r raised", event)


# Module-level singleton (the app uses one global bus). Tests can
# instantiate their own bus instead of patching this.
bus = SimpleEventBus()


__all__ = ["SimpleEventBus", "bus"]