# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.13 `uv` project for a local-first Hyprland/Wayland desktop agent. Runtime code lives in `src/agent/`. Key modules are `daemon/` for the long-running server, `client/` for RPC clients, `ipc/` for NDJSON protocol framing, `brain/` for model providers, `tools/` for Hyprland/screen/input integrations, `safety/` for allowlist and kill switch logic, and `tui/` for the Textual UI. Tests live in `tests/`, with Textual snapshots under `tests/__snapshots__/`. User-facing setup and operational behavior are documented in `README.md`; Claude-specific implementation notes are in `CLAUDE.md`.

The architecture is daemon-centric: CLI and TUI clients talk to the daemon over NDJSON on `$XDG_RUNTIME_DIR/hyprland-agent.sock` with mode `0600`, while state, run execution, pubsub, and tool dispatch remain daemon-owned. Shared Pydantic schemas live in `src/agent/schemas.py`; keep IPC contracts in `src/agent/ipc/`, including the protocol version and 1 MiB frame limit.

## Build, Test, and Development Commands

- `uv sync`: install project and development dependencies from `pyproject.toml` and `uv.lock`.
- `uv run pytest`: run the full test suite.
- `uv run pytest tests/test_input.py`: run one test module while iterating.
- `uv run agent doctor`: check local prerequisites, sockets, credentials, and configuration.
- `uv run agent service start -v`: run the daemon in the foreground for local debugging.
- `uv run agent plan "<task>"`: plan actions without executing desktop actions.
- `scripts/install-local.sh`: build and install the host runtime outside the source checkout.
- `scripts/verify-local-install.sh`: verify the user service is not importing from the repo venv.

There is no Makefile and no Ruff configuration in `pyproject.toml`. The Typer entry point is `agent = "agent.cli:app"`.

## Coding Style & Naming Conventions

Use clear, typed Python with 4-space indentation. Keep Pydantic schemas in `src/agent/schemas.py` and shared IPC contracts in `src/agent/ipc/`. Prefer small modules with explicit async boundaries for daemon/client code. Test files use `test_<feature>.py`; test functions should name the behavior under test, for example `test_killswitch_disarms_after_detection`.

Keep provider routing in `src/agent/brain/router.py`. OpenAI-compatible providers share `OpenAICompatibleBrain` and the `PROVIDERS` registry in `src/agent/brain/openai_brain.py`; Claude uses its own `ClaudeBrain`. Provider keys are read only by the daemon process and must not cross IPC. `.env.example` is the canonical list of provider environment variables. Provider enablement belongs in `~/.config/hyprland-agent/config.yaml`: `brain.auto_order` controls `--brain auto`, and `brain.providers.<name>.enabled` can disable Anthropic/Claude or any OpenAI-compatible provider.

For OpenAI requests, use `max_completion_tokens`, not `max_tokens`. Keep the brain loop cap at 20 iterations unless you deliberately update both Claude and OpenAI-compatible implementations. The run executor has a 300s hard timeout. Screenshots are downscaled before brain calls, so coordinate scaling must stay equivalent in Claude and OpenAI action translation paths.

Hyprland command/event integration uses native Hyprland Unix sockets, not `hyprctl` subprocess calls. `HYPRLAND_INSTANCE_SIGNATURE` is required at runtime. Keyboard input is sent with `wtype`; mouse input uses `ydotool`, which requires the user service and `input` group setup.

## Testing Guidelines

The project uses `pytest`, `pytest-asyncio` in auto mode, and `pytest-textual-snapshot` for TUI snapshots. Add focused tests beside related coverage in `tests/` when changing safety gates, IPC contracts, provider routing, or Hyprland action translation. For TUI changes, update snapshots intentionally and inspect `snapshot_report.html` when a snapshot fails.

The documented current full-suite state is `338 passed`. If `tests/test_tui.py::test_tui_error_screen_snapshot` fails after a TUI change, inspect `snapshot_report.html` and update the snapshot intentionally.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit prefixes such as `feat:` and `fix:`. Keep commits scoped and descriptive, for example `fix: normalize key aliases for wtype`. Pull requests should describe the behavioral change, list verification commands, mention any security/safety impact, and include screenshots or snapshot notes for TUI changes.

## Security & Configuration Notes

Treat screenshots, provider keys, and desktop sockets as sensitive. Do not send credentials over IPC or broaden the allowlist casually. Before real desktop runs, verify `agent doctor`, bind the kill switch, and use `agent plan` after provider or action-loop changes.

Configuration lives under `~/.config/hyprland-agent/` (`allowlist.yaml`, `rules.yaml`, `env`, optional `config.yaml`). Use `config.yaml` for provider enablement and audit settings; use `env` for provider credentials and model overrides loaded by the daemon. Runtime state lives under `~/.cache/hyprland-agent/`, including `runs.db` and the `STOP` kill-switch flag. The kill switch is edge-triggered: detection consumes the flag to avoid repeated logs, and `agent stop` writes the file flag before attempting daemon RPC.

The allowlist is deny-by-default when empty. Password-manager windows such as `1password`, `_1password`, `keepassxc`, and `gnome-keyring` are always blocked regardless of allowlist entries. Rule `run` actions must stay `shlex.split` parsed, constrained to the whitelisted environment, and protected by the destructive first-token deny list.

The orchestrator refuses `type_text`, `key`, and `clipboard_paste` when the focused window hosts a control terminal (codex/claude/agent) to avoid agent feedback loops. Use the `terminal_command` action for foreground shell work; `hold_s` is clamped to 30 s.
