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
    auto: first OpenAI-compatible provider with API key set (registry order:
    openai, moonshot, groq, together, zai, qwen). Falls back to Claude only
    if no OpenAI-compat key is configured.
    """
    import os

    choice = (override or "auto").lower()

    if choice in _ALIASES:
        from agent.brain.openai_brain import build_brain

        return build_brain(_ALIASES[choice])

    if choice == "claude":
        from agent.brain.claude import ClaudeBrain

        return ClaudeBrain(dry_run=dry_run)

    # auto: first configured OpenAI-compat provider, else Claude fallback
    from agent.brain.openai_brain import PROVIDERS, build_brain

    for key, cfg in PROVIDERS.items():
        if os.environ.get(cfg.key_env, "").strip():
            return build_brain(key)

    from agent.brain.claude import ClaudeBrain

    return ClaudeBrain(dry_run=dry_run)
