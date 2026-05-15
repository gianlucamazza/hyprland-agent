# examples/

Template configuration files. Copy them to `~/.config/hyprland-agent/` and edit.

| File | Destination | Purpose |
|------|-------------|---------|
| `allowlist.yaml` | `~/.config/hyprland-agent/allowlist.yaml` | Which windows the agent can interact with |
| `rules.yaml` | `~/.config/hyprland-agent/rules.yaml` | Event-driven automation rules |
| `config.yaml` | `~/.config/hyprland-agent/config.yaml` | Brain, memory, learning settings |
| `env` | `~/.config/hyprland-agent/env` | Provider API keys (sensitive — mode 600) |

## Quick setup

```bash
mkdir -p ~/.config/hyprland-agent
cp examples/allowlist.yaml ~/.config/hyprland-agent/allowlist.yaml
cp examples/config.yaml    ~/.config/hyprland-agent/config.yaml
install -Dm600 examples/env ~/.config/hyprland-agent/env
# Edit the files, then:
agent doctor
```

`install-local.sh` copies `env` automatically on first install if the file is missing.
