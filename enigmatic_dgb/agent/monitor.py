"""Event source adapters and polling monitor."""

from __future__ import annotations

import time
from collections import deque
from threading import Event
from typing import Callable, Deque, Iterable, List, Protocol

from .events import AgentEvent
from .processor import EventProcessor


class EventSource(Protocol):
    def poll(self) -> List[AgentEvent]:
        ...


class QueueEventSource:
    def __init__(self, events: Iterable[AgentEvent] | None = None) -> None:
        self._queue: Deque[AgentEvent] = deque(events or [])

    def push(self, event: AgentEvent) -> None:
        self._queue.append(event)

    def poll(self) -> List[AgentEvent]:
        events = list(self._queue)
        self._queue.clear()
        return events


class EventMonitor:
    def __init__(
        self,
        source: EventSource,
        processor: EventProcessor,
        *,
        poll_interval_seconds: float = 5.0,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.source = source
        self.processor = processor
        self.poll_interval_seconds = poll_interval_seconds
        self.on_error = on_error

    def run_once(self) -> List[AgentEvent]:
        handled: List[AgentEvent] = []
        for event in self.source.poll():
            self.processor.process(event)
            handled.append(event)
        return handled

    def run_forever(self, *, stop_event: Event | None = None) -> None:
        while True:
            if stop_event and stop_event.is_set():
                return
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - defensive logging
                if self.on_error:
                    self.on_error(exc)
            time.sleep(self.poll_interval_seconds)
