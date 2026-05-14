# hyprland-agent

Local-first desktop agent for Hyprland / Wayland. It turns natural-language
tasks and Hyprland events into controlled desktop actions, with explicit
allowlists, a kill switch, local run history, and daemon-side observability.

The project is meant to be a personal desktop control plane: the agent observes
the screen, asks a computer-use or vision model for actions, executes those
actions through Wayland/Hyprland tools, and records what happened.

## What this is

- A local control plane for agentic desktop automation on Hyprland.
- A daemon with CLI/TUI clients, NDJSON IPC, pubsub topics, run storage, and
  event-driven rules.
- A safety-oriented desktop tool: empty allowlist means deny all, password
  manager windows are always blocked, and a file-backed kill switch is required
  before real agentic runs.

## What this is not

- Not a generic cloud RPA platform.
- Not a multi-provider router for arbitrary model benchmarking.
- Not a tool to run without an allowlist, a kill switch, and an explicit plan pass.
- Not a safe way to expose your desktop socket to other users or machines.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ hyprland-agent daemon  (systemd user service)            │
│ ┌─────────────┐ ┌──────────────┐ ┌───────────────────┐  │
│ │ Hypr event  │ │ Run executor │ │ Watcher service   │  │
│ │ subscriber  │ │ (queue, exec │ │ (rules -> bus)    │  │
│ │ (fan-out)   │ │ orchestrator)│ │                   │  │
│ └─────────────┘ └──────────────┘ └───────────────────┘  │
│        │              │                  │               │
│        ▼              ▼                  ▼               │
│      PubSub bus (topics: runs, hypr_events, logs)        │
│        │                                                  │
│  ┌─────┴────┐   ┌──────────────┐   ┌──────────────┐      │
│  │ SQLite   │   │ JSONL audit  │   │ Killswitch   │      │
│  │ RunStore │   │ (opt-in)     │   │ poll + RPC   │      │
│  └──────────┘   └──────────────┘   └──────────────┘      │
│                                                           │
│  $XDG_RUNTIME_DIR/hyprland-agent.sock  (NDJSON, 0600)    │
└──────────────────────────────────────────────────────────┘
              ▲                ▲              ▲
       ┌──────┴─────┐   ┌──────┴─────┐  ┌────┴────┐
       │ CLI client │   │ TUI client │  │ stop    │
       │ (typer)    │   │ (textual)  │  │ flag    │
       └────────────┘   └────────────┘  └─────────┘
```

```
src/agent/
  ipc/           Shared NDJSON protocol: frames, framing, constants
  daemon/        Long-running server: IPC, pubsub, run executor, watcher, SQLite
  client/        Async RPC client used by CLI and TUI
  tui/           Textual monitoring TUI
  tools/         Hyprland IPC, screen capture, keyboard, mouse, clipboard
  brain/         LLM clients: Claude computer-use, OpenAI-compatible vision, router
  safety/        Allowlist, confirmation gate, kill switch
  orchestrator   Task loop: screenshot -> brain -> actions -> execute
```

## Prerequisites

### System packages

```bash
sudo pacman -S ydotool wtype grim wl-clipboard
```

### ydotool daemon

```bash
# Add yourself to the input group (re-login required)
sudo usermod -aG input $USER

