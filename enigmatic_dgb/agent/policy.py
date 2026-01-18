"""Policy evaluation for agent actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .actions import ActionRequest
from .state import AgentStateStore


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None


@dataclass
class PolicyEngine:
    high_risk_action_types: set[str] | None = None

    def __post_init__(self) -> None:
        if self.high_risk_action_types is None:
            self.high_risk_action_types = {
                "send_transaction",
                "broadcast",
                "transfer",
                "execute_trade",
            }

    def evaluate(
        self, action: ActionRequest, state: AgentStateStore
    ) -> PolicyDecision:
        if action.requires_confirmation:
            return PolicyDecision(False, "Action flagged as requiring confirmation.")

        preferences = state.get_preferences()
        require_all = bool(preferences.get("require_confirmation", False))
        if require_all:
            return PolicyDecision(False, "Global confirmation required.")

        require_for = set(preferences.get("require_confirmation_for", []))
        if action.action_type in require_for:
            return PolicyDecision(False, "Confirmation required by preference.")

        auto_for = set(preferences.get("auto_approve_for", []))
        if action.action_type in auto_for:
            return PolicyDecision(True, "Auto-approved by preference.")

        if action.action_type in (self.high_risk_action_types or set()):
            return PolicyDecision(False, "High-risk action type.")

        return PolicyDecision(True, None)
