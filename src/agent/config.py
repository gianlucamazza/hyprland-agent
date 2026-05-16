"""Local configuration for provider selection and daemon behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent.paths import CACHE_DIR, CONFIG_DIR  # noqa: F401 — re-exported for downstream consumers

CONFIG_PATH = CONFIG_DIR / "config.yaml"

KNOWN_PROVIDERS = ("claude", "openai", "moonshot", "groq", "together", "zai", "qwen")
DEFAULT_AUTO_ORDER = KNOWN_PROVIDERS

PROVIDER_LABELS: dict[str, str] = {
    "claude": "Claude",
    "openai": "OpenAI",
    "moonshot": "Kimi",
    "groq": "Groq",
    "together": "Together",
    "zai": "Z.AI",
    "qwen": "Qwen",
}

# Public alias map: user-facing name → canonical provider key.
BRAIN_ALIASES: dict[str, str] = {
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

# Default tunables — single source of truth; imported by brain and daemon modules.
DEFAULT_MAX_ITER: int = 20  # max LLM tool-use iterations per run
DEFAULT_RUN_TIMEOUT: float = 300.0  # seconds before a run is force-aborted

# Env vars forwarded to integration/rule subprocesses — no credentials leaked.
ENV_WHITELIST: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "XDG_SESSION_TYPE",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "DBUS_SESSION_BUS_ADDRESS",
        "LANG",
        "LC_ALL",
    }
)


class ConfigError(ValueError):
    """Raised when config.yaml contains unsupported values."""


@dataclass(frozen=True)
class BrainConfig:
    default: str = "auto"
    auto_order: tuple[str, ...] = DEFAULT_AUTO_ORDER
    providers: dict[str, bool] = field(
        default_factory=lambda: {provider: True for provider in KNOWN_PROVIDERS}
    )

    def is_enabled(self, provider: str) -> bool:
        return self.providers.get(provider, False)


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool = True
    recall_k: int = 3
    embedder_model: str = "intfloat/multilingual-e5-large"
    filter_failure_in_recall: bool = True


@dataclass(frozen=True)
class DecayConfig:
    enabled: bool = True
    half_life_days: int = 90
    prune_threshold: float = 0.1
    cleanup_interval_s: int = 3600


@dataclass(frozen=True)
class LearningConfig:
    enabled: bool = True
    mining_interval_s: int = 300
    rule_mining_enabled: bool = True
    allowlist_mining_enabled: bool = True
    decay: DecayConfig = field(default_factory=DecayConfig)


@dataclass(frozen=True)
class RateLimitConfig:
    gui_actions_per_minute: int = 30
    terminal_commands_per_minute: int = 10
    other_actions_per_minute: int = 60


@dataclass(frozen=True)
class TerminalConfig:
    capture_cap_kb: int = 64  # 64KB default (up from 8KB)


@dataclass(frozen=True)
class VoiceCoreConfig:
    enabled: bool = False


@dataclass(frozen=True)
class IntegrationsConfig:
    enabled: tuple[str, ...] = ()  # empty = load all discovered
    binary_overrides: dict[str, str] = field(default_factory=dict)
    mako_app_name: str = "hyprland-agent"
    voice: VoiceCoreConfig = field(default_factory=VoiceCoreConfig)


@dataclass(frozen=True)
class ContextConfig:
    budget_tokens: int = 160_000  # 80% of typical 200K window
    keep_rounds: int = 3


@dataclass(frozen=True)
class AgentConfig:
    brain: BrainConfig = field(default_factory=BrainConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    terminal: TerminalConfig = field(default_factory=TerminalConfig)
    integrations: IntegrationsConfig = field(default_factory=IntegrationsConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    audit_log: bool = False
    path: Path = CONFIG_PATH


def _normalize_provider(name: Any) -> str:
    if not isinstance(name, str):
        raise ConfigError(f"Provider names must be strings, got {name!r}")
    provider = BRAIN_ALIASES.get(name.lower(), name.lower())
    if provider not in KNOWN_PROVIDERS:
        raise ConfigError(f"Unknown provider {name!r}")
    return provider


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    return data


def _brain_config(data: dict[str, Any]) -> BrainConfig:
    raw = data.get("brain", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("brain must be a mapping")

    default = raw.get("default", "auto")
    if not isinstance(default, str):
        raise ConfigError("brain.default must be a string")
    default = default.lower()
    if default != "auto":
        default = _normalize_provider(default)

    raw_order = raw.get("auto_order", DEFAULT_AUTO_ORDER)
    if not isinstance(raw_order, list | tuple):
        raise ConfigError("brain.auto_order must be a list")
    auto_order = tuple(dict.fromkeys(_normalize_provider(item) for item in raw_order))
    if not auto_order:
        raise ConfigError("brain.auto_order must contain at least one provider")

    enabled = {provider: True for provider in KNOWN_PROVIDERS}
    raw_providers = raw.get("providers", {}) or {}
    if not isinstance(raw_providers, dict):
        raise ConfigError("brain.providers must be a mapping")
    for name, provider_cfg in raw_providers.items():
        provider = _normalize_provider(name)
        if isinstance(provider_cfg, bool):
            enabled[provider] = provider_cfg
            continue
        if not isinstance(provider_cfg, dict):
            raise ConfigError(f"brain.providers.{name} must be a mapping or boolean")
        raw_enabled = provider_cfg.get("enabled", True)
        if not isinstance(raw_enabled, bool):
            raise ConfigError(f"brain.providers.{name}.enabled must be true or false")
        enabled[provider] = raw_enabled

    return BrainConfig(default=default, auto_order=auto_order, providers=enabled)


def _clamp_int(raw: Any, key: str, default: int, lo: int, hi: int | None = None) -> int:
    """Read *key* from *raw* (mapping), clamp to [lo, hi] and return."""
    value = int(raw.get(key, default))
    if value < lo:
        raise ConfigError(f"{key} must be >= {lo}, got {value}")
    if hi is not None and value > hi:
        raise ConfigError(f"{key} must be <= {hi}, got {value}")
    return value


def _memory_config(data: dict[str, Any]) -> MemoryConfig:
    raw = data.get("memory", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("memory must be a mapping")
    return MemoryConfig(
        enabled=bool(raw.get("enabled", True)),
        recall_k=_clamp_int(raw, "recall_k", 3, 1),
        embedder_model=str(raw.get("embedder_model", "intfloat/multilingual-e5-large")),
        filter_failure_in_recall=bool(raw.get("filter_failure_in_recall", True)),
    )


def _decay_config(raw_parent: dict[str, Any]) -> DecayConfig:
    raw = raw_parent.get("decay", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("learning.decay must be a mapping")
    prune = float(raw.get("prune_threshold", 0.1))
    if prune < 0.0 or prune > 1.0:
        raise ConfigError(f"learning.decay.prune_threshold must be 0.0..1.0, got {prune}")
    return DecayConfig(
        enabled=bool(raw.get("enabled", True)),
        half_life_days=_clamp_int(raw, "half_life_days", 90, 1),
        prune_threshold=prune,
        cleanup_interval_s=_clamp_int(raw, "cleanup_interval_s", 3600, 1),
    )


def _learning_config(data: dict[str, Any]) -> LearningConfig:
    raw = data.get("learning", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("learning must be a mapping")
    return LearningConfig(
        enabled=bool(raw.get("enabled", True)),
        mining_interval_s=_clamp_int(raw, "mining_interval_s", 300, 1),
        rule_mining_enabled=bool(raw.get("rule_mining_enabled", True)),
        allowlist_mining_enabled=bool(raw.get("allowlist_mining_enabled", True)),
        decay=_decay_config(raw),
    )


def _rate_limit_config(data: dict[str, Any]) -> RateLimitConfig:
    raw = data.get("rate_limit", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("rate_limit must be a mapping")
    return RateLimitConfig(
        gui_actions_per_minute=_clamp_int(raw, "gui_actions_per_minute", 30, 0),
        terminal_commands_per_minute=_clamp_int(raw, "terminal_commands_per_minute", 10, 0),
        other_actions_per_minute=_clamp_int(raw, "other_actions_per_minute", 60, 0),
    )


def _terminal_config(data: dict[str, Any]) -> TerminalConfig:
    raw = data.get("terminal", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("terminal must be a mapping")
    return TerminalConfig(
        capture_cap_kb=_clamp_int(raw, "capture_cap_kb", 64, 1),
    )


def _integrations_config(data: dict[str, Any]) -> IntegrationsConfig:
    raw = data.get("integrations", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("integrations must be a mapping")
    known_keys = {"enabled", "binary_overrides", "mako_app_name", "voice"}
    for key in raw:
        if key not in known_keys:
            raise ConfigError(f"integrations.{key!r} is not a recognised key")

    raw_enabled = raw.get("enabled", [])
    if not isinstance(raw_enabled, list):
        raise ConfigError("integrations.enabled must be a list of integration names")
    enabled = tuple(str(e) for e in raw_enabled)

    raw_overrides = raw.get("binary_overrides", {}) or {}
    if not isinstance(raw_overrides, dict):
        raise ConfigError("integrations.binary_overrides must be a mapping")
    binary_overrides = {str(k): str(v) for k, v in raw_overrides.items()}

    mako_app_name = str(raw.get("mako_app_name", "hyprland-agent"))
    raw_voice = raw.get("voice", {}) or {}
    if not isinstance(raw_voice, dict):
        raise ConfigError("integrations.voice must be a mapping")
    voice_enabled = bool(raw_voice.get("enabled", False))
    return IntegrationsConfig(
        enabled=enabled,
        binary_overrides=binary_overrides,
        mako_app_name=mako_app_name,
        voice=VoiceCoreConfig(enabled=voice_enabled),
    )


def _context_config(data: dict[str, Any]) -> ContextConfig:
    raw = data.get("context", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("context must be a mapping")
    return ContextConfig(
        budget_tokens=_clamp_int(raw, "budget_tokens", 160_000, 1),
        keep_rounds=_clamp_int(raw, "keep_rounds", 3, 0),
    )


def load_config(path: Path = CONFIG_PATH) -> AgentConfig:
    data = _read_mapping(path)
    audit_log = data.get("audit_log", False)
    if not isinstance(audit_log, bool):
        raise ConfigError("audit_log must be true or false")
    return AgentConfig(
        brain=_brain_config(data),
        memory=_memory_config(data),
        learning=_learning_config(data),
        rate_limit=_rate_limit_config(data),
        terminal=_terminal_config(data),
        integrations=_integrations_config(data),
        context=_context_config(data),
        audit_log=audit_log,
        path=path,
    )
