"""Conversational intent parsing and command handling."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List

from .actions import ActionStatus
from .events import AgentEvent
from .state import AgentStateStore


@dataclass(frozen=True)
class ParsedIntent:
    intent: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)
    needs_clarification: bool = False
    clarification: str | None = None
    matched: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChatResponse:
    message: str
    follow_up: str | None = None


def parse_user_message(message: str) -> ParsedIntent:
    text = message.strip()
    if not text:
        return ParsedIntent(
            intent="clarify",
            confidence=0.0,
            needs_clarification=True,
            clarification="I didn't catch that. Try 'help' to see what I can do.",
        )

    lowered = text.lower()
    candidates: List[ParsedIntent] = []

    if "help" in lowered or "commands" in lowered:
        candidates.append(ParsedIntent("help", 0.95, matched=("help",)))

    threshold_match = re.search(
        r"(?:set|update|change)\s+(?:alert\s+)?threshold(?:\s+to)?\s+([0-9]+(?:\.[0-9]+)?)",
        lowered,
    )
    if threshold_match:
        candidates.append(
            ParsedIntent(
                "set_alert_threshold",
                0.9,
                payload={"value": float(threshold_match.group(1))},
                matched=("set_alert_threshold",),
            )
        )
    elif "threshold" in lowered and any(
        word in lowered for word in ("set", "update", "change")
    ):
        candidates.append(
            ParsedIntent(
                "set_alert_threshold",
                0.4,
                needs_clarification=True,
                clarification="Tell me the numeric threshold, e.g. 'set alert threshold to 10'.",
                matched=("set_alert_threshold",),
            )
        )

    if any(
        phrase in lowered for phrase in ("recent events", "latest activity", "status")
    ):
        count_match = re.search(r"(?:last|recent)\s+(\d+)", lowered)
        limit = int(count_match.group(1)) if count_match else 5
        candidates.append(
            ParsedIntent(
                "show_recent_events",
                0.6,
                payload={"limit": limit},
                matched=("show_recent_events",),
            )
        )

    if "pending actions" in lowered or "needs approval" in lowered:
        candidates.append(ParsedIntent("list_pending_actions", 0.7))

    if "preferences" in lowered:
        candidates.append(ParsedIntent("show_preferences", 0.6))

    if "action history" in lowered or "recent actions" in lowered:
        candidates.append(ParsedIntent("show_action_history", 0.6))

    approve_match = re.search(r"\bapprove(?:\s+action)?\s+([0-9a-f]+)\b", lowered)
    if approve_match:
        candidates.append(
            ParsedIntent(
                "approve_action",
                0.9,
                payload={"action_id": approve_match.group(1)},
                matched=("approve_action",),
            )
        )

    reject_match = re.search(r"\breject(?:\s+action)?\s+([0-9a-f]+)\b", lowered)
    if reject_match:
        candidates.append(
            ParsedIntent(
                "reject_action",
                0.9,
                payload={"action_id": reject_match.group(1)},
                matched=("reject_action",),
            )
        )

    if not candidates:
        return ParsedIntent(
            intent="unknown",
            confidence=0.0,
            needs_clarification=True,
            clarification="I can help with alerts, events, and pending actions. Try 'help'.",
        )

    if len(candidates) > 1:
        intents = ", ".join(sorted({intent.intent for intent in candidates}))
        return ParsedIntent(
            intent="clarify",
            confidence=0.2,
            needs_clarification=True,
            clarification=f"I heard multiple requests ({intents}). Which one should I run?",
        )

    return candidates[0]


class ChatHandler:
    def __init__(self, state: AgentStateStore) -> None:
        self.state = state

    def handle(self, message: str) -> ChatResponse:
        intent = parse_user_message(message)
        if intent.needs_clarification:
            return ChatResponse(intent.clarification or self._help_text())

        if intent.intent == "help":
            return ChatResponse(self._help_text())
        if intent.intent == "set_alert_threshold":
            value = intent.payload.get("value")
            if value is None:
                return ChatResponse(
                    "Tell me the numeric threshold, e.g. 'set alert threshold to 10'."
                )
            self.state.set_preference("alert_threshold", value)
            return ChatResponse(
                f"Alert threshold updated to {value}.", follow_up="I'll apply this to future events."
            )
        if intent.intent == "show_recent_events":
            limit = int(intent.payload.get("limit", 5))
            return ChatResponse(self._summarize_events(limit))
        if intent.intent == "list_pending_actions":
            return ChatResponse(self._summarize_pending_actions())
        if intent.intent == "show_preferences":
            return ChatResponse(self._summarize_preferences())
        if intent.intent == "show_action_history":
            return ChatResponse(self._summarize_action_history())
        if intent.intent == "approve_action":
            action_id = intent.payload.get("action_id")
            return self._approve_action(action_id)
        if intent.intent == "reject_action":
            action_id = intent.payload.get("action_id")
            return self._reject_action(action_id)

        return ChatResponse("I couldn't parse that. Try 'help'.")

    def _help_text(self) -> str:
        return "\n".join(
            [
                "Available commands:",
                "- help",
                "- status / recent events",
                "- set alert threshold to <number>",
                "- pending actions",
                "- approve <action_id> | reject <action_id>",
                "- preferences",
                "- action history",
            ]
        )

    def _summarize_events(self, limit: int) -> str:
        events = self.state.get_recent_events(limit)
        if not events:
            return "No events recorded yet."
        lines = ["Recent events:"]
        for event in events:
            lines.append(self._format_event(event))
        return "\n".join(lines)

    def _format_event(self, event: AgentEvent) -> str:
        amount = event.payload.get("amount")
        amount_text = f" amount={amount}" if amount is not None else ""
        return (
            f"- {event.occurred_at.isoformat()} "
            f"{event.event_type} source={event.source}{amount_text}"
        )

    def _summarize_pending_actions(self) -> str:
        actions = self.state.list_pending_actions()
        if not actions:
            return "No pending actions."
        lines = ["Pending actions:"]
        for action in actions:
            lines.append(
                f"- {action.action_id} {action.action_type} status={action.status.value}"
            )
        lines.append("Reply with 'approve <id>' or 'reject <id>'.")
        return "\n".join(lines)

    def _summarize_preferences(self) -> str:
        prefs = self.state.get_preferences()
        if not prefs:
            return "No preferences set."
        lines = ["Preferences:"]
        for key in sorted(prefs.keys()):
            lines.append(f"- {key}: {prefs[key]}")
        return "\n".join(lines)

    def _summarize_action_history(self, limit: int = 10) -> str:
        history = self.state.get_action_history(limit)
        if not history:
            return "No action history yet."
        lines = ["Recent action history:"]
        for entry in history:
            lines.append(
                f"- {entry.completed_at.isoformat()} {entry.action_type} "
                f"{entry.status.value}"
            )
        return "\n".join(lines)

    def _approve_action(self, action_id: str | None) -> ChatResponse:
        if not action_id:
            return ChatResponse("Provide the action id to approve.")
        try:
            action = self.state.update_pending_action_status(
                action_id, ActionStatus.APPROVED
            )
        except KeyError:
            return ChatResponse(f"Unknown action id: {action_id}")
        return ChatResponse(f"Action {action.action_id} approved.")

    def _reject_action(self, action_id: str | None) -> ChatResponse:
        if not action_id:
            return ChatResponse("Provide the action id to reject.")
        try:
            self.state.resolve_action(action_id, ActionStatus.REJECTED)
        except KeyError:
            return ChatResponse(f"Unknown action id: {action_id}")
        return ChatResponse(f"Action {action_id} rejected.")
