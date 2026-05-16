# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-05-16

### Fixed

- **mypy clean**: resolved all 17 pre-existing type errors across `schemas.py`, `allowlist.py`, `ipc/framing.py`, `daemon/store.py`, `daemon/watcher_service.py`, `cli/config.py`, `tools/screen.py`, `awareness/meta_cognition.py`, `tui/widgets/status_bar.py`, `tui/widgets/run_modal.py`, `learning/api.py`. `Image.LANCZOS` → `Image.Resampling.LANCZOS` (modern Pillow API); removed `unused type: ignore` comments; added explicit type annotations; `DaemonConnection | None` narrowed correctly in TUI widgets via `cast(AgentApp, self.app)`.
- `tui/widgets/run_modal.py`: submitting a task when the daemon is not connected now shows a `"Daemon not connected"` notification instead of crashing with `AttributeError`.
- `daemon/store.py`: `list_allowlist_proposals(status=None)` now returns all proposals regardless of status (previously would have returned zero rows due to `WHERE status=NULL`).

## [1.1.0] - 2026-05-16

### Added

- `src/agent/brain/anthropic_client.py` — Anthropic SDK client factory. Reads `ANTHROPIC_API_KEY`; honors `ANTHROPIC_BASE_URL` to redirect to Anthropic-compatible endpoints (e.g. Z.AI GLM Coding Plan at `https://api.z.ai/api/anthropic`).
- `tests/test_anthropic_client.py` — 3 unit tests for the new client factory (missing key, default headers, base_url override).
- `pyproject.toml` `[tool.pytest.ini_options]` `testpaths = ["tests"]` — prevents pytest from collecting build artifacts under `packaging/aur/src/`.

### Changed

- Anthropic auth is now **`ANTHROPIC_API_KEY` only**. Works against the Anthropic API natively, or against any Anthropic-compatible endpoint via `ANTHROPIC_BASE_URL`.
- `diagnostics.py`: `Claude OAuth` doctor check replaced by `ANTHROPIC_API_KEY` check.
- `brain/router.py`: `_claude_credentials_available()` renamed to `_anthropic_api_key_available()`.
- Docs (README, CLAUDE.md, docs/architecture.md, docs/privacy.md, .env.example, examples/env): remove all OAuth references; document `ANTHROPIC_BASE_URL` usage.
- Test count in CLAUDE.md/README.md corrected from 338 to 399.

### Removed

- `src/agent/brain/oauth_bridge.py` — OAuth token refresh against `auth.anthropic.com` (no longer needed).
- `src/agent/daemon/credentials.py` — orphan module, no importers.
- Support for `CLAUDE_CODE_OAUTH_TOKEN` and `~/.claude/.credentials.json` as auth sources for the `claude` brain. **Migration**: export `ANTHROPIC_API_KEY` (or add it to `~/.config/hyprland-agent/env`).

### Fixed

- `agent doctor --json` crashed with `AttributeError: 'Check' object has no attribute 'ok'` (`src/agent/cli/primary.py`). Now correctly uses `c.status == Status.ok`.

## [1.0.2] - 2026-05-16

### Added

- `packaging/desktop/hyprland-agent-tui.desktop` — XDG desktop entry that launches the monitoring TUI in a new `foot` terminal window. Installed to `/usr/share/applications/` by the AUR package. `foot` listed in `optdepends`.

### Changed

- AUR PKGBUILD: add `foot` to `optdepends` (required by the `hyprland-agent-tui.desktop` launcher); `pkgver` bump resets `pkgrel` to 1.
- `AGENTS.md`: collapse duplicated Commands section to a pointer to `CLAUDE.md` (single source of truth for command reference); add link to `docs/architecture.md`.
- `AGENTS.md` / `CLAUDE.md`: correct false statement that `pyproject.toml` has no Ruff configuration — `[tool.ruff]` lives at lines 107-113.

### Fixed

- `CHANGELOG.md` `[1.0.1]` entry claimed AUR PKGBUILD bumped `pkgrel` to 3 — the v1.0.1 publish was `1.0.1-1` (pkgver reset from `1.0.0-3`).
- `.github/ISSUE_TEMPLATE/bug_report.yml` version placeholder still showed `1.0.0` — refreshed to `1.0.2`.
- `packaging/aur/README.md` documentation examples still referenced `v1.0.0` URLs and commit messages — updated to `v1.0.2`.

## [1.0.1] - 2026-05-16

### Added

