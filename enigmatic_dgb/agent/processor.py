"""Event processing pipeline for hybrid agent workflows."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Dict, List

from .actions import ActionRequest
from .events import AgentEvent
from .rules import RuleEngine
from .state import AgentStateStore


@dataclass
class ProcessorMetrics:
    events_seen: int = 0
    events_processed: int = 0
    events_throttled: int = 0
    events_duplicates: int = 0
    actions_created: int = 0
    actions_dropped: int = 0


@dataclass
class EventProcessor:
    state: AgentStateStore
    rules: RuleEngine
    max_actions_per_event: int = 5
    max_events_per_source_per_minute: int = 120
    throttle_window_seconds: int = 60
    metrics: ProcessorMetrics = field(default_factory=ProcessorMetrics)
    _source_windows: Dict[str, Deque[datetime]] = field(
        default_factory=lambda: defaultdict(deque), init=False
    )

    def process(self, event: AgentEvent) -> List[ActionRequest]:
        self.metrics.events_seen += 1
        if self.state.is_event_processed(event.event_id):
            self.metrics.events_duplicates += 1
            return []
        if self._is_throttled(event):
            self.metrics.events_throttled += 1
            self.state.record_event(event)
            self.state.mark_event_processed(event.event_id)
            return []
        self.state.record_event(event)
        self.state.mark_event_processed(event.event_id)
        actions = self.rules.evaluate(event, self.state)
        if self.max_actions_per_event > 0:
            if len(actions) > self.max_actions_per_event:
                self.metrics.actions_dropped += len(actions) - self.max_actions_per_event
                actions = actions[: self.max_actions_per_event]
        for action in actions:
            self.state.add_pending_action(action)
        self.metrics.events_processed += 1
        self.metrics.actions_created += len(actions)
        return actions

    def _is_throttled(self, event: AgentEvent) -> bool:
        if self.max_events_per_source_per_minute <= 0:
            return False
        source = event.source or "unknown"
        window = self._source_windows[source]
        cutoff = event.occurred_at - timedelta(seconds=self.throttle_window_seconds)
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= self.max_events_per_source_per_minute:
            return True
        window.append(event.occurred_at)
        return False
