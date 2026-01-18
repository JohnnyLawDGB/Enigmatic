from dataclasses import dataclass

from enigmatic_dgb.agent.actions import ActionRequest
from enigmatic_dgb.agent.coordinator import AgentCoordinator
from enigmatic_dgb.agent.dispatcher import ActionDispatcher, build_notify_handler
from enigmatic_dgb.agent.events import AgentEvent
from enigmatic_dgb.agent.policy import PolicyEngine
from enigmatic_dgb.agent.processor import EventProcessor
from enigmatic_dgb.agent.rules import RuleEngine
from enigmatic_dgb.agent.state import AgentStateStore


def test_policy_engine_respects_high_risk() -> None:
    state = AgentStateStore()
    policy = PolicyEngine()
    low_risk = ActionRequest.create(action_type="notify")
    decision = policy.evaluate(low_risk, state)
    assert decision.allowed is True

    high_risk = ActionRequest.create(action_type="send_transaction")
    decision = policy.evaluate(high_risk, state)
    assert decision.allowed is False

    flagged = ActionRequest.create(action_type="notify", requires_confirmation=True)
    decision = policy.evaluate(flagged, state)
    assert decision.allowed is False


@dataclass
class SendRule:
    rule_id: str = "send_rule"

    def evaluate(self, event, state):
        return [
            ActionRequest.create(
                action_type="send_transaction",
                payload={"amount": 1.0},
            )
        ]

    def debounce_key(self, event):
        return "send_rule"


@dataclass
class NotifyRule:
    rule_id: str = "notify_rule"

    def evaluate(self, event, state):
        return [
            ActionRequest.create(
                action_type="notify",
                payload={"message": "auto"},
            )
        ]

    def debounce_key(self, event):
        return "notify_rule"


def test_coordinator_auto_dispatch() -> None:
    state = AgentStateStore()
    rule_engine = RuleEngine([NotifyRule()])
    processor = EventProcessor(state, rule_engine)
    policy = PolicyEngine()
    notifications = []
    dispatcher = ActionDispatcher(
        {
            "notify": build_notify_handler(
                lambda message, payload: notifications.append((message, payload))
            )
        }
    )
    coordinator = AgentCoordinator(state, processor, policy, dispatcher)
    event = AgentEvent.create(
        event_type="transaction",
        source="rpc",
        payload={"amount": 5.0},
    )
    coordinator.handle_event(event)
    assert state.list_pending_actions() == []
    assert state.get_action_history(1)[0].action_type == "notify"
    assert notifications[0][0] == "auto"


def test_coordinator_requires_confirmation() -> None:
    state = AgentStateStore()
    rule_engine = RuleEngine([SendRule()])
    processor = EventProcessor(state, rule_engine)
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
    event = AgentEvent.create(event_type="transaction", source="rpc")
    coordinator.handle_event(event)
    assert state.list_pending_actions() == []
    history = state.get_action_history(1)
    assert history[0].status.value == "rejected"
    assert notices[0][0] == "action_blocked"
