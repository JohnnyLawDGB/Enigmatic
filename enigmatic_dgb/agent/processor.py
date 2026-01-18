"""Event processing pipeline for hybrid agent workflows."""

from __future__ import annotations

from typing import List

from .actions import ActionRequest
from .events import AgentEvent
from .rules import RuleEngine
from .state import AgentStateStore


class EventProcessor:
    def __init__(self, state: AgentStateStore, rules: RuleEngine) -> None:
        self.state = state
        self.rules = rules

    def process(self, event: AgentEvent) -> List[ActionRequest]:
        if self.state.is_event_processed(event.event_id):
            return []
        self.state.record_event(event)
        self.state.mark_event_processed(event.event_id)
        actions = self.rules.evaluate(event, self.state)
        for action in actions:
            self.state.add_pending_action(action)
        return actions