- `docs/architecture.md` — user-facing architecture reference (daemon flow, module map, safety model, DB schema history, integrations system).

### Changed

- Loosen `anthropic` constraint to `>=0.50,<1.0` (was `>=0.101.0`) to allow installation alongside AUR `python-anthropic` 0.97. Code verified compatible.
- Loosen `openai` constraint to `>=2.0,<3.0` (was `>=2.36.0`) to allow installation alongside Arch `python-openai` 2.29. Code verified compatible.
- AUR PKGBUILD: declare `python-rich` explicitly in `depends`; publish as `1.0.1-1` (pkgver reset).
- README: deduplicate embedder size warning, add AUR badge, document `agent --version` and `agent service uninstall` in Usage, link to new `docs/architecture.md`.

### Fixed

- `CONTRIBUTING.md` referenced `bge-m3` embedder (old model name) — corrected to `intfloat/multilingual-e5-large`.
- `AGENTS.md` listed obsolete `agent daemon -v` command — corrected to `agent service start -v`.
- `AGENTS.md` showed stale test count `180 passed` — corrected to `338 passed`.
- `CLAUDE.md` listed non-existent `learning explain` subcommand — corrected to `learning show`.

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

### Hardening (pre-publish audit)

**Added**
- `--version` flag on `agent` CLI (`agent --version` prints `hyprland-agent 1.0.0`).
- `agent service uninstall` command — removes config, cache, and systemd unit with `--yes` confirmation.
- `examples/` directory — annotated templates for `allowlist.yaml`, `rules.yaml`, `config.yaml`, `env`.
- `docs/troubleshooting.md` — FAQ covering daemon startup, ydotool permissions, embedder download, killswitch, and provider key issues.
- `.pre-commit-config.yaml` — local ruff + ruff-format + pre-commit-hooks gates.
- `.github/dependabot.yml` — weekly pip updates (grouped LLM SDKs) + monthly Actions updates.
- `.github/workflows/codeql.yml` — CodeQL static analysis for Python.
- `pytest-cov` and `pip-audit` added to dev dependencies; coverage gate at 60% and security audit in CI.
- Smoke tests for CLI entry-point (`tests/cli/test_help.py`).
- `KNOWN_PROVIDERS`, `BRAIN_ALIASES`, `DEFAULT_MAX_ITER`, `DEFAULT_RUN_TIMEOUT` constants centralised in `config.py` (SSOT).
- `_LATEST_SCHEMA_VERSION = 4` constant in `daemon/store.py`.

**Changed**
- `brain/router.py` imports `BRAIN_ALIASES` and `KNOWN_PROVIDERS` from `config.py` instead of duplicating them.
- `brain/claude.py` and `brain/openai_brain.py` consume `DEFAULT_MAX_ITER` from `config.py`.
- `daemon/run_executor.py` consumes `DEFAULT_RUN_TIMEOUT` from `config.py`.
- `tui/widgets/run_modal.py` fallback provider list uses `KNOWN_PROVIDERS` from `config.py`.
- `scripts/install-local.sh` copies `.env.example` to `~/.config/hyprland-agent/env` on first install.
- README: embedder download warning added to Prerequisites and Quickstart; ydotool udev rule added.
- `docs/privacy.md` and `CLAUDE.md` updated to reflect actual embedder model (`intfloat/multilingual-e5-large`, ~1.3 GB).
- `CONTRIBUTING.md` references updated model size; pre-commit setup instructions added.
- `pyproject.toml`: classifier updated to `Environment :: Console`; `Topic :: System :: Shells` added; `sdist` exclude list extended.
- CI workflows: `astral-sh/setup-uv@v3` → `@v5`; coverage + security audit jobs added.

**Fixed**
- `safety/allowlist.py` default config writes deny-all `allow: []` instead of permissive example entries.
- `tui/app.py` silent `except Exception: pass` blocks replaced with `log.debug(...)`.
- `memory/ingest_consumer.py` and `learning/consumer.py` no longer swallow `asyncio.CancelledError` (now re-raised for correct asyncio task lifecycle).
- `asyncio.create_task` calls tracked in `_bg_tasks` sets with `add_done_callback` in `LearningConsumer`, `EpisodicIngestor`, `StatusBar`, `RunDetail`.
- `ipc/constants.py` fallback uses `/run/user/{uid}` instead of `/tmp`.
- Ruff violations: all 177 original errors resolved; `B904` (`raise ... from exc`) applied throughout.
- `packaging/aur/PKGBUILD` sha256 TODO comment added.

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
