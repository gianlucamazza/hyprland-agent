# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Local-first agentic desktop controller for Hyprland/Wayland. A long-running daemon takes natural-language tasks, screenshots the desktop, asks an LLM "brain" for actions, and executes them via `wtype` (keyboard), `ydotool` (mouse), and Hyprland IPC. Safety is allowlist + killswitch + explicit planning before real execution.

Read `README.md` for prerequisites, setup, and user-facing docs. This file covers what's not obvious from the code.

## Commands

```bash
uv sync                      # install deps (Python >= 3.13, managed via uv)
uv run pytest                # full test suite (338 tests)
uv run pytest -m "not slow"  # fast suite (skips embedder download)
uv run pytest tests/test_orchestrator.py::test_name   # single test
uv run agent service start -v  # run daemon in foreground
uv run agent doctor          # health check (binaries, sockets, credentials)
uv run agent plan "<task>"   # plan actions without executing
uv run agent learning list skill           # list draft skills
uv run agent learning approve skill <id>   # approve a skill
scripts/install-local.sh       # install host runtime outside this checkout
scripts/verify-local-install.sh # confirm systemd does not run from repo .venv
agent-waybar --watch           # stream Waybar JSON (run after install)
fuzzel-agent                   # fuzzel dmenu to re-run a recent task
```

No Makefile. `pytest-asyncio` is in auto mode (`pyproject.toml:90`). Ruff config lives in `[tool.ruff]` (lines 107-113); mypy config in `[tool.mypy]`.

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
- `src/agent/daemon/` — server, run_executor, watcher_service, pubsub, SQLite RunStore (v4), rule_runner
- `src/agent/client/` — async RPC client
- `src/agent/brain/` — LLM providers + router + Claude Code OAuth bridge; `brain/context.py` assembles `BrainContext` injected into every LLM call
- `src/agent/tools/` — Hyprland IPC (native socket, not `hyprctl` subprocess), screen capture, input, clipboard, events
- `src/agent/safety/` — allowlist (deny-by-default + miss counter), confirmation gate, killswitch
- `src/agent/tui/` — Textual monitoring TUI; `widgets/learning_pane.py` is the Ctrl+I learning inbox
- `src/agent/schemas.py` — all Pydantic models (Action, ScreenState, RunSummary, ActionResult, …)
- `src/agent/awareness/` — `WorkingMemory` (per-run action log), `WorldSnapshot` (active windows + focused)
- `src/agent/introspection/` — `SelfModel` (capabilities, constraints, version)
- `src/agent/memory/` — `FastEmbedder` (intfloat/multilingual-e5-large, lazy singleton, ONNX CPU), `EpisodicMemory` (ingest + recall), `EpisodicIngestor`
- `src/agent/learning/` — `LearningConsumer` (single Topic.runs subscriber), `ReflectionEngine`, `SkillLibrary`, `RuleMiner`, `AllowlistMiner`, `api.py` (proposals CRUD + approval side-effects)
- `src/agent/awareness/meta_cognition.py` — `LoopDetector` (ring buffer, repeat_threshold=3), `PostActionVerifier` (dHash pre/post screenshot), `StuckError`

## Multi-provider design

`brain/router.py` resolves `--brain <name>` (or RPC param) to an implementation. Six OpenAI-compatible providers (openai, moonshot, groq, together, zai, qwen) share a single `OpenAICompatibleBrain` class differing only in `base_url` and env-var names — see the `PROVIDERS` registry in `brain/openai_brain.py`. Claude uses its own `ClaudeBrain` with the native `computer_20251124` tool plus custom `list_windows`, `focus_window`, `dispatch_hypr` tools.

**`--brain auto`** reads `~/.config/hyprland-agent/config.yaml`: `brain.auto_order` controls priority, and `brain.providers.<name>.enabled` controls whether a provider can be selected. This is the operational switch for disabling Anthropic/Claude and using OpenAI when credits or OAuth are unavailable.

Provider keys are read **only by the daemon process** and never cross the IPC socket. Clients see run IDs and events, not credentials.

## Configuration & paths

