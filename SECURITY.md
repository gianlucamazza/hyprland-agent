# Security Policy

## Scope

hyprland-agent is a daemon that issues **real keyboard/mouse input**, captures **desktop screenshots**, and sends them to external LLM providers. The attack surface includes:

- The Unix domain socket (`$XDG_RUNTIME_DIR/hyprland-agent.sock`, mode 0600) — only processes running as the same user can connect.
- The allowlist/killswitch mechanism — controls which windows the agent may interact with.
- Provider API keys — stored in `~/.config/hyprland-agent/env`, never transmitted over IPC.
- Screenshot data — sent to the configured LLM provider as part of each step.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Email: **homen3@gmail.com** with subject `[hyprland-agent security] <short description>`.

Include:
- Description of the vulnerability and its potential impact.
- Steps to reproduce.
- Affected version(s).

I aim to acknowledge receipt within **7 days** and provide a resolution or mitigation within **30 days**.

## Known Limitations / Non-Issues

The following are by design and will not be treated as security vulnerabilities:

- Screenshots contain whatever is on screen at action time, including sensitive content. **You** control which provider receives them.
- The daemon can type arbitrary text into any window not blocked by the allowlist — this is the intended functionality. Use the allowlist to restrict which windows are reachable.
- The killswitch (`~/.cache/hyprland-agent/STOP`) is edge-triggered and race conditions are theoretically possible under extreme load — this is a usability safeguard, not a security boundary.
- `ydotool` runs as a system service with access to `/dev/uinput` — this is a system-level privilege required by the tool and is not introduced by hyprland-agent.

## Disclaimer

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND. It can issue real input events on your desktop. Use it responsibly and review the allowlist configuration before enabling it on sensitive workstations.
