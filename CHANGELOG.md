# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-15

### Added

- **LICENSE** — Apache-2.0 license file.
- **SECURITY.md** — vulnerability disclosure policy, scope, and safety disclaimers.
- **CONTRIBUTING.md** — development setup, branch naming, commit style, test and lint instructions.
- **CODE_OF_CONDUCT.md** — Contributor Covenant 2.1.
- **GitHub Actions CI** (`.github/workflows/ci.yml`) — test (pytest -m "not slow"), lint (ruff), and build jobs on push/PR to `main`.
- **GitHub Actions release** (`.github/workflows/release.yml`) — builds wheel and creates GitHub Release on tag push.
- **GitHub issue/PR templates** — bug report, feature request, and PR checklist.
- **AUR packaging** (`packaging/aur/PKGBUILD`) — Arch Linux package with system dependency declarations.
- **systemd unit template** (`packaging/systemd/hyprland-agent.service`) — portable user service file for AUR and manual installs.
- **`docs/privacy.md`** — per-provider data handling, local storage inventory, and screenshot handling policy.
- **`pyproject.toml` metadata** — `readme`, `license`, `authors`, `keywords`, `classifiers`, `[project.urls]`.
- **`[tool.ruff]` and `[tool.mypy]`** configuration in `pyproject.toml`.
- **README quickstart** — 4-step install block and requirements box at the top; AUR install path; CI/license/release badges.

### Changed

- `src/agent/cli.py` monolith split into `src/agent/cli/` package (no user-visible change; entry points unchanged).
- `pyproject.toml` version bumped to `1.0.0`.
- Upper bounds added on volatile SDK dependencies: `anthropic<1.0`, `openai<3.0`, `sqlite-vec<0.2`.
- README "Breaking changes (v1 → v2)" section renamed to "CLI rename history" to avoid confusion with package version.
- README Development section updated to reference `src/agent/cli/` package instead of deleted `cli.py`.

### Fixed

- `orchestrator.py` — `except Exception: pass` on pre/post hash capture replaced with `log.debug(...)`.
- `memory/episodic.py` — `except Exception: pass` on analytics fetch replaced with `log.debug(...)`.

## [0.3.0] - 2026-05-15

### Added

- **Integrations framework** — entry-points group `hyprland_agent.integrations`; `Integration` Protocol, `CapabilitySpec` dataclass, and `IntegrationRegistry` with API schema versioning 1.0. Third-party integrations can be installed as separate packages and discovered automatically.
- **Built-in integrations**: `mako` (desktop notifications via `notify-send`), `waybar` (status indicator JSON), `fuzzel` (quick-launcher via fuzzel dmenu), `idle` (lock/unlock detection via D-Bus `org.freedesktop.ScreenSaver`).
- **`ActionKind.notify`** — daemon action kind for desktop notifications dispatched through active notification integrations.
- **`ActionKind.update_status`** — daemon action kind for status bar integrations.
- **Console script `agent-waybar`** — streams NDJSON events from the daemon as Waybar-compatible JSON to stdout; reconnects with exponential backoff.
- **Console script `fuzzel-agent`** — lists recent runs via RPC, pipes titles to `fuzzel --dmenu`, and re-runs the selected task.
- **`IntegrationsConfig`** in `config.yaml` — `integrations.enabled` list controls which integrations are loaded; `integrations.binary_overrides` allows overriding binary paths; `integrations.mako_app_name` controls the `--app-name` passed to `notify-send`.
- **`is_binary_allowed(name)`** in `safety/allowlist.py` — default binary allowlist for integration subprocess calls; extends the deny-by-default allowlist model to integration scripts.
- **`WorldSnapshot.integrations`** — integration status dict injected into every LLM `BrainContext` call so the model knows which desktop integrations are available.
- **`tools/_proc.py`** — unified async subprocess wrapper (`ProcResult`, `safe_env()`, `run()`) with configurable timeout, stdout capture, and env whitelisting. Shared by all integrations.

### Changed

- `tools/input.py`, `tools/screen.py`, `tools/clipboard.py` migrated to `_proc.run` wrapper for consistent timeout handling.
- `scripts/install-local.sh` — fully modular: Python version detected from `pyproject.toml` `requires-python` (no more hardcoded `3.13`); systemd block optional via `--no-systemd` / `HYPRLAND_AGENT_SKIP_SYSTEMD`; console scripts discovered by glob on `$venv/bin/`; new env vars `HYPRLAND_AGENT_BIN_DIR`, `HYPRLAND_AGENT_PYTHON`, `HYPRLAND_AGENT_SKIP_SYSTEMD`, `HYPRLAND_AGENT_WHEEL`; equivalent CLI flags for all options.
- `scripts/verify-local-install.sh` — checks all console scripts (agent, agent-waybar, fuzzel-agent); systemd checks skipped if unit file is absent.
- `CLAUDE.md` — documents integrations framework, `IntegrationRegistry` lifecycle, and new console scripts.

### Dependencies

- Added `jeepney>=0.8` (pure-Python D-Bus; used only by the `idle` integration, lazy-imported).

## [0.2.0] - 2026-04-01

### Added

- Self-learning pipeline (P2–P4): episodic memory with BAAI/bge-m3 embeddings, `ReflectionEngine`, `SkillLibrary`, `RuleMiner`, `AllowlistMiner`, and learning inbox TUI (Ctrl+I).
- Loop detection (`LoopDetector`) and post-action visual verification (`PostActionVerifier`).
- SQLite schema v4 with `sqlite-vec` for semantic similarity search.
- `brain/context.py` — unified `BrainContext` injection for episodic recall, negative reflections, and skill suggestions.

## [0.1.0] - 2026-03-01

### Added

- Initial release: daemon, CLI, TUI, orchestrator, Hyprland IPC tools, screen capture, multi-provider LLM router, allowlist, killswitch, watch rules, SQLite run storage.
