# Architecture

hyprland-agent is a **daemon-centric** application: the daemon owns all state,
execution, and tool dispatch. CLI and TUI are thin RPC clients over a Unix
socket. This design means you can kill and restart the CLI at any point without
losing a running task.

For implementation details and gotchas see [`CLAUDE.md`](../CLAUDE.md). This
document is the high-level public reference for contributors.

---

## Component flow

```
agent run "<task>"
    └─ src/agent/cli/           (Typer commands, RPC client)
        └─ NDJSON over $XDG_RUNTIME_DIR/hyprland-agent.sock (mode 0600)
            └─ src/agent/daemon/server.py        (RPC dispatch)
                └─ daemon/run_executor.py        (queue, 300 s hard timeout)
                    └─ orchestrator.py           (the task loop)
                        ├─ safety/killswitch.py  (polled between every action)
                        ├─ safety/allowlist.py   (deny-by-default)
                        ├─ tools/screen.py       (grim → 0.5× downscale → bytes)
                        ├─ brain/router.py       (selects brain implementation)
                        │   ├─ brain/claude.py           (Anthropic computer_20251124)
                        │   └─ brain/openai_brain.py     (6 providers, PROVIDERS registry)
                        └─ tools/{input,hypr,clipboard}.py  (execute actions)
```

---

## Module map

| Module | Role |
|--------|------|
| `src/agent/ipc/` | Shared NDJSON wire protocol — Pydantic discriminated union, 1 MiB frame cap, protocol v1.0 |
| `src/agent/daemon/` | `server.py` RPC dispatch, `run_executor.py` queue + timeout, `watcher_service.py` Hyprland event fan-out, `pubsub.py` internal topic bus, `store.py` SQLite RunStore (schema v4), `rule_runner.py` watcher rules |
| `src/agent/client/` | Async RPC client; used by CLI and TUI |
| `src/agent/brain/` | LLM providers + `router.py` + Anthropic SDK client (`anthropic_client.py`); `context.py` assembles `BrainContext` injected into every LLM call |
| `src/agent/tools/` | Hyprland native IPC (not `hyprctl`), screen capture, keyboard (`wtype`), mouse (`ydotool`), clipboard, events |
| `src/agent/safety/` | `allowlist.py` deny-by-default + miss counter, `confirm.py` gate, `killswitch.py` STOP flag (edge-triggered) |
| `src/agent/tui/` | Textual monitoring TUI; `widgets/learning_pane.py` is the Ctrl+I Learning Inbox |
| `src/agent/schemas.py` | All Pydantic models: `Action`, `ScreenState`, `RunSummary`, `ActionResult`, … |
| `src/agent/awareness/` | `WorkingMemory` (per-run action log), `WorldSnapshot` (active windows + focused), `meta_cognition.py` (loop detection + post-action visual verify) |
| `src/agent/introspection/` | `SelfModel` — capabilities, constraints, version string exposed to the brain |
| `src/agent/memory/` | `FastEmbedder` (intfloat/multilingual-e5-large, lazy ONNX singleton), `EpisodicMemory` (ingest + cosine recall), `EpisodicIngestor` |
| `src/agent/learning/` | `LearningConsumer`, `ReflectionEngine`, `SkillLibrary`, `RuleMiner`, `AllowlistMiner`, `api.py` (proposals CRUD + approval side-effects) |
| `src/agent/integrations/` | `IntegrationRegistry`, `CapabilitySpec`, built-in Mako / Waybar / Fuzzel / Idle integrations |

---

## Multi-provider design

`brain/router.py` resolves `--brain <name>` to an implementation. Six
OpenAI-compatible providers (`openai`, `moonshot`, `groq`, `together`, `zai`,
`qwen`) share a single `OpenAICompatibleBrain` class — they differ only in
`base_url` and env-var names. See the `PROVIDERS` registry in
`brain/openai_brain.py`. Claude uses its own `ClaudeBrain` with the native
`computer_20251124` tool.

**`--brain auto`** selects the first enabled and credentialed provider from
`brain.auto_order` in `~/.config/hyprland-agent/config.yaml`. Provider keys are
read only by the daemon process and never cross the IPC socket.

---

## Safety model

Three independent gates protect every action:

1. **Allowlist** (`safety/allowlist.py`) — deny-by-default per window class.
   Password managers (`1password`, `keepassxc`, etc.) are hardcoded as always
   blocked regardless of user configuration.
2. **Killswitch** (`safety/killswitch.py`) — polled between every action. The
   `STOP` file flag in `~/.cache/hyprland-agent/` is edge-triggered (consumed on
   detection). `SUPER+SHIFT+ESC` writes it; `agent stop` writes it and sends RPC.
