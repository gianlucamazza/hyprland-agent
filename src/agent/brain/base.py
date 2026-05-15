"""Brain protocol — any brain implementation must satisfy this interface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agent.schemas import Action, ScreenState

if TYPE_CHECKING:
    from agent.brain.context import BrainContext


@runtime_checkable
class Brain(Protocol):
    async def decide(self, state: ScreenState, task: str, ctx: BrainContext) -> list[Action]:
        """Given screen state, task description, and brain context, return actions."""
        ...
