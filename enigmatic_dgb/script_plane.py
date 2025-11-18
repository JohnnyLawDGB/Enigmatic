"""Helpers describing the optional script plane for state vectors."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable


class ScriptPlaneError(RuntimeError):
    """Raised when a script plane declaration is invalid."""


@dataclass(frozen=True)
class ScriptPlane:
    """Represents script-level telemetry for a spend or output."""

    script_type: str
    taproot_mode: str | None = None
    branch_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


def parse_script_plane_block(
    payload: Any, error_factory: Callable[[str], Exception]
) -> ScriptPlane:
    """Convert a loosely-typed mapping into a :class:`ScriptPlane`."""

    if not isinstance(payload, dict):
        raise error_factory("script_plane must be a mapping")

    script_type = payload.get("script_type")
    if not isinstance(script_type, str) or not script_type:
        raise error_factory("script_plane.script_type must be a non-empty string")

    taproot_mode = payload.get("taproot_mode")
    if taproot_mode is not None and not isinstance(taproot_mode, str):
        raise error_factory("script_plane.taproot_mode must be a string if provided")

    branch_id = payload.get("branch_id")
    if branch_id is not None:
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise error_factory("script_plane.branch_id must be an integer") from exc
        if branch_id < 0:
            raise error_factory("script_plane.branch_id must be non-negative")

    return ScriptPlane(script_type=script_type, taproot_mode=taproot_mode, branch_id=branch_id)