3. **Explicit planning** — `agent plan` shows the action sequence before
   `agent run` executes it.

---

## SQLite schema versioning

All migrations are applied in sequence by `_init_db` in `daemon/store.py`.
`sqlite-vec` (vec0 extension) is loaded per-connection in `_run_vec_sync`.

| Version | Tables added |
|---------|-------------|
| v1 | `runs`, `actions`, `run_events` |
| v2 | `outcomes`, `feedback`, `action_outcomes` |
| v3 | `episodes`, `episode_vecs` (vec0), `reflections` |
| v4 | `skills`, `skill_vecs`, `skill_outcomes`, `learned_rules`, `allowlist_proposals` |

---

## Hyprland integration

`tools/hypr.py` communicates over native Hyprland Unix sockets
(`.socket.sock` for commands, `.socket2.sock` for events) — no `hyprctl`
subprocess. `daemon/watcher_service.py` fans events into the `hypr_events`
pubsub topic. `daemon/rule_runner.py` matches `rules.yaml` + `learned_rules.yaml`
and dispatches `dispatch` / `log` / `notify` / `run` actions. `run` actions are
`shlex.split`-parsed with a deny list for destructive first tokens.

Input bypasses Hyprland entirely: keyboard via `wtype`, mouse via `ydotool`
(requires `input` group and `ydotool.service`).

---

## Self-learning pipeline

The orchestrator enriches every `BrainContext` via `learning/api.inject_context()`:

1. **Episodic recall** (`memory/episodic.py`): top-3 past runs by cosine
   similarity (multilingual-e5-large embeddings stored in sqlite-vec). Silently
   returns `[]` if the model has not been downloaded yet.
2. **Negative reflections** (`learning/reflection.py`): rule-based lessons from
   failed / stuck / errored runs, stored in `reflections` table.
3. **Skill suggestions** (`learning/skills.py`): approved skills ranked by task
   similarity, surfaced once approved via `agent learning approve skill <id>`.

`LearningConsumer` is a single asyncio.Task subscribing to `Topic.runs`. On
every `run_finished` event it dispatches to `EpisodicMemory.ingest()` and
`ReflectionEngine.reflect()`.

Safety invariant: `_ALWAYS_DENY` is hardcoded and cannot be bypassed by any
learning or approval path.

---

## Integrations system

Third-party packages register integrations via the entry-points group
`hyprland_agent.integrations`. Built-in integrations:

| Module | Class | Role |
|--------|-------|------|
| `integrations/mako.py` | `MakoIntegration` | Desktop notifications via `notify-send` |
| `integrations/waybar.py` | `WaybarIntegration` | Status module for Waybar |
| `integrations/fuzzel.py` | `FuzzelIntegration` | Task launcher via fuzzel dmenu |
| `integrations/idle.py` | `IdleIntegration` | Cancel active runs on screen lock (D-Bus) |

`IntegrationRegistry` discovers integrations at daemon startup, calls `setup()`,
and routes `ActionKind.notify` / `ActionKind.update_status` to all registered
handlers. Schema version `INTEGRATIONS_API_VERSION = "1.0"` — major-version
mismatch causes the integration to be skipped.

Console scripts: `agent-waybar` (`cli/waybar_module.py`) and `fuzzel-agent`
(`cli/fuzzel_launcher.py`) are thin async RPC clients over the daemon socket.

**Desktop launcher**: the AUR package installs
`packaging/desktop/hyprland-agent-tui.desktop` to `/usr/share/applications/`.
It opens the monitoring TUI via `foot --app-id=hyprland-agent-tui agent tui`.
The `StartupWMClass=hyprland-agent-tui` field lets Hyprland window rules match it
by class. Requires `foot` (listed as `optdepend`).

---

## Configuration and paths

| Path | Purpose |
|------|---------|
| `~/.config/hyprland-agent/allowlist.yaml` | Window class allow rules |
| `~/.config/hyprland-agent/rules.yaml` | Watcher rules (human-authored) |
| `~/.config/hyprland-agent/learned_rules.yaml` | Approved learned rules |
| `~/.config/hyprland-agent/config.yaml` | Provider enablement, memory/learning knobs |
| `~/.config/hyprland-agent/env` | Provider API keys (read only by daemon) |
| `~/.cache/hyprland-agent/runs.db` | SQLite WAL run store (schema v4) |
| `~/.cache/hyprland-agent/STOP` | Killswitch flag file |
| `~/.cache/fastembed/` | Embedder model cache (~1.3 GB after first use) |
| `$XDG_RUNTIME_DIR/hyprland-agent.sock` | Daemon RPC socket (mode 0600) |
| `~/.config/systemd/user/hyprland-agent.service` | Systemd user unit |
