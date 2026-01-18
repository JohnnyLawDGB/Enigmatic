import time

from enigmatic_dgb.agent.actions import ActionRequest, ActionResult, ActionStatus
from enigmatic_dgb.agent.dispatcher import ActionDispatcher, RetryPolicy


def test_dispatcher_retries_on_exception() -> None:
    calls = {"count": 0}

    def handler(action: ActionRequest) -> ActionResult:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ValueError("boom")
        return ActionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            completed_at=action.created_at,
            status=ActionStatus.SUCCEEDED,
            details={"ok": True},
        )

    dispatcher = ActionDispatcher(
        {"notify": handler},
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )
    action = ActionRequest.create(action_type="notify")
    result = dispatcher.dispatch(action)
    assert calls["count"] == 2
    assert result.status == ActionStatus.SUCCEEDED
    assert result.details["attempts"] == 2


def test_dispatcher_retries_on_failed_status() -> None:
    calls = {"count": 0}

    def handler(action: ActionRequest) -> ActionResult:
        calls["count"] += 1
        status = ActionStatus.FAILED if calls["count"] == 1 else ActionStatus.SUCCEEDED
        return ActionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            completed_at=action.created_at,
            status=status,
            details={},
            error="failed" if status == ActionStatus.FAILED else None,
        )

    dispatcher = ActionDispatcher(
        {"notify": handler},
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )
    action = ActionRequest.create(action_type="notify")
    result = dispatcher.dispatch(action)
    assert calls["count"] == 2
    assert result.status == ActionStatus.SUCCEEDED
    assert result.details["attempts"] == 2


def test_dispatcher_timeout() -> None:
    def handler(action: ActionRequest) -> ActionResult:
        time.sleep(0.05)
        return ActionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            completed_at=action.created_at,
            status=ActionStatus.SUCCEEDED,
        )

    dispatcher = ActionDispatcher(
        {"notify": handler},
        retry_policy=RetryPolicy(max_attempts=1),
        timeout_seconds=0.01,
    )
    action = ActionRequest.create(action_type="notify")
    result = dispatcher.dispatch(action)
    assert result.status == ActionStatus.FAILED
    assert "timed out" in (result.error or "").lower()
