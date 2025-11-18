"""Helpers describing the optional script plane for state vectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class ScriptPlaneError(RuntimeError):
    """Raised when a script plane declaration is invalid."""


@dataclass(frozen=True)
class ScriptPlaneAggregation:
    """Metadata describing how witnesses were aggregated for a spend."""

    aggregation_mode: str = "none"
    signer_set_id: str | None = None
    threshold: int | None = None
    total_signers: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"aggregation_mode": self.aggregation_mode}
        if self.signer_set_id is not None:
            data["signer_set_id"] = self.signer_set_id
        if self.threshold is not None:
            data["threshold"] = self.threshold
        if self.total_signers is not None:
            data["total_signers"] = self.total_signers
        return data

    def is_default(self) -> bool:
        return self.aggregation_mode == "none" and not any(
            value is not None for value in (self.signer_set_id, self.threshold, self.total_signers)
        )


@dataclass(frozen=True)
class ScriptPlane:
    """Represents script-level telemetry for a spend or output."""

    script_type: str
    taproot_mode: str | None = None
    branch_id: int | None = None
    aggregation: ScriptPlaneAggregation = field(default_factory=ScriptPlaneAggregation)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"script_type": self.script_type}
        if self.taproot_mode is not None:
            data["taproot_mode"] = self.taproot_mode
        if self.branch_id is not None:
            data["branch_id"] = self.branch_id
        if self.aggregation:
            data["aggregation"] = self.aggregation.to_dict()
        return data


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

    aggregation_block = payload.get("aggregation")
    aggregation = _parse_aggregation_block(aggregation_block, error_factory)

    return ScriptPlane(
        script_type=script_type,
        taproot_mode=taproot_mode,
        branch_id=branch_id,
        aggregation=aggregation,
    )


def _parse_aggregation_block(
    payload: Any, error_factory: Callable[[str], Exception]
) -> ScriptPlaneAggregation:
    if payload is None:
        return ScriptPlaneAggregation()
    if not isinstance(payload, dict):
        raise error_factory("script_plane.aggregation must be a mapping if provided")

    aggregation_mode = payload.get("aggregation_mode", "none")
    if not isinstance(aggregation_mode, str) or not aggregation_mode:
        raise error_factory("script_plane.aggregation_mode must be a non-empty string")

    signer_set_id = payload.get("signer_set_id")
    if signer_set_id is not None:
        signer_set_id = str(signer_set_id)

    threshold = payload.get("threshold")
    if threshold is not None:
        try:
            threshold = int(threshold)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise error_factory("script_plane.aggregation.threshold must be an integer") from exc
        if threshold <= 0:
            raise error_factory("script_plane.aggregation.threshold must be positive")

    total_signers = payload.get("total_signers")
    if total_signers is not None:
        try:
            total_signers = int(total_signers)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise error_factory("script_plane.aggregation.total_signers must be an integer") from exc
        if total_signers <= 0:
            raise error_factory("script_plane.aggregation.total_signers must be positive")

    if threshold is not None and total_signers is not None and threshold > total_signers:
        raise error_factory("script_plane.aggregation.threshold cannot exceed total_signers")

    return ScriptPlaneAggregation(
        aggregation_mode=aggregation_mode,
        signer_set_id=signer_set_id,
        threshold=threshold,
        total_signers=total_signers,
    )
