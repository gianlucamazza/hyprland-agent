# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Local-first agentic desktop controller for Hyprland/Wayland. A long-running daemon takes natural-language tasks, screenshots the desktop, asks an LLM "brain" for actions, and executes them via `wtype` (keyboard), `ydotool` (mouse), and Hyprland IPC. Safety is allowlist + killswitch + explicit planning before real execution.

Read `README.md` for prerequisites, setup, and user-facing docs. Read [`docs/architecture.md`](docs/architecture.md) for the full architectural breakdown of modules, providers, safety model, and DB schema. This file covers what's not obvious from the code.

## Commands

```bash
uv sync                      # install deps (Python >= 3.13, managed via uv)
uv run pytest                # full test suite
uv run pytest -m "not slow"  # fast suite (skips embedder download)
uv run pytest tests/test_orchestrator.py::test_name   # single test
uv run agent service start -v  # run daemon in foreground
uv run agent doctor          # health check (binaries, sockets, credentials)
uv run agent plan "<task>"   # plan actions without executing
uv run agent learning list skill           # list draft skills
uv run agent learning approve skill <id>   # approve a skill
scripts/install-local.sh       # install host runtime outside this checkout
scripts/verify-local-install.sh # confirm systemd does not run from repo .venv
agent-waybar                   # stream Waybar JSON (run after install)
fuzzel-agent                   # fuzzel dmenu to re-run a recent task
```

No Makefile. `pytest-asyncio` is in auto mode; Ruff config lives in `[tool.ruff]`; mypy config in `[tool.mypy]`.

Entry point: `agent = "agent.cli:app"` (typer). CLI is a package at `src/agent/cli/`.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full breakdown of modules, providers, safety model, and DB schema versioning. Quick flow:

```
agent run "<task>"
    └─ src/agent/cli/            (typer package, RPC client)
        └─ NDJSON over $XDG_RUNTIME_DIR/hyprland-agent.sock (mode 0600)
            └─ src/agent/daemon/server.py        (RPC dispatch)
                └─ daemon/run_executor.py        (queue, 300s hard timeout)
                    └─ orchestrator.py           (the task loop)
                        ├─ safety/killswitch.py  (poll between every action)
                        ├─ safety/allowlist.py   (deny-by-default; pw managers always blocked)
                        ├─ tools/screen.py       (grim → 0.5× downscale → bytes)
                        ├─ brain/router.py       (selects brain implementation)
                        │   ├─ brain/claude.py           (Anthropic computer_20251124)
                        │   └─ brain/openai_brain.py     (one impl, 6 providers via PROVIDERS registry)
                        └─ tools/{input,hypr,clipboard}.py  (execute actions)
```

Brain aliases: `kimi` is a canonical alias for `moonshot` (see `BRAIN_ALIASES` in `src/agent/config.py`). `--brain auto` resolves via `brain.auto_order` in `config.yaml`.

## Gotchas

