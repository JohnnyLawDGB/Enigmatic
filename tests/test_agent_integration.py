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
