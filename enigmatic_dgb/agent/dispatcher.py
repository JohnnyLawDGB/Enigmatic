"""Action dispatching utilities."""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from .actions import ActionRequest, ActionResult, ActionStatus

ActionHandler = Callable[[ActionRequest], ActionResult]


class HandlerTimeoutError(RuntimeError):
    """Raised when an action handler exceeds the configured timeout."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 5.0
    retry_on_exceptions: Tuple[type[BaseException], ...] = (Exception,)
    retry_on_statuses: Tuple[ActionStatus, ...] = (ActionStatus.FAILED,)


@dataclass
class ActionDispatcher:
    handlers: Dict[str, ActionHandler]
    retry_policy: RetryPolicy | None = None
    timeout_seconds: float | None = None

    def dispatch(self, action: ActionRequest) -> ActionResult:
        handler = self.handlers.get(action.action_type)
        if not handler:
            return ActionResult(
                action_id=action.action_id,
                action_type=action.action_type,
                completed_at=datetime.now(timezone.utc),
                status=ActionStatus.FAILED,
                error=f"No handler registered for action '{action.action_type}'.",
                details={"attempts": 0},
            )
        policy = self.retry_policy or RetryPolicy()
        attempts = 0
        backoff = max(0.0, policy.backoff_seconds)
        max_attempts = max(1, policy.max_attempts)
        while True:
            attempts += 1
            try:
                result = self._run_handler(handler, action)
            except BaseException as exc:  # pragma: no cover - defensive logging
                if self._should_retry_exception(exc, attempts, policy, max_attempts):
                    self._sleep_backoff(backoff)
                    backoff = self._next_backoff(backoff, policy)
                    continue
                return self._failure_result(action, str(exc), attempts)

            if not isinstance(result, ActionResult):
                return self._failure_result(
                    action,
                    "Action handler returned invalid result type.",
                    attempts,
                )
            result = self._with_attempts_result(result, attempts)
            if (
                result.status in policy.retry_on_statuses
                and attempts < max_attempts
            ):
                self._sleep_backoff(backoff)
                backoff = self._next_backoff(backoff, policy)
                continue
            return result

    def _run_handler(
        self, handler: ActionHandler, action: ActionRequest
    ) -> ActionResult:
        if not self.timeout_seconds:
            return handler(action)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(handler, action)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeout as exc:
            raise HandlerTimeoutError(
                f"Handler timed out after {self.timeout_seconds:.2f}s"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _should_retry_exception(
        self,
        exc: BaseException,
        attempts: int,
        policy: RetryPolicy,
        max_attempts: int,
    ) -> bool:
        if attempts >= max_attempts:
            return False
        return isinstance(exc, policy.retry_on_exceptions)

    @staticmethod
    def _next_backoff(current: float, policy: RetryPolicy) -> float:
        if current <= 0:
            return policy.backoff_seconds
        return min(current * policy.backoff_multiplier, policy.max_backoff_seconds)

    @staticmethod
    def _sleep_backoff(backoff: float) -> None:
        if backoff > 0:
            time.sleep(backoff)

    @staticmethod
    def _failure_result(
        action: ActionRequest, error: str, attempts: int
    ) -> ActionResult:
        return ActionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            completed_at=datetime.now(timezone.utc),
            status=ActionStatus.FAILED,
            error=error,
            details={"attempts": attempts},
        )

    @staticmethod
    def _with_attempts_result(
        result: ActionResult, attempts: int
    ) -> ActionResult:
        merged = dict(result.details or {})
        merged["attempts"] = attempts
        return ActionResult(
            action_id=result.action_id,
            action_type=result.action_type,
            completed_at=result.completed_at,
            status=result.status,
            details=merged,
            error=result.error,
        )


def build_notify_handler(
    notifier: Callable[[str, dict], None]
) -> Callable[[ActionRequest], ActionResult]:
    def _handler(action: ActionRequest) -> ActionResult:
        payload = dict(action.payload)
        message = str(payload.get("message") or "Notification")
        notifier(message, payload)
        return ActionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            completed_at=datetime.now(timezone.utc),
            status=ActionStatus.SUCCEEDED,
            details={"notified": True},
        )

    return _handler
