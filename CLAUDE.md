# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Local-first agentic desktop controller for Hyprland/Wayland. A long-running daemon takes natural-language tasks, screenshots the desktop, asks an LLM "brain" for actions, and executes them via `wtype` (keyboard), `ydotool` (mouse), and Hyprland IPC. Safety is allowlist + killswitch + dry-run.

Read `README.md` for prerequisites, setup, and user-facing docs. This file covers what's not obvious from the code.

## Commands

```bash
uv sync                      # install deps (Python >= 3.13, managed via uv)
uv run pytest                # full test suite (180 tests)
uv run pytest tests/test_orchestrator.py::test_name   # single test
uv run agent daemon -v       # run daemon in foreground
uv run agent doctor          # health check (binaries, sockets, credentials)
uv run agent dry-run "<task>"  # plan actions without executing — use after any brain change
scripts/install-local.sh       # install host runtime outside this checkout
scripts/verify-local-install.sh # confirm systemd does not run from repo .venv
```

No Makefile, no ruff config in `pyproject.toml` despite `.ruff_cache/` being present. `pytest-asyncio` is in auto mode (`pyproject.toml:37`).

Entry point: `agent = "agent.cli:app"` (typer).

## Architecture

Daemon-centric. The CLI and TUI are thin RPC clients over a Unix socket; all state and execution live in the daemon.

```
agent run "<task>"
    └─ src/agent/cli.py            (typer command, RPC client)
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

**Module map:**
- `src/agent/ipc/` — shared NDJSON wire protocol (Pydantic discriminated union, 1 MiB frame cap)
- `src/agent/daemon/` — server, run_executor, watcher_service, pubsub, SQLite RunStore, rule_runner
- `src/agent/client/` — async RPC client
- `src/agent/brain/` — LLM providers + router + Claude Code OAuth bridge
- `src/agent/tools/` — Hyprland IPC (native socket, not `hyprctl` subprocess), screen capture, input, clipboard, events
- `src/agent/safety/` — allowlist, confirmation gate, killswitch
- `src/agent/tui/` — Textual monitoring TUI
- `src/agent/schemas.py` — all Pydantic models (Action, ScreenState, RunSummary, …)

## Multi-provider design

`brain/router.py` resolves `--brain <name>` (or RPC param) to an implementation. Six OpenAI-compatible providers (openai, moonshot, groq, together, zai, qwen) share a single `OpenAICompatibleBrain` class differing only in `base_url` and env-var names — see the `PROVIDERS` registry in `brain/openai_brain.py`. Claude uses its own `ClaudeBrain` with the native `computer_20251124` tool plus custom `list_windows`, `focus_window`, `dispatch_hypr` tools.

**`--brain auto`** reads `~/.config/hyprland-agent/config.yaml`: `brain.auto_order` controls priority, and `brain.providers.<name>.enabled` controls whether a provider can be selected. This is the operational switch for disabling Anthropic/Claude and using OpenAI when credits or OAuth are unavailable.

Provider keys are read **only by the daemon process** and never cross the IPC socket. Clients see run IDs and events, not credentials.

## Configuration & paths

- `~/.config/hyprland-agent/` — `allowlist.yaml`, `rules.yaml`, `env`, optional `config.yaml` (`brain` provider policy and `audit_log: true` JSONL audit)
- `~/.cache/hyprland-agent/` — `runs.db` (SQLite WAL), `STOP` (killswitch flag, polled every 100ms)
- `$XDG_RUNTIME_DIR/hyprland-agent.sock` — daemon RPC socket, mode 0600
- `~/.config/systemd/user/hyprland-agent.service` — installed by `agent migrate-systemd`
- `HYPRLAND_INSTANCE_SIGNATURE` env var is **required at runtime** (used to locate Hyprland sockets in `tools/hypr.py`)
- `.env.example` is the canonical list of provider env vars

## Hyprland integration

`tools/hypr.py` talks to Hyprland over native Unix sockets (`.socket.sock` for commands, `.socket2.sock` for events), not by spawning `hyprctl`. `daemon/watcher_service.py` fans events into the `hypr_events` pubsub topic; `daemon/rule_runner.py` matches `rules.yaml` and executes `dispatch` / `log` / `notify` / `run` actions. `run` actions are `shlex.split`-parsed, run with a whitelisted env, and reject destructive first tokens (`rm`, `sudo`, `shutdown`, etc.).

Input is **not** routed through Hyprland: keyboard via `wtype`, mouse via `ydotool` (needs `input` group + `ydotool.service`).

## Gotchas

- **`max_completion_tokens`, not `max_tokens`**, for OpenAI requests (`brain/openai_brain.py`) — required by gpt-5.x. Using `max_tokens` will fail.
- **Brain loop is hard-capped at 20 iterations** (`_MAX_LOOP = 20` in both `claude.py` and `openai_brain.py`). On overflow a warning is logged and the run ends without completing — increase carefully.
- **Run hard timeout is 300s** (`_RUN_TIMEOUT` in `daemon/run_executor.py`). Long screen tasks abort with `RunStatus.errored`.
- **Screenshot is downscaled to 0.5×** before sending to the brain; the brain's coords are scaled back up before dispatch. Coordinate translation lives in **two places** — `claude.py`'s `_computer_action_to_actions` and `openai_brain.py`'s `_sc()` helper. Keep them in parity when adding new action kinds.
- **Key normalization** (`tools/input.py`): the LLM uses friendly names (`enter`, `esc`, `pageup`, `super`) which are mapped to `wtype` X11 names (`Return`, `Escape`, `Prior`). Modifiers are sent with `-M` and released in reverse order with `-m`.
- **Killswitch is edge-triggered**: the `STOP` file flag is consumed by `disarm()` after detection to avoid log spam. `agent stop` always writes the file flag, then also sends RPC if the daemon is reachable.
- **Allowlist defaults to deny-all**. Password-manager class names (`1password`, `_1password`, `keepassxc`, `gnome-keyring`) are always blocked regardless of the allowlist.
- **NDJSON frame size cap is 1 MiB** (`ipc/constants.py`). Protocol version 1.0; major-version mismatches are rejected.
- **Provider enablement is config-driven**. Explicit `--brain openai` or `--brain claude` fails if that provider is disabled in `config.yaml`; `auto` skips disabled or uncredentialed providers.

## Known test state

`uv run pytest` → 180 passed. The Textual error-screen snapshot is tracked; inspect `snapshot_report.html` before intentionally updating it after TUI rendering changes.
