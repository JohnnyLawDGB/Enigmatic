"""Minimal wiring demo for the hybrid agent stack."""

from __future__ import annotations

from enigmatic_dgb.agent import (
    ActionDispatcher,
    AgentCoordinator,
    AgentEvent,
    AgentStateStore,
    ChatHandler,
    EventMonitor,
    EventProcessor,
    HighValueAlertRule,
    PolicyEngine,
    QueueEventSource,
    RuleEngine,
    build_notify_handler,
)


def main() -> None:
    state = AgentStateStore()
    rules = RuleEngine([HighValueAlertRule(default_threshold=2.0)])
    processor = EventProcessor(state, rules)
    policy = PolicyEngine()

    def notify(message: str, payload: dict) -> None:
        print(f"[notify] {message} payload={payload}")

    dispatcher = ActionDispatcher({"notify": build_notify_handler(notify)})

    def emit(kind: str, payload: dict) -> None:
        print(f"[event] {kind}: {payload}")

    coordinator = AgentCoordinator(
        state,
        processor,
        policy,
        dispatcher,
        notifier=emit,
    )

    source = QueueEventSource()
    monitor = EventMonitor(source, processor)

    # Simulate an incoming transaction event.
    source.push(
        AgentEvent.create(
            event_type="transaction",
            source="demo",
            payload={"amount": 5.0},
        )
    )
    for event in monitor.run_once():
        coordinator.handle_event(event)

    pending = state.list_pending_actions()
    print(f"Pending actions: {[action.action_id for action in pending]}")

    chat = ChatHandler(state)
    print(chat.handle("pending actions").message)


if __name__ == "__main__":
    main()
