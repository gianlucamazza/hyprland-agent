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
| `src/agent/ipc/` | Shared NDJSON wire protocol — Pydantic discriminated union, 1 MiB frame cap, protocol v1.0, `SOCKET_PATH` |
| `src/agent/daemon/` | `server.py` RPC dispatch, `run_executor.py` queue + timeout, `watcher_service.py` Hyprland event fan-out, `pubsub.py` internal topic bus, `store.py` SQLite RunStore (schema v5), `rule_runner.py` watcher rules, `audit_log.py` run audit trail, `log_publisher.py` structured log distribution |
| `src/agent/client/` | Async RPC client; used by CLI and TUI |
| `src/agent/brain/` | LLM providers + `router.py` + Anthropic SDK client (`anthropic_client.py`); `context.py` assembles `BrainContext` injected into every LLM call |
| `src/agent/tools/` | Hyprland native IPC (not `hyprctl`), screen capture, keyboard (`wtype`), mouse (`ydotool`), clipboard (`wl-copy`/`wl-paste`), events, filesystem I/O |
| `src/agent/safety/` | `allowlist.py` deny-by-default + miss counter, `confirm.py` gate, `killswitch.py` STOP flag (edge-triggered), `rate_limit.py` per-action-type rate limiter + command sanitizer |
| `src/agent/tui/` | Textual monitoring TUI; `widgets/learning_pane.py` is the Ctrl+I Learning Inbox |
| `src/agent/schemas.py` | All Pydantic models: `Action`, `ScreenState`, `RunSummary`, `ActionResult`, … |
| `src/agent/awareness/` | `WorkingMemory` (per-run action log), `WorldSnapshot` (active windows + focused), `meta_cognition.py` (loop detection + post-action visual verify) |
| `src/agent/introspection/` | `SelfModel` — capabilities, constraints, version string exposed to the brain |
| `src/agent/memory/` | `FastEmbedder` (intfloat/multilingual-e5-large, lazy ONNX singleton), `EpisodicMemory` (ingest + cosine recall) |
| `src/agent/learning/` | `LearningConsumer`, `ReflectionEngine`, `RuleMiner`, `AllowlistMiner`, `api.py` (proposals CRUD + approval side-effects), `outcome.py` (feedback→outcome derivation) |
| `src/agent/integrations/` | `IntegrationRegistry`, `CapabilitySpec`, built-in Mako / Waybar / Fuzzel / Idle / Voice integrations |
| `src/agent/voice/` | Voice I/O sidecar engines: Piper TTS, faster-whisper STT, openWakeWord, Silero VAD, ring buffer, redaction, audio pipeline |
| `src/agent/diagnostics.py` | Health checks for `agent doctor` (binaries, sockets, credentials, connectivity) |
| `src/agent/paths.py` | Shared path helpers (`CONFIG_DIR`, `CACHE_DIR`, `runtime_dir()`, …) |

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
`sqlite-vec` (vec0 extension) is loaded per-connection in `run_vec_sync`.

| Version | Tables added |
|---------|-------------|
| v1 | `runs`, `actions`, `run_events` |
| v2 | `outcomes`, `feedback`, `action_outcomes` |
| v3 | `episodes`, `episode_vecs` (vec0), `reflections` |
| v4 | `skills`, `skill_vecs`, `skill_outcomes`, `learned_rules`, `allowlist_proposals` |
| v5 | Adds `decay_score REAL DEFAULT 1.0` and `last_accessed_at REAL` columns to `episodes`, `reflections`, `skills` (memory decay) |

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
3. **Approved skills**: surfaced via `agent learning approve skill <id>` / `agent learning list skill`.
   Skill extraction (`SkillLibrary`) was removed as dead code; skills must be added manually through the learning inbox.

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
| `integrations/voice.py` | `VoiceIntegration` | Wires `ActionKind.speak`, publishes `Topic.voice` state |

`IntegrationRegistry` discovers integrations at daemon startup, calls `setup()`,
and routes `ActionKind.notify` / `ActionKind.update_status` / `ActionKind.speak` to all registered
handlers. Schema version `INTEGRATIONS_API_VERSION = PROTOCOL_VERSION` (derived from `ipc.constants`)
— major-version mismatch causes the integration to be skipped.