- `~/.config/hyprland-agent/` — `allowlist.yaml`, `rules.yaml`, `learned_rules.yaml` (approved rules appended here by `learning approve rule`), `env`, optional `config.yaml`
- `~/.cache/hyprland-agent/` — `runs.db` (SQLite WAL, schema v4), `STOP` (killswitch flag, polled every 100ms)
- `$XDG_RUNTIME_DIR/hyprland-agent.sock` — daemon RPC socket, mode 0600
- `~/.config/systemd/user/hyprland-agent.service` — installed by `agent service install`
- `HYPRLAND_INSTANCE_SIGNATURE` env var is **required at runtime** (used to locate Hyprland sockets in `tools/hypr.py`)
- `.env.example` is the canonical list of provider env vars

`config.yaml` knobs added in P2/P4:

```yaml
memory:
  enabled: true # episodic memory + recall (intfloat/multilingual-e5-large)
  recall_k: 3 # top-k episodes injected into BrainContext
  embedder_model: "intfloat/multilingual-e5-large"
  filter_failure_in_recall: true

learning:
  enabled: true # LearningConsumer task in daemon
  mining_interval_s: 300 # rule/allowlist mining interval
  skill_extraction_enabled: true
  rule_mining_enabled: true
  allowlist_mining_enabled: true
```

**DB schema versions**: v2 (outcomes, feedback, action_outcomes) → v3 (episodes, episode_vecs, reflections) → v4 (skills, skill_vecs, skill_outcomes, learned_rules, allowlist_proposals). All migrations are applied in sequence in `_init_db`. vec0 (`sqlite-vec`) is loaded per-connection in `_run_vec_sync`.

## Hyprland integration

`tools/hypr.py` talks to Hyprland over native Unix sockets (`.socket.sock` for commands, `.socket2.sock` for events), not by spawning `hyprctl`. `daemon/watcher_service.py` fans events into the `hypr_events` pubsub topic; `daemon/rule_runner.py` matches `rules.yaml` and executes `dispatch` / `log` / `notify` / `run` actions. `run` actions are `shlex.split`-parsed, run with a whitelisted env, and reject destructive first tokens (`rm`, `sudo`, `shutdown`, etc.).

Input is **not** routed through Hyprland: keyboard via `wtype`, mouse via `ydotool` (needs `input` group + `ydotool.service`).

## Self-learning pipeline (P2–P4)

The orchestrator enriches every `BrainContext` via `learning/api.inject_context()`:

1. **Episodic recall** (`memory/episodic.py`): top-3 past runs by cosine similarity (multilingual-e5-large, sqlite-vec). If the embedder model isn't downloaded yet, recall silently returns `[]`.
2. **Negative reflections** (`learning/reflection.py`): rule-based lessons from failed/stuck/errored runs, stored in `reflections` table, injected into the prompt.
3. **Skill suggestions** (`learning/skills.py`): approved skills ranked by task similarity — surfaced in `BrainContext` once a skill is approved via `agent learning approve skill <id>`.

**LearningConsumer** is a single asyncio.Task subscribing to `Topic.runs`. On every `run_finished` event it dispatches to `EpisodicMemory.ingest()` + `ReflectionEngine.reflect()`. No N-subscriber fan-out.

**Loop detection**: `LoopDetector` (window=6, repeat_threshold=3) in the orchestrator run loop. Detects identical `(action_kind, params_json)` repeated ≥3 times → raises `StuckError` → `RunStatus.aborted`.

**Post-action verification**: `PostActionVerifier` takes a dHash (8×8 Pillow `tobytes()`) before and after visual actions (click, mouse_move, scroll, focus_window, dispatch_hypr). Identical hash → `result.warnings.append("no visual change")`.

**Learning inbox** (`agent learning {list,approve,reject,show}`): proposals are never auto-approved. Approval side-effects:

- `skill` → UPDATE `skills.status = 'approved'` in DB
- `rule` → append YAML to `learned_rules.yaml` + daemon `reload_rules`
- `allowlist` → append entry to `allowlist.yaml`

**Safety invariant preserved**: `_ALWAYS_DENY` is hardcoded and cannot be bypassed by any learning path. `is_allowed()` reads only YAML files, not DB proposals.

## Gotchas

