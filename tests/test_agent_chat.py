from enigmatic_dgb.agent.actions import ActionRequest
from enigmatic_dgb.agent.chat import ChatHandler, parse_user_message
from enigmatic_dgb.agent.state import AgentStateStore


def test_parse_set_threshold() -> None:
    intent = parse_user_message("set alert threshold to 10")
    assert intent.intent == "set_alert_threshold"
    assert intent.payload["value"] == 10.0


def test_parse_needs_clarification() -> None:
    intent = parse_user_message("set threshold")
    assert intent.needs_clarification is True


def test_chat_updates_threshold() -> None:
    state = AgentStateStore()
    handler = ChatHandler(state)
    response = handler.handle("set alert threshold to 2.5")
    assert "updated" in response.message.lower()
    assert state.get_preferences()["alert_threshold"] == 2.5


def test_chat_pending_actions() -> None:
    state = AgentStateStore()
    action = ActionRequest.create(action_type="notify")
    state.add_pending_action(action)
    handler = ChatHandler(state)
    response = handler.handle("pending actions")
    assert action.action_id in response.message


def test_chat_help() -> None:
    handler = ChatHandler(AgentStateStore())
    response = handler.handle("help")
    assert "available commands" in response.message.lower()