- **`max_completion_tokens`, not `max_tokens`**, for OpenAI requests (`brain/openai_brain.py`) — required by gpt-5.x. Using `max_tokens` will fail.
- **Brain loop cap and run timeout** are defined in `src/agent/config.py` (`DEFAULT_MAX_ITER = 20`, `DEFAULT_RUN_TIMEOUT = 300`). Both brains import `MAX_LOOP` from `brain/_common.py` (which reads `DEFAULT_MAX_ITER` from config). `DEFAULT_RUN_TIMEOUT` is used by `run_executor.py` as the hard timeout. Increase `DEFAULT_MAX_ITER` carefully.
- **Screenshot is downscaled to 0.5×** before sending to the brain; the brain's coords are scaled back up before dispatch. Coordinate translation is in `brain/_action_map.py:computer_actions()` — shared by both `claude.py` and `openai_brain.py`. Add new verbs there.
- **Key normalization** (`tools/input.py`): the LLM uses friendly names (`enter`, `esc`, `pageup`, `super`) which are mapped to `wtype` X11 names (`Return`, `Escape`, `Prior`). Modifiers are sent with `-M` and released in reverse order with `-m`.
- **Terminal commands** use `terminal_command` and `tools/terminal.py`, not `type_text` + `Return` into the focused terminal. `hold_s` is only for visible debug/test runs and is capped at 30 seconds.
- **Killswitch is edge-triggered**: the `STOP` file flag is consumed by `disarm()` after detection to avoid log spam. `agent stop` always writes the file flag, then also sends RPC if the daemon is reachable.
- **Allowlist defaults to deny-all**. Password-manager class names (`1password`, `_1password`, `keepassxc`, `gnome-keyring`) are always blocked regardless of the allowlist.
- **NDJSON frame size cap is 1 MiB** (`ipc/constants.py`). Protocol version 1.0; major-version mismatches are rejected.
- **Provider enablement is config-driven**. Explicit `--brain openai` or `--brain claude` fails if that provider is disabled in `config.yaml`; `auto` skips disabled or uncredentialed providers.
- **sqlite-vec loaded per-connection**: `_run_vec_sync` calls `_load_vec0(conn)` on every invocation. `_run_sync` does NOT load vec0. Do not call vec queries through `_run_sync` or they will silently return empty results.
- **`intfloat/multilingual-e5-large` model is ~1.3 GB** and downloaded lazily on first embed call to `~/.cache/fastembed`. Mark tests that need the real embedder with `@pytest.mark.slow`; stub it with `[[0.1]*1024]` for unit tests.
- **`watcher_service.load_rules()`** merges `rules.yaml` and `learned_rules.yaml` with dedup by `(on, match)` key. Duplicate rules across both files are silently dropped.
- **Memory decay (v5 schema)** adds `decay_score` and `last_accessed_at` columns to `episodes`, `reflections`, `skills`. The `_memory_decay_loop` task in `daemon/main.py` periodically calls `store.prune_decayed(threshold=0.1, half_life_days=90)` using exponential decay. `touch_memory()` resets the score on recall — memory consumers (episodic recall, reflection queries) should call it after successful lookups.
- **RateLimiter** (`safety/rate_limit.py`) is lazy-initialized from `config.rate_limit` and tracks three action groups: GUI (30/min), terminal (10/min), other (60/min). `reconfigure()` allows live updates without a daemon restart. `sanitize_command()` blocks rm -f /, mkfs, dd to /dev/, piping to agent, and backgrounding.
- **Learning pipeline mining**: `AppState.open()` optionally instantiates `AllowlistMiner` and `RuleMiner` gated by `config.learning.{allowlist_mining_enabled,rule_mining_enabled}`. They run as periodic tasks inside `LearningConsumer` every `mining_interval_s` (default 300 s) and submit proposals to the `allowlist_proposals` / `learned_rules` tables.

## Integrations (P5)

See [`docs/architecture.md`](docs/architecture.md) for the full integration spec. Entry-points group `hyprland_agent.integrations`. Built-in: `mako`, `waybar`, `fuzzel`, `idle`, `voice`. `IntegrationRegistry` routes `ActionKind.notify` and `ActionKind.speak` to all registered integrations via `handle()`. `INTEGRATIONS_API_VERSION = "1.0"` — major-version mismatch causes the integration to be skipped.

**Desktop launcher**: `packaging/desktop/hyprland-agent-tui.desktop` ships via the AUR package (`/usr/share/applications/`). Exec: `foot --app-id=hyprland-agent-tui agent tui`. Requires `foot` (declared as `optdepend` in PKGBUILD).

**Console scripts:** `agent-waybar` → `cli/waybar_module.py:main`; `fuzzel-agent` → `cli/fuzzel_launcher.py:main`; `agent-voice` → `cli/voice_sidecar.py:main`. All three are thin async clients over the daemon socket.

## Known test state

`uv run pytest` must be green. `uv run pytest -m "not slow"` skips embedder download tests. The Textual error-screen snapshot is tracked under `tests/__snapshots__/`; inspect `snapshot_report.html` before intentionally updating it after TUI rendering changes.
