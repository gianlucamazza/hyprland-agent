"""Local configuration for provider selection and daemon behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path.home() / ".config" / "hyprland-agent"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
CACHE_DIR = Path.home() / ".cache" / "hyprland-agent"

KNOWN_PROVIDERS = ("claude", "openai", "moonshot", "groq", "together", "zai", "qwen")
DEFAULT_AUTO_ORDER = ("claude", "openai", "moonshot", "groq", "together", "zai", "qwen")

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
class LearningConfig:
    enabled: bool = True
    mining_interval_s: int = 300
    skill_extraction_enabled: bool = True
    rule_mining_enabled: bool = True
    allowlist_mining_enabled: bool = True


@dataclass(frozen=True)
class IntegrationsConfig:
    enabled: tuple[str, ...] = ()  # empty = load all discovered
    binary_overrides: dict[str, str] = field(default_factory=dict)
    mako_app_name: str = "hyprland-agent"


@dataclass(frozen=True)
class AgentConfig:
    brain: BrainConfig = field(default_factory=BrainConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    integrations: IntegrationsConfig = field(default_factory=IntegrationsConfig)
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


def _memory_config(data: dict[str, Any]) -> MemoryConfig:
    raw = data.get("memory", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("memory must be a mapping")
    return MemoryConfig(
        enabled=bool(raw.get("enabled", True)),
        recall_k=int(raw.get("recall_k", 3)),
        embedder_model=str(raw.get("embedder_model", "intfloat/multilingual-e5-large")),
        filter_failure_in_recall=bool(raw.get("filter_failure_in_recall", True)),
    )


def _learning_config(data: dict[str, Any]) -> LearningConfig:
    raw = data.get("learning", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("learning must be a mapping")
    return LearningConfig(
        enabled=bool(raw.get("enabled", True)),
        mining_interval_s=int(raw.get("mining_interval_s", 300)),
        skill_extraction_enabled=bool(raw.get("skill_extraction_enabled", True)),
        rule_mining_enabled=bool(raw.get("rule_mining_enabled", True)),
        allowlist_mining_enabled=bool(raw.get("allowlist_mining_enabled", True)),
    )


def _integrations_config(data: dict[str, Any]) -> IntegrationsConfig:
    raw = data.get("integrations", {}) or {}
    if not isinstance(raw, dict):
        raise ConfigError("integrations must be a mapping")
    known_keys = {"enabled", "binary_overrides", "mako_app_name"}
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
    return IntegrationsConfig(
        enabled=enabled,
        binary_overrides=binary_overrides,
        mako_app_name=mako_app_name,
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
        integrations=_integrations_config(data),
        audit_log=audit_log,
        path=path,
    )