Console scripts: `agent-waybar` (`cli/waybar_module.py`), `fuzzel-agent`
(`cli/fuzzel_launcher.py`), and `agent-voice` (`cli/voice_sidecar.py`) are thin
async RPC clients over the daemon socket.

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
| `~/.cache/hyprland-agent/runs.db` | SQLite WAL run store (schema v5) |
| `~/.cache/hyprland-agent/STOP` | Killswitch flag file |
| `~/.cache/hyprland-agent/voice/` | STT / TTS / wake-word model cache |
| `$XDG_RUNTIME_DIR/hyprland-agent-voice.sock` | Voice sidecar PTT socket |
| `$XDG_RUNTIME_DIR/hyprland-agent-voice.muted` | Mute flag for voice capture |
| `~/.cache/fastembed/` | Embedder model cache (~1.3 GB after first use) |
| `$XDG_RUNTIME_DIR/hyprland-agent.sock` | Daemon RPC socket (mode 0600) |
| `~/.config/systemd/user/hyprland-agent.service` | Systemd user unit |
| `~/.config/hyprland-agent/voice.yaml` | Voice subsystem config (STT/TTS/wake/VAD) |

---

## Voice subsystem

Voice adds an optional speech I/O channel via a **sidecar** architecture:

```
agent-voice                           (src/agent/cli/voice_sidecar.py)
  │  ┌──────────────────────────┐
  │  │ AudioSource (sounddevice) │ ← PipeWire input @ 16 kHz mono
  │  │ AudioSink   (sounddevice) │ → PipeWire output
  │  └──────────┬───────────────┘
  │             │ ring buffer (1.5 s pre-wake)
  │  ┌──────────▼───────────────┐
  │  │ WakeEngine (openWakeWord)│   IDLE ──► ARMED ──► CAPTURING
  │  │ VadEngine (Silero VAD)   │     ▲                       │
  │  │ SttEngine (faster-whisper)│   │    endpoint (700 ms)    │
  │  │ TtsEngine (Piper)        │   ◄──────── TRANSCRIBING    │
  │  └──────────────────────────┘              │
  │         │ RPC (run_task / cancel_run)      ▼
  │         └─────────────────────► daemon  SUBMITTING
  │                                              │
  │         ◄────────── Topic.runs ──────────────┘
  │                    run_started → TTS "Avvio: …"
  │                    run_done    → TTS "Fatto"
  │                    run_error   → TTS "Errore: …"
  │
  └──────────────────────────────────────────────────
         PTT socket: $XDG_RUNTIME_DIR/hyprland-agent-voice.sock
         Mute flag:  $XDG_RUNTIME_DIR/hyprland-agent-voice.muted
```

**Architecture boundary** — hybrid:
- **`agent-voice` sidecar** (`src/agent/cli/voice_sidecar.py`): owns audio I/O, ML engines, FSM, barge-in. Heavy deps isolated here.
- **`VoiceIntegration`** (`src/agent/integrations/voice.py`): thin daemon-integrated class. Registers `ActionKind.speak`, publishes `Topic.voice` state, wires killswitch pause.

**FSM states**: `IDLE → ARMED → CAPTURING → TRANSCRIBING → SUBMITTING → LISTENING_EVENTS → SPEAKING → IDLE`

**Engine protocol** — each engine implements a Protocol in `src/agent/voice/engines/__init__.py`. Built-in engines loaded via `hyprland_agent.voice.*` entry points, mirroring the integration registry pattern.

**Privacy**:
- Audio never crosses IPC; only transcribed text reaches the daemon via `RpcMethod.run_task`.
- Mute flag checked at every wake; killswitch arms → sidecar closes PipeWire input.
- Transcript opt-in (`voice.privacy.log_transcripts`), stored `0600` with TTL rotation.
- Pre-TTS redaction (`src/agent/voice/redact.py`) replaces tokens/secrets/paths with `[REDACTED]`.
- Cloud engines blocked by default (`voice.privacy.allow_cloud_engines: false`).

**Configuration** — two-tier: `config.yaml` holds `integrations.voice.enabled: bool`; full voice config lives in `~/.config/hyprland-agent/voice.yaml`.

**Roadmap** (M1 = current skeleton):
| Milestone | Deliverable |
|-----------|-------------|
| M1 skeleton | VoiceIntegration, Topic.voice, ActionKind.speak, voice config, sidecar entry point |
| M2 TTS-only | Piper, subscribe Topic.runs, template + redact, mute file |
| M3 STT+PTT | PTT socket, faster-whisper, submit. Hyprland hotkey documented |
| M4 wake-word+VAD+barge-in | openWakeWord, Silero VAD, ring buffer, barge-in |
| M5 packaging | AUR split package, systemd unit |
| M6 polish | Cloud engine opt-in, Parakeet TDT v3, Kokoro TTS |

The engine abstraction lets each piece land independently. After M2 the sidecar is already useful for accessibility (TTS feedback on run completion).