# Enable and start the daemon
systemctl --user enable --now ydotool.service
```

After adding yourself to the `input` group, re-login or open a fresh session.

### Python environment

For development, keep dependencies in the repo-local uv environment:

```bash
cd ~/Workspace/ai-agents/hyprland_agent
uv sync
```

Do not point the long-running host service at this checkout venv. Install the
runtime separately before enabling the service:

```bash
scripts/install-local.sh
scripts/verify-local-install.sh
```

The installer builds a wheel from the checkout, installs it into:

```text
~/.local/share/hyprland-agent/venv
```

and points `~/.local/bin/agent` plus the user systemd unit at that installed
runtime. The source checkout remains for code, tests, and future builds only.

## Provider policy

The agent controls a real desktop, so provider choice is reliability-first.
Claude is the recommended action brain when available, but every provider can
be enabled or disabled from local config. This matters operationally: if
Anthropic credits or OAuth are unavailable, disable Claude and let `auto` use
OpenAI or another configured provider.

| Role             | Provider                      |                        Brain option | Default model       |
| ---------------- | ----------------------------- | ----------------------------------: | ------------------- |
| Primary          | Anthropic Claude computer-use |                    `--brain claude` | `claude-opus-4-7`   |
| Claude fallback  | Anthropic Claude computer-use | `ANTHROPIC_MODEL=claude-sonnet-4-6` | `claude-sonnet-4-6` |
| Premium fallback | OpenAI vision/tool calling    |                    `--brain openai` | `gpt-5.2`           |
| Economy fallback | Moonshot Kimi                 |                      `--brain kimi` | `kimi-k2.6`         |
| Experimental     | Groq                          |                      `--brain groq` | see `.env.example`  |
| Experimental     | Together AI                   |                  `--brain together` | see `.env.example`  |
| Experimental     | Z.AI / GLM                    |      `--brain zai` or `--brain glm` | see `.env.example`  |
| Experimental     | Qwen / DashScope              |                      `--brain qwen` | see `.env.example`  |

Avoid routed or aggregate providers as the default desktop-control brain.
Desktop screenshots are sensitive, and action reliability matters more than
provider breadth.

Provider selection is controlled by:

```yaml
# ~/.config/hyprland-agent/config.yaml
brain:
  default: auto
  auto_order: [openai, claude, moonshot, groq, together, zai, qwen]
  providers:
    claude:
      enabled: false
    openai:
      enabled: true
    moonshot:
      enabled: false
    groq:
      enabled: false
    together:
      enabled: false
    zai:
      enabled: false
    qwen:
      enabled: false
audit_log: false
```

With that config and `OPENAI_API_KEY` in the daemon environment, `agent plan`
and `agent run` use OpenAI through `--brain auto`. Explicit provider
choices still work only when that provider is enabled in config.

## Credentials

Claude uses Claude Code OAuth credentials. Supported sources are:

- `CLAUDE_CODE_OAUTH_TOKEN`, for a token created by Claude Code.
- `~/.claude/.credentials.json`, used as the fallback credential source.

No `ANTHROPIC_API_KEY` is required for the Claude Code OAuth path.

Override the Claude model with:

```bash
export ANTHROPIC_MODEL=claude-sonnet-4-6
```

OpenAI-compatible providers use environment variables in the daemon process.
Use `.env.example` as the canonical list of keys and model override names.
Provider enablement belongs in `config.yaml`; credentials belong in the daemon
environment.

Recommended injection options:

- **1Password**

  ```bash
  op run --env-file=$HOME/.config/op/secrets.env -- agent daemon
  ```

- **systemd EnvironmentFile**

  Add this to the user service and put provider keys in that file:

  ```ini
  EnvironmentFile=%h/.config/hyprland-agent/env
  ```

Provider keys are read by the daemon process and are never sent over the IPC
socket.

## Setup

```bash
# 1. Start the daemon in the foreground
agent daemon

# 2. Create the allowlist. Empty allowlist means deny all.
agent config init-allowlist
# Edit ~/.config/hyprland-agent/allowlist.yaml

# 3. Bind the kill switch hotkey
agent config bind-killswitch
hyprctl reload

# 4. Check prerequisites and live configuration
agent doctor
```

### systemd service

```bash
scripts/install-local.sh
systemctl --user status hyprland-agent
scripts/verify-local-install.sh
```

`agent migrate-systemd` only rewrites the user unit. For a clean host runtime,
prefer `scripts/install-local.sh`, which installs outside the repository before
restarting the daemon.

### First safe run

Use `plan` before allowing real desktop actions:

```bash
agent plan "resize the focused window to 800x600"
agent run "open foot and run htop"
```

## Usage

```bash
# Execute a task
agent run "open foot and run htop"
agent run --brain openai "find and click the Accept button"
agent run --brain kimi "summarize the visible terminal output"
agent run "run printf hello in an agent-owned terminal and keep it visible for 3 seconds"

# Plan actions without executing them
agent plan "resize the focused window to 800x600"

# List open windows
agent windows

# Capture current screen
agent screenshot -o /tmp/screen.png

# Stream Hyprland events
agent events

# Run history
agent list-runs
agent list-runs --limit 50
agent get-run <run-id>

# Daemon status and monitoring
agent status
agent tui

# Watcher rules
agent rules reload

# Health check and kill switch
agent doctor
agent stop
```

## Kill switch

During a running task, press `SUPER+SHIFT+ESC` to arm the kill switch. The agent
stops within one action cycle.

Two independent paths are used:

1. File flag: `~/.cache/hyprland-agent/STOP`, polled every 100ms.
2. RPC: `arm_killswitch`, sent over the daemon socket when reachable.

`agent stop` always creates the file flag, then also sends the RPC if the daemon
is up.

## Allowlist

The agent refuses to act on windows not in the allowlist. Edit:

```text
~/.config/hyprland-agent/allowlist.yaml
```

Example:

```yaml
allow:
  - class: foot
    title: "*"
  - class: firefox
    title: "*"
  - class: chromium
    title: "*"
