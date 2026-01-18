"""Coordinator wiring policy checks, dispatching, and notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .actions import ActionRequest, ActionStatus
from .dispatcher import ActionDispatcher
from .events import AgentEvent
from .policy import PolicyDecision, PolicyEngine
from .processor import EventProcessor
from .state import AgentStateStore

NotificationHandler = Callable[[str, dict], None]


@dataclass
class AgentCoordinator:
    state: AgentStateStore
    processor: EventProcessor
    policy: PolicyEngine
    dispatcher: ActionDispatcher
    notifier: NotificationHandler | None = None

    def handle_event(self, event: AgentEvent) -> list[ActionRequest]:
        actions = self.processor.process(event)
        for action in actions:
            self._apply_policy(action)
        return actions

    def apply_action_decision(self, action_id: str, approved: bool) -> None:
        action = self.state.get_pending_action(action_id)
        if action is None:
            raise KeyError(f"Unknown action id: {action_id}")
        if approved:
            self.state.update_pending_action_status(action_id, ActionStatus.APPROVED)
            self._dispatch_and_record(action)
            return
        self.state.resolve_action(action_id, ActionStatus.REJECTED)

    def _apply_policy(self, action: ActionRequest) -> None:
        decision = self.policy.evaluate(action, self.state)
        if not decision.allowed:
            self.state.resolve_action(
                action.action_id,
                ActionStatus.REJECTED,
                error=decision.reason,
            )
            if self.notifier:
                self.notifier(
                    "action_blocked",
                    {
                        "action_id": action.action_id,
                        "action_type": action.action_type,
                        "reason": decision.reason,
                    },
                )
            return
        self.state.update_pending_action_status(action.action_id, ActionStatus.APPROVED)
        self._dispatch_and_record(action)

    def _dispatch_and_record(self, action: ActionRequest) -> None:
        result = self.dispatcher.dispatch(action)
        self.state.resolve_action(
            action.action_id,
            result.status,
            details=result.details,
            error=result.error,
        )
        if self.notifier:
            self.notifier(
                "action_result",
                {
                    "action_id": result.action_id,
                    "action_type": result.action_type,
                    "status": result.status.value,
                    "error": result.error,
                },
            )