- **`max_completion_tokens`, not `max_tokens`**, for OpenAI requests (`brain/openai_brain.py`) — required by gpt-5.x. Using `max_tokens` will fail.
- **Brain loop is hard-capped at 20 iterations** (`_MAX_LOOP = 20` in both `claude.py` and `openai_brain.py`). On overflow a warning is logged and the run ends without completing — increase carefully.
- **Run hard timeout is 300s** (`_RUN_TIMEOUT` in `daemon/run_executor.py`). Long screen tasks abort with `RunStatus.errored`.
- **Screenshot is downscaled to 0.5×** before sending to the brain; the brain's coords are scaled back up before dispatch. Coordinate translation lives in **two places** — `claude.py`'s `_computer_action_to_actions` and `openai_brain.py`'s `_sc()` helper. Keep them in parity when adding new action kinds.
- **Key normalization** (`tools/input.py`): the LLM uses friendly names (`enter`, `esc`, `pageup`, `super`) which are mapped to `wtype` X11 names (`Return`, `Escape`, `Prior`). Modifiers are sent with `-M` and released in reverse order with `-m`.
- **Terminal commands** use `terminal_command` and `tools/terminal.py`, not `type_text` + `Return` into the focused terminal. `hold_s` is only for visible debug/test runs and is capped at 30 seconds.
- **Killswitch is edge-triggered**: the `STOP` file flag is consumed by `disarm()` after detection to avoid log spam. `agent stop` always writes the file flag, then also sends RPC if the daemon is reachable.
- **Allowlist defaults to deny-all**. Password-manager class names (`1password`, `_1password`, `keepassxc`, `gnome-keyring`) are always blocked regardless of the allowlist.
- **NDJSON frame size cap is 1 MiB** (`ipc/constants.py`). Protocol version 1.0; major-version mismatches are rejected.
- **Provider enablement is config-driven**. Explicit `--brain openai` or `--brain claude` fails if that provider is disabled in `config.yaml`; `auto` skips disabled or uncredentialed providers.
- **sqlite-vec loaded per-connection**: `_run_vec_sync` calls `_load_vec0(conn)` on every invocation. `_run_sync` does NOT load vec0. Do not call vec queries through `_run_sync` or they will silently return empty results.
- **`intfloat/multilingual-e5-large` model is ~1.3 GB** and downloaded lazily on first embed call to `~/.cache/fastembed`. Mark tests that need the real embedder with `@pytest.mark.slow`; stub it with `[[0.1]*1024]` for unit tests.
- **`watcher_service.load_rules()`** merges `rules.yaml` and `learned_rules.yaml` with dedup by `(on, match)` key. Duplicate rules across both files are silently dropped.

## Integrations (P5)

Entry-points group `hyprland_agent.integrations` — third-party packages can register integrations by adding entries to this group. Built-in integrations live in `src/agent/integrations/`.

**`IntegrationRegistry`** (`src/agent/integrations/__init__.py`): discovers integrations via `importlib.metadata.entry_points`, calls `setup()` on each, routes `ActionKind.notify` / `ActionKind.update_status` to all registered integrations via `handle()`. Lifecycle is tied to `AppState.open()` / `AppState.close()` in `src/agent/daemon/state.py`.

**`CapabilitySpec`** declares what an integration can do (`action_kinds`, `context_keys`). Schema version is `INTEGRATIONS_API_VERSION = "1.0"` — major-version mismatch causes the integration to be skipped.

**Built-in integrations:**

| Module | Class | Role |
| ------ | ----- | ---- |
| `integrations/mako.py` | `MakoIntegration` | `notify-send` with app-name and urgency mapping |
| `integrations/waybar.py` | `WaybarIntegration` | server-side no-op; client is `cli/waybar_module.py` |
| `integrations/fuzzel.py` | `FuzzelIntegration` | binary probe; client is `cli/fuzzel_launcher.py` |
| `integrations/idle.py` | `IdleIntegration` | D-Bus `org.freedesktop.ScreenSaver` → cancel active runs on lock |

**Desktop launcher**: `packaging/desktop/hyprland-agent-tui.desktop` ships via the AUR package (`/usr/share/applications/`). Exec: `foot --app-id=hyprland-agent-tui agent tui`. Requires `foot` (declared as `optdepend` in PKGBUILD).

**Console scripts:** `agent-waybar` → `cli/waybar_module.py:main`; `fuzzel-agent` → `cli/fuzzel_launcher.py:main`. Both are thin async clients over the daemon socket.

**Enabled integrations** are controlled by `config.yaml` `integrations.enabled` list. An empty list loads all discovered integrations. `idle` is intentionally excluded from the user's local config.

## Known test state

`uv run pytest` → 338 passed. `uv run pytest -m "not slow"` skips embedder download tests. The Textual error-screen snapshot is tracked; inspect `snapshot_report.html` before intentionally updating it after TUI rendering changes.
