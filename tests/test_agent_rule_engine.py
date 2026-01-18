from dataclasses import dataclass

from enigmatic_dgb.agent.actions import ActionRequest
from enigmatic_dgb.agent.events import AgentEvent
from enigmatic_dgb.agent.rules import RuleEngine
from enigmatic_dgb.agent.state import AgentStateStore


@dataclass
class ExplodingRule:
    rule_id: str = "explode"

    def evaluate(self, event, state):
        raise RuntimeError("boom")

    def debounce_key(self, event):
        return "explode"


@dataclass
class SimpleRule:
    rule_id: str = "simple"

    def evaluate(self, event, state):
        return [ActionRequest.create(action_type="notify")]

    def debounce_key(self, event):
        return "simple"


def test_rule_engine_skips_failures() -> None:
    state = AgentStateStore()
    errors = []
    engine = RuleEngine(
        [ExplodingRule(), SimpleRule()],
        on_rule_error=lambda rule, exc: errors.append((rule.rule_id, str(exc))),
    )
    actions = engine.evaluate(
        AgentEvent.create(event_type="transaction", source="demo"),
        state,
    )
    assert len(actions) == 1
    assert actions[0].action_type == "notify"
    assert errors[0][0] == "explode"
    assert engine.metrics.rules_failed == 1
    assert engine.metrics.actions_generated == 1