```

Globs are supported. Windows matching `1password`, `_1password`, `keepassxc`, or
`gnome-keyring` are always blocked regardless of the allowlist.

## Watch rules

Create or edit:

```text
~/.config/hyprland-agent/rules.yaml
```

The implemented rule format is:

```yaml
rules:
  - on: openwindow
    match:
      class: spotify
    actions:
      - dispatch: "movetoworkspace 9"

  - on: activewindow
    match:
      class: foot
    actions:
      - log: "terminal focused"
      - notify: "Terminal active"

  - on: openwindow
    match:
      class: "*"
      title: "*zoom*"
    actions:
      - dispatch: "movetoworkspace 8"

  - on: openwindow
    match:
      class: firefox
    actions:
      - run: "notify-send 'hyprland-agent' 'Firefox opened'"
```

Supported events:

```text
openwindow, closewindow, activewindow, workspace, focusedmon, urgent
```

Supported actions:

- `dispatch`: Hyprland dispatch command.
- `log`: daemon logger entry.
- `notify`: `notify-send` message.
- `run`: command string parsed with `shlex.split`.

`run` actions are constrained by the rule runner:

- The command is parsed into argv, not run through a shell.
- The environment is whitelisted.
- Denied first tokens include `rm`, `dd`, `shutdown`, `reboot`, `kill`, `sudo`,
  `su`, and similar destructive or privilege-changing commands.
- Each action has a timeout.

After editing rules:

```bash
agent rules reload
```

## Run storage

Runs are stored in SQLite at:

```text
~/.cache/hyprland-agent/runs.db
```

The database uses WAL mode and stores a summary plus event timeline for each
run.

```bash
agent list-runs
agent get-run <run-id>
```

Opt-in JSONL audit logging is available when `audit_log: true` is set in:

```text
~/.config/hyprland-agent/config.yaml
```

## Security notes

- Bind the kill switch before running real desktop tasks.
- Keep the allowlist tight. Do not allow password managers, root terminals, or
  sensitive credential windows.
- Treat screenshots as sensitive data. Provider choice is a security decision.
- Keep the daemon socket local. It is created under `$XDG_RUNTIME_DIR` with mode
  `0600`.
- Use `agent plan` before first real runs or after changing providers.
- For visible terminal validation, explicitly ask to keep the agent-owned
  terminal open for a few seconds; normal shell commands close immediately.
- Do not rely on watch rules for destructive host operations.

## Breaking changes (v1 -> v2)

| Old command             | New command                                                               |
| ----------------------- | ------------------------------------------------------------------------- |
| `agent init-allowlist`  | `agent config init-allowlist`                                             |
| `agent bind-killswitch` | `agent config bind-killswitch`                                            |
| `agent watch`           | Watcher runs inside the daemon. Use `agent rules reload` to reload rules. |

| Old                            | New                                                   |
| ------------------------------ | ----------------------------------------------------- |
| `hyprland-agent-watch.service` | `hyprland-agent.service`; run `agent migrate-systemd` |
| JSONL as primary storage       | SQLite `runs.db`; JSONL is opt-in audit output        |
| `RunSummary.dry_run: bool`     | `RunSummary.kind: RunKind` (`run`\|`plan`)            |
| `agent dry-run`                | `agent plan`                                          |

## Current validation status

The codebase is currently green in this workspace.

Observed on this workspace:

```bash
uv run pytest
```

Result:

```text
180 tests collected
180 passed
```

The Textual error-screen snapshot is tracked under `tests/__snapshots__/`.
If it fails after a TUI change, inspect `snapshot_report.html` before updating
the snapshot intentionally.

## Development

```bash
uv run pytest
uv run agent doctor
uv run agent daemon -v
```

The development command `uv run agent daemon -v` is for foreground debugging.
The installed Lenovo service should run through `~/.local/bin/agent`, which must
resolve outside `~/Workspace/ai-agents/hyprland_agent`.

Before changing behavior, compare the README against:

- `src/agent/cli.py` for commands.
- `src/agent/schemas.py` and `src/agent/daemon/rule_runner.py` for watch rules.
- `.env.example` for provider environment variables.
