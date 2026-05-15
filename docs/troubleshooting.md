# Troubleshooting

## Daemon doesn't start

**Symptom**: `agent service start` exits immediately or `agent status` says "not running".

1. **`HYPRLAND_INSTANCE_SIGNATURE` not set** — the daemon requires an active Hyprland session.
   Run from a terminal inside Hyprland, not via SSH or a non-graphical session.
   ```bash
   echo $HYPRLAND_INSTANCE_SIGNATURE   # must be non-empty
   ```

2. **Socket permission error** — stale socket from a crashed daemon:
   ```bash
   ls -la "$XDG_RUNTIME_DIR/hyprland-agent.sock"
   rm -f "$XDG_RUNTIME_DIR/hyprland-agent.sock"
   agent service start -v
   ```

3. **Systemd unit fails** — check logs:
   ```bash
   systemctl --user status hyprland-agent.service
   journalctl --user -u hyprland-agent.service -n 50
   ```

---

## ydotool permission denied

**Symptom**: mouse/keyboard actions fail with "permission denied" or `/dev/uinput` errors.

1. **Not in `input` group**:
   ```bash
   groups | grep input   # must show "input"
   sudo usermod -aG input $USER
   # Then re-login (or use: newgrp input in the current shell)
   ```

2. **udev rule missing** (non-Arch distros):
   ```bash
   echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | \
       sudo tee /etc/udev/rules.d/80-uinput.rules
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```

3. **ydotoold not running**:
   ```bash
   systemctl --user enable --now ydotool.service
   agent doctor   # shows ydotoold status
   ```

---

## Embedding download slow or fails

**Symptom**: first `agent run` hangs at "downloading model" or fails with a network error.

The agent downloads `intfloat/multilingual-e5-large` (~1.3 GB) from Hugging Face on first use.

- **Slow network**: the download uses `fastembed`'s cache at `~/.cache/fastembed`. It resumes if interrupted.
- **No internet**: disable episodic memory until you're online:
  ```yaml
  # ~/.config/hyprland-agent/config.yaml
  memory:
    enabled: false
  ```
- **Corporate proxy**: set `HF_HUB_OFFLINE=1` and pre-download the model on a connected machine,
  then copy `~/.cache/fastembed` to the target machine.

---

## Hyprland IPC not available

**Symptom**: `agent hypr windows` or event watching fails.

The daemon connects to Hyprland's native Unix sockets using `$HYPRLAND_INSTANCE_SIGNATURE`.
If the variable is set but sockets are missing:
```bash
ls "$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/"
# Should show: .socket.sock  .socket2.sock
```
If the directory is empty, restart Hyprland.

---

## Provider key not recognised

**Symptom**: `agent doctor` shows a provider key as WARN/FAIL even though you set it.

Provider keys are read **only by the daemon process** at start-up. If you added a key after the
daemon started:
```bash
systemctl --user restart hyprland-agent.service
# or
agent service stop && agent service start
```

Keys must be in `~/.config/hyprland-agent/env` (loaded via `EnvironmentFile` in the systemd unit)
**or** exported in the same shell where the daemon is running. The CLI does not read them.

---

## Killswitch stuck / agent won't stop

**Symptom**: `agent stop` doesn't work; the daemon keeps running.

1. **Check for stale STOP file**:
   ```bash
   ls ~/.cache/hyprland-agent/STOP
   rm -f ~/.cache/hyprland-agent/STOP
   ```
   The STOP file is consumed once detected. If left from a previous session it blocks the next run.

2. **Force stop the daemon**:
   ```bash
   systemctl --user stop hyprland-agent.service
   # or find and kill the process:
   pkill -f "agent service start"
   ```

3. **Verify with doctor**:
   ```bash
   agent doctor   # daemon socket should show "not running"
   ```

---

## `agent doctor` shows everything red

Run with verbose output to see detailed errors:
```bash
agent service start -v   # in one terminal
agent doctor             # in another
```

Common causes:
- Hyprland not running (required at startup)
- `wtype` / `grim` / `wl-clipboard` packages missing
- No provider credentials configured
