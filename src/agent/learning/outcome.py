"""Run outcome tracking — derives and records outcome from status or explicit feedback."""

from __future__ import annotations

from enum import Enum

from agent.schemas import RunStatus


class RunOutcome(str, Enum):
    success = "success"
    partial = "partial"
    failure = "failure"
    stuck = "stuck"
    unknown = "unknown"


class FeedbackKind(str, Enum):
    thumbs_up = "thumbs_up"
    thumbs_down = "thumbs_down"
    comment = "comment"
    retry = "retry"


def derive_from_status(status: RunStatus) -> tuple[str, float]:
    """Return (outcome, score) derived from run status. Source is 'derived'."""
    match status:
        case RunStatus.completed:
            return RunOutcome.success, 0.8
        case RunStatus.errored:
            return RunOutcome.failure, -0.8
        case RunStatus.aborted:
            return RunOutcome.partial, -0.3
        case _:
            return RunOutcome.unknown, 0.0


def feedback_to_outcome(kind: str) -> tuple[str, float]:
    """Map explicit feedback kind to (outcome, score). Source is 'explicit'."""
    match kind:
        case "thumbs_up":
            return RunOutcome.success, 1.0
        case "thumbs_down":
            return RunOutcome.failure, -1.0
        case _:
            return RunOutcome.unknown, 0.0
