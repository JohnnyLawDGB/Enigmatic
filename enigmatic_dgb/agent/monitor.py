"""Event source adapters and polling monitor."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Event
from typing import Callable, Deque, Iterable, List, Protocol

from .events import AgentEvent
from .processor import EventProcessor


class EventSource(Protocol):
    def poll(self) -> List[AgentEvent]:
        ...


class QueueEventSource:
    def __init__(
        self,
        events: Iterable[AgentEvent] | None = None,
        *,
        max_queue_size: int = 1000,
        drop_strategy: str = "drop_oldest",
    ) -> None:
        self._queue: Deque[AgentEvent] = deque(events or [])
        self.max_queue_size = max_queue_size
        self.drop_strategy = drop_strategy
        self.dropped_count = 0

    def push(self, event: AgentEvent) -> None:
        if self.max_queue_size > 0 and len(self._queue) >= self.max_queue_size:
            if self._drop_for_capacity():
                return
        self._queue.append(event)

    def poll(self) -> List[AgentEvent]:
        events = list(self._queue)
        self._queue.clear()
        return events

    def _drop_for_capacity(self) -> bool:
        if self.drop_strategy == "drop_newest":
            self.dropped_count += 1
            return True
        if self._queue:
            self._queue.popleft()
            self.dropped_count += 1
        return False


@dataclass
class MonitorMetrics:
    polls: int = 0
    events_seen: int = 0
    events_processed: int = 0
    errors: int = 0


class EventMonitor:
    def __init__(
        self,
        source: EventSource,
        processor: EventProcessor,
        *,
        poll_interval_seconds: float = 5.0,
        on_error: Callable[[Exception], None] | None = None,
        max_events_per_poll: int | None = None,
    ) -> None:
        self.source = source
        self.processor = processor
        self.poll_interval_seconds = poll_interval_seconds
        self.on_error = on_error
        self.max_events_per_poll = max_events_per_poll
        self.metrics = MonitorMetrics()

    def run_once(self) -> List[AgentEvent]:
        handled: List[AgentEvent] = []
        self.metrics.polls += 1
        try:
            events = self.source.poll()
        except Exception as exc:  # pragma: no cover - defensive logging
            self.metrics.errors += 1
            if self.on_error:
                self.on_error(exc)
            return handled
        if self.max_events_per_poll is not None and self.max_events_per_poll > 0:
            events = events[: self.max_events_per_poll]
        self.metrics.events_seen += len(events)
        for event in events:
            self.processor.process(event)
            handled.append(event)
        self.metrics.events_processed += len(handled)
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
