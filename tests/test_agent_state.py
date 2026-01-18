from datetime import datetime, timezone

from enigmatic_dgb.agent.actions import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    action_request_from_dict,
    action_request_to_dict,
    action_result_from_dict,
    action_result_to_dict,
)
from enigmatic_dgb.agent.events import (
    AgentEvent,
    EventSeverity,
    event_from_dict,
    event_to_dict,
)
from enigmatic_dgb.agent.monitor import QueueEventSource
from enigmatic_dgb.agent.processor import EventProcessor
from enigmatic_dgb.agent.rules import HighValueAlertRule, RuleEngine
from enigmatic_dgb.agent.state import AgentStateStore


def test_event_roundtrip() -> None:
    event = AgentEvent.create(
        event_type="tx_received",
        source="rpc",
        payload={"amount": 1.25},
        severity=EventSeverity.WARNING,
        tags=["alert", "funds"],
    )
    data = event_to_dict(event)
    restored = event_from_dict(data)
    assert restored.event_id == event.event_id
    assert restored.event_type == "tx_received"
    assert restored.source == "rpc"
    assert restored.payload == {"amount": 1.25}
    assert restored.severity == EventSeverity.WARNING
    assert restored.tags == ("alert", "funds")


def test_action_roundtrip() -> None:
    action = ActionRequest.create(
        action_type="send_transaction",
        payload={"amount": 2.0, "to": "DGB123"},
        requires_confirmation=True,
    )
    action.status = ActionStatus.APPROVED
    data = action_request_to_dict(action)
    restored = action_request_from_dict(data)
    assert restored.action_id == action.action_id
    assert restored.action_type == "send_transaction"
    assert restored.payload == {"amount": 2.0, "to": "DGB123"}
    assert restored.requires_confirmation is True
    assert restored.status == ActionStatus.APPROVED

    result = ActionResult(
        action_id=action.action_id,
        action_type=action.action_type,
        completed_at=datetime.now(timezone.utc),
        status=ActionStatus.SUCCEEDED,
        details={"txid": "abc"},
    )
    result_data = action_result_to_dict(result)
    restored_result = action_result_from_dict(result_data)
    assert restored_result.action_id == result.action_id
    assert restored_result.status == ActionStatus.SUCCEEDED
    assert restored_result.details == {"txid": "abc"}


def test_state_store_persists_state(tmp_path) -> None:
    persist_path = tmp_path / "agent_state.json"
    store = AgentStateStore(max_events=2, persist_path=persist_path)
    event_one = AgentEvent.create(event_type="incoming", source="rpc")
    event_two = AgentEvent.create(event_type="incoming", source="rpc")
    event_three = AgentEvent.create(event_type="incoming", source="rpc")
    store.record_event(event_one)
    store.record_event(event_two)
    store.record_event(event_three)

    assert len(store.get_recent_events(10)) == 2
    store.mark_event_processed(event_two.event_id)
    store.set_preference("alert_threshold", 10)

    action = ActionRequest.create(action_type="notify", requires_confirmation=False)
    store.add_pending_action(action)
    store.resolve_action(
        action.action_id,
        ActionStatus.SUCCEEDED,
        details={"message_id": "note-1"},
    )
    store.save()

    reloaded = AgentStateStore(max_events=2, persist_path=persist_path)
    assert reloaded.is_event_processed(event_two.event_id) is True
    assert reloaded.get_preferences()["alert_threshold"] == 10
    assert reloaded.list_pending_actions() == []
    history = reloaded.get_action_history(1)
    assert history[0].action_id == action.action_id
    assert history[0].details["message_id"] == "note-1"


def test_event_processor_and_rules() -> None:
    state = AgentStateStore()
    engine = RuleEngine([HighValueAlertRule(default_threshold=5.0)], debounce_seconds=60)
    processor = EventProcessor(state, engine)
    event = AgentEvent.create(
        event_type="transaction",
        source="rpc",
        payload={"amount": 10.0},
    )
    actions = processor.process(event)
    assert len(actions) == 1
    assert actions[0].action_type == "notify"
    assert state.list_pending_actions()[0].action_id == actions[0].action_id

    duplicate = processor.process(event)
    assert duplicate == []


def test_rule_engine_debounce() -> None:
    state = AgentStateStore()
    engine = RuleEngine([HighValueAlertRule(default_threshold=1.0)], debounce_seconds=60)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    first = AgentEvent.create(
        event_type="transaction",
        source="rpc",
        payload={"amount": 2.0},
        occurred_at=base,
    )
    second = AgentEvent.create(
        event_type="transaction",
        source="rpc",
        payload={"amount": 3.0},
        occurred_at=base,
    )
    assert engine.evaluate(first, state)
    assert engine.evaluate(second, state) == []


def test_queue_event_source() -> None:
    event = AgentEvent.create(event_type="transaction", source="rpc")
    source = QueueEventSource([event])
    assert source.poll() == [event]
    assert source.poll() == []
