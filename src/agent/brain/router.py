"""Brain router — picks the right brain for a given task."""

from __future__ import annotations

from agent.brain.base import Brain

_ALIASES: dict[str, str] = {
    "openai": "openai",
    "gpt": "openai",
    "moonshot": "moonshot",
    "kimi": "moonshot",
    "k2": "moonshot",
    "groq": "groq",
    "together": "together",
    "togetherai": "together",
    "zai": "zai",
    "glm": "zai",
    "z.ai": "zai",
    "qwen": "qwen",
    "dashscope": "qwen",
}


def get_brain(override: str | None = None, dry_run: bool = False) -> Brain:
    """
    override: 'claude' | 'openai' | 'gpt' | 'kimi' | 'moonshot' | 'k2' |
              'groq' | 'together' | 'zai' | 'glm' | 'qwen' | 'dashscope' | 'auto' | None
    auto: defaults to Claude (computer-use is most capable for desktop control).
    """
    choice = (override or "auto").lower()

    if choice in _ALIASES:
        from agent.brain.openai_brain import build_brain

        return build_brain(_ALIASES[choice])

    if choice == "claude":
        from agent.brain.claude import ClaudeBrain

        return ClaudeBrain(dry_run=dry_run)

    # auto
    from agent.brain.claude import ClaudeBrain

    return ClaudeBrain(dry_run=dry_run)
