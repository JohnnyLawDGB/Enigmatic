from dataclasses import dataclass

from enigmatic_dgb.agent.actions import ActionRequest, ActionStatus
from enigmatic_dgb.agent.coordinator import AgentCoordinator
from enigmatic_dgb.agent.dispatcher import ActionDispatcher, build_notify_handler
from enigmatic_dgb.agent.events import AgentEvent
from enigmatic_dgb.agent.monitor import EventMonitor, QueueEventSource
from enigmatic_dgb.agent.policy import PolicyEngine
from enigmatic_dgb.agent.processor import EventProcessor
from enigmatic_dgb.agent.rules import HighValueAlertRule, RuleEngine
from enigmatic_dgb.agent.state import AgentStateStore


@dataclass
class UnknownActionRule:
    rule_id: str = "unknown_action"

    def evaluate(self, event, state):
        return [ActionRequest.create(action_type="do_unknown")]

    def debounce_key(self, event):
        return "unknown_action"


@dataclass
class HighRiskRule:
    rule_id: str = "high_risk"

    def evaluate(self, event, state):
        return [ActionRequest.create(action_type="send_transaction")]

    def debounce_key(self, event):
        return "high_risk"


def test_monitor_to_coordinator_dispatch() -> None:
    state = AgentStateStore()
    rules = RuleEngine([HighValueAlertRule(default_threshold=1.0)])
    processor = EventProcessor(state, rules)
    policy = PolicyEngine()
    notifications = []
    dispatcher = ActionDispatcher(
        {"notify": build_notify_handler(lambda msg, payload: notifications.append(msg))}
    )
    coordinator = AgentCoordinator(state, processor, policy, dispatcher)
    source = QueueEventSource(
        [
            AgentEvent.create(
                event_type="transaction",
                source="demo",
                payload={"amount": 5.0},
            )
        ]
    )
    for event in source.poll():
        coordinator.handle_event(event)

    assert state.list_pending_actions() == []
    assert state.get_action_history(1)[0].action_type == "notify"
    assert notifications == ["High-value transaction detected: 5.0 (threshold 1.0)."]


def test_dispatcher_missing_handler_records_failure() -> None:
    state = AgentStateStore()
    rules = RuleEngine([UnknownActionRule()])
    processor = EventProcessor(state, rules)
    policy = PolicyEngine()
    notices = []
    dispatcher = ActionDispatcher({})
    coordinator = AgentCoordinator(
        state,
        processor,
        policy,
        dispatcher,
        notifier=lambda kind, payload: notices.append((kind, payload)),
    )
    coordinator.handle_event(AgentEvent.create(event_type="transaction", source="demo"))

    history = state.get_action_history(1)
    assert history[0].status == ActionStatus.FAILED
    assert "No handler registered" in (history[0].error or "")
    assert notices[-1][0] == "action_result"


def test_policy_blocks_high_risk_action() -> None:
    state = AgentStateStore()
    rules = RuleEngine([HighRiskRule()])
    processor = EventProcessor(state, rules)
    policy = PolicyEngine()
    notices = []
    dispatcher = ActionDispatcher({})
    coordinator = AgentCoordinator(
        state,
        processor,
        policy,
        dispatcher,
        notifier=lambda kind, payload: notices.append((kind, payload)),
    )
    coordinator.handle_event(AgentEvent.create(event_type="transaction", source="demo"))

    assert state.list_pending_actions() == []
    history = state.get_action_history(1)
    assert history[0].status == ActionStatus.REJECTED
    assert notices[-1][0] == "action_blocked"


def test_monitor_runs_processor() -> None:
    state = AgentStateStore()
    processor = EventProcessor(state, RuleEngine([]))
    source = QueueEventSource([AgentEvent.create(event_type="transaction", source="demo")])
    monitor = EventMonitor(source, processor)

    handled = monitor.run_once()
    assert len(handled) == 1
    assert state.is_event_processed(handled[0].event_id) is True
    assert monitor.metrics.polls == 1
    assert monitor.metrics.events_seen == 1
    assert monitor.metrics.events_processed == 1


def test_queue_event_source_drop_oldest() -> None:
    source = QueueEventSource(max_queue_size=2, drop_strategy="drop_oldest")
    source.push(AgentEvent.create(event_type="a", source="demo"))
    source.push(AgentEvent.create(event_type="b", source="demo"))
    source.push(AgentEvent.create(event_type="c", source="demo"))
    events = source.poll()
    assert [event.event_type for event in events] == ["b", "c"]
    assert source.dropped_count == 1


def test_queue_event_source_drop_newest() -> None:
    source = QueueEventSource(max_queue_size=2, drop_strategy="drop_newest")
    source.push(AgentEvent.create(event_type="a", source="demo"))
    source.push(AgentEvent.create(event_type="b", source="demo"))
    source.push(AgentEvent.create(event_type="c", source="demo"))
    events = source.poll()
    assert [event.event_type for event in events] == ["a", "b"]
    assert source.dropped_count == 1


def test_monitor_limits_events_per_poll() -> None:
    state = AgentStateStore()
    processor = EventProcessor(state, RuleEngine([]))
    source = QueueEventSource(
        [
            AgentEvent.create(event_type="a", source="demo"),
            AgentEvent.create(event_type="b", source="demo"),
            AgentEvent.create(event_type="c", source="demo"),
        ]
    )
    monitor = EventMonitor(source, processor, max_events_per_poll=2)

    handled = monitor.run_once()
    assert len(handled) == 2
    assert monitor.metrics.events_seen == 2
