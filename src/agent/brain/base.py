"""Brain protocol — any brain implementation must satisfy this interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.schemas import Action, ScreenState


@runtime_checkable
class Brain(Protocol):
    async def decide(self, state: ScreenState, task: str) -> list[Action]:
        """Given the current screen state and a task description, return actions to execute."""
        ...
