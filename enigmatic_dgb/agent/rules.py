"""Rule engine for evaluating agent events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Protocol

from .actions import ActionRequest
from .events import AgentEvent
from .state import AgentStateStore


class Rule(Protocol):
    rule_id: str

    def evaluate(self, event: AgentEvent, state: AgentStateStore) -> List[ActionRequest]:
        ...

    def debounce_key(self, event: AgentEvent) -> str:
        ...


@dataclass
class RuleEngine:
    rules: List[Rule]
    debounce_seconds: int = 30
    _last_fired: dict[str, datetime] = field(default_factory=dict, init=False)

    def evaluate(self, event: AgentEvent, state: AgentStateStore) -> List[ActionRequest]:
        actions: List[ActionRequest] = []
        for rule in self.rules:
            key = rule.debounce_key(event)
            if self._is_debounced(key, event.occurred_at):
                continue
            rule_actions = rule.evaluate(event, state)
            if rule_actions:
                self._last_fired[key] = event.occurred_at
                actions.extend(rule_actions)
        return actions

    def _is_debounced(self, key: str, occurred_at: datetime) -> bool:
        last = self._last_fired.get(key)
        if not last:
            return False
        delta = (occurred_at - last).total_seconds()
        return delta < self.debounce_seconds


@dataclass
class HighValueAlertRule:
    rule_id: str = "high_value_transaction"
    event_types: tuple[str, ...] = ("transaction", "incoming_transaction")
    default_threshold: float = 1.0
    preference_key: str = "alert_threshold"

    def evaluate(self, event: AgentEvent, state: AgentStateStore) -> List[ActionRequest]:
        if event.event_type not in self.event_types:
            return []
        amount = event.payload.get("amount")
        if not isinstance(amount, (int, float)):
            return []
        preferences = state.get_preferences()
        threshold = preferences.get(self.preference_key, self.default_threshold)
        if amount < float(threshold):
            return []
        payload = {
            "message": (
                f"High-value {event.event_type} detected: {amount} "
                f"(threshold {threshold})."
            ),
            "event_id": event.event_id,
            "amount": amount,
            "threshold": float(threshold),
            "source": event.source,
        }
        return [
            ActionRequest.create(
                action_type="notify",
                payload=payload,
                requires_confirmation=False,
            )
        ]

    def debounce_key(self, event: AgentEvent) -> str:
        return f"{self.rule_id}:{event.source}"
