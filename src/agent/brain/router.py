"""Brain router — picks the right brain for a given task."""

from __future__ import annotations

import os
from pathlib import Path

from agent.brain.base import Brain
from agent.config import CONFIG_PATH, AgentConfig, ConfigError, load_config

_ALIASES: dict[str, str] = {
    "claude": "claude",
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


class BrainSelectionError(RuntimeError):
    """Raised when provider config cannot select a usable brain."""


def canonical_provider(name: str) -> str:
    provider = _ALIASES.get(name.lower(), name.lower())
    if provider not in {
        "claude",
        "openai",
        "moonshot",
        "groq",
        "together",
        "zai",
        "qwen",
    }:
        raise BrainSelectionError(f"Unknown brain provider: {name}")
    return provider


def _claude_credentials_available() -> bool:
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip():
        return True
    return (Path.home() / ".claude" / ".credentials.json").exists()


def _provider_available(provider: str) -> tuple[bool, str]:
    if provider == "claude":
        if _claude_credentials_available():
            return True, "available"
        return False, "Claude OAuth credentials not found"

    from agent.brain.openai_brain import PROVIDERS

    cfg = PROVIDERS[provider]
    if os.environ.get(cfg.key_env, "").strip():
        return True, f"{cfg.key_env} set"
    return False, f"{cfg.key_env} not set"


def _build_provider(provider: str, dry_run: bool) -> Brain:
    if provider == "claude":
        from agent.brain.claude import ClaudeBrain

        return ClaudeBrain(dry_run=dry_run)

    from agent.brain.openai_brain import build_brain

    return build_brain(provider)


def selectable_providers(config: AgentConfig | None = None) -> list[str]:
    cfg = config or load_config()
    return [provider for provider in cfg.brain.auto_order if cfg.brain.is_enabled(provider)]


def get_brain(override: str | None = None, dry_run: bool = False) -> Brain:
    """
    override: 'claude' | 'openai' | 'gpt' | 'kimi' | 'moonshot' | 'k2' |
              'groq' | 'together' | 'zai' | 'glm' | 'qwen' | 'dashscope' | 'auto' | None
    auto: first enabled and credentialed provider from config brain.auto_order.
    """
    try:
        config = load_config()
    except ConfigError as exc:
        raise BrainSelectionError(f"Invalid provider config {CONFIG_PATH}: {exc}") from exc

    configured_default = config.brain.default
    choice = (override or configured_default or "auto").lower()

    if choice != "auto":
        provider = canonical_provider(choice)
        if not config.brain.is_enabled(provider):
            raise BrainSelectionError(
                f"Brain provider '{provider}' is disabled in {config.path}"
            )
        available, reason = _provider_available(provider)
        if not available:
            raise BrainSelectionError(f"Brain provider '{provider}' unavailable: {reason}")
        return _build_provider(provider, dry_run=dry_run)

    checked: list[str] = []
    for provider in config.brain.auto_order:
        if not config.brain.is_enabled(provider):
            checked.append(f"{provider}: disabled")
            continue
        available, reason = _provider_available(provider)
        if available:
            return _build_provider(provider, dry_run=dry_run)
        checked.append(f"{provider}: {reason}")

    raise BrainSelectionError(
        f"No enabled brain provider is available from {config.path}: "
        + "; ".join(checked)
    )
