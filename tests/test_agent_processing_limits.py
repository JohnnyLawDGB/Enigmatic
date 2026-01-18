from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from enigmatic_dgb.agent.actions import ActionRequest
from enigmatic_dgb.agent.events import AgentEvent
from enigmatic_dgb.agent.processor import EventProcessor
from enigmatic_dgb.agent.rules import RuleEngine
from enigmatic_dgb.agent.state import AgentStateStore


@dataclass
class ManyActionsRule:
    rule_id: str = "many_actions"

    def evaluate(self, event, state):
        return [ActionRequest.create(action_type="notify") for _ in range(10)]

    def debounce_key(self, event):
        return "many_actions"


@dataclass
class SingleActionRule:
    rule_id: str = "single_action"

    def evaluate(self, event, state):
        return [ActionRequest.create(action_type="notify")]

    def debounce_key(self, event):
        return "single_action"


def test_max_actions_per_event() -> None:
    state = AgentStateStore()
    processor = EventProcessor(
        state,
        RuleEngine([ManyActionsRule()]),
        max_actions_per_event=3,
    )
    event = AgentEvent.create(event_type="transaction", source="demo")
    actions = processor.process(event)
    assert len(actions) == 3
    assert len(state.list_pending_actions()) == 3
    assert processor.metrics.actions_dropped == 7


def test_throttle_limits_per_source() -> None:
    state = AgentStateStore()
    processor = EventProcessor(
        state,
        RuleEngine([SingleActionRule()], debounce_seconds=0),
        max_events_per_source_per_minute=2,
        throttle_window_seconds=60,
    )
    events = [
        AgentEvent.create(event_type="transaction", source="demo"),
        AgentEvent.create(event_type="transaction", source="demo"),
        AgentEvent.create(event_type="transaction", source="demo"),
    ]
    results = [processor.process(event) for event in events]
    assert len(results[0]) == 1
    assert len(results[1]) == 1
    assert results[2] == []
    assert len(state.list_pending_actions()) == 2
    assert len(state.get_recent_events(10)) == 3
    assert state.is_event_processed(events[2].event_id) is True
    assert processor.metrics.events_throttled == 1


def test_debounce_out_of_order_event() -> None:
    state = AgentStateStore()
    rule_engine = RuleEngine([SingleActionRule()], debounce_seconds=60)
    now = datetime.now(timezone.utc)
    first = AgentEvent.create(
        event_type="transaction",
        source="demo",
        occurred_at=now,
    )
    older = AgentEvent.create(
        event_type="transaction",
        source="demo",
        occurred_at=now - timedelta(seconds=30),
    )
    assert rule_engine.evaluate(first, state)
    assert rule_engine.evaluate(older, state) == []


def test_processor_tracks_duplicates() -> None:
    state = AgentStateStore()
    processor = EventProcessor(state, RuleEngine([SingleActionRule()]))
    event = AgentEvent.create(event_type="transaction", source="demo")
    processor.process(event)
    processor.process(event)
    assert processor.metrics.events_duplicates == 1
