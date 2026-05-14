"""Main agent loop — ties brain, tools, events, and safety together."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from agent.brain.base import Brain
from agent.safety import confirm, killswitch
from agent.safety.allowlist import is_allowed
from agent.schemas import Action, ActionKind, ScreenState
from agent.tools import hypr, input as inp, screen, terminal

if TYPE_CHECKING:
    from agent.daemon.run_executor import RunContext

log = logging.getLogger(__name__)

_TERMINAL_CLASSES = {"foot", "kitty", "alacritty", "wezterm", "ghostty"}
_CONTROL_PROCESS_MARKERS = {"codex", "claude", "agent"}


def _process_tree_contains(pid: int, markers: set[str]) -> bool:
    children: dict[int, list[int]] = {}
    candidates: dict[int, str] = {}
    proc_root = Path("/proc")

    for path in proc_root.iterdir():
        if not path.name.isdigit():
            continue
        current_pid = int(path.name)
        try:
            status = (path / "status").read_text(errors="ignore")
            cmdline = (path / "cmdline").read_text(errors="ignore").replace("\0", " ")
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        ppid = 0
        for line in status.splitlines():
            if line.startswith("PPid:"):
                ppid = int(line.split()[1])
                break
        children.setdefault(ppid, []).append(current_pid)
        candidates[current_pid] = f"{path.name} {status} {cmdline}".lower()

    stack = [pid]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        details = candidates.get(current, "")
        if any(marker in details for marker in markers):
            return True
        stack.extend(children.get(current, []))
    return False


async def _focused_control_terminal() -> dict | None:
    active = await hypr.active_window()
    if active is None:
        return None
    if active.app_class.lower() not in _TERMINAL_CLASSES:
        return None
    if not _process_tree_contains(active.pid, _CONTROL_PROCESS_MARKERS):
        return None
    return active.model_dump()


async def _ensure_keyboard_target_is_safe(ctx: "RunContext | None") -> bool:
    active = await _focused_control_terminal()
    if active is None:
        return True
    payload = {
        "reason": "control_terminal_keyboard_target",
        "active": active,
    }
    if ctx is not None:
        await ctx.emit("blocked", payload)
    log.warning("Refusing keyboard input into control terminal: %s", active)
    return False


async def _execute_action(action: Action, ctx: "RunContext | None") -> None:
    k = action.kind
    p = action.params

    if k == ActionKind.screenshot:
        return  # brain handles its own screenshotting

    if k == ActionKind.terminal_command:
        run_id = ctx.run_id if ctx is not None else "local"
        await terminal.run_command(
            p["command"],
            run_id=run_id,
            emit=ctx.emit if ctx else None,
            hold_s=float(p.get("hold_s", 0)),
        )
    elif k == ActionKind.type_text:
        if not await _ensure_keyboard_target_is_safe(ctx):
            return
        await inp.type_text(p["text"])
    elif k == ActionKind.key:
        if not await _ensure_keyboard_target_is_safe(ctx):
            return
        await inp.key(p["combo"])
    elif k == ActionKind.mouse_move:
        await inp.move(p["x"], p["y"])
    elif k == ActionKind.click:
        await inp.click(p.get("button", "left"))
    elif k == ActionKind.scroll:
        await inp.scroll(p["amount"], p.get("horizontal", False))
    elif k == ActionKind.focus_window:
        await hypr.dispatch(f"focuswindow address:{p['address']}")
    elif k == ActionKind.dispatch:
        cmd = p["cmd"]
        if confirm.is_destructive_dispatch(cmd):
            ok = await confirm.confirm(f"Hyprland dispatch: {cmd!r}")
            if not ok:
                log.warning("User rejected dispatch %r", cmd)
                return
        await hypr.dispatch(cmd)
    elif k == ActionKind.clipboard_copy:
        from agent.tools import clipboard

        await clipboard.write(p["text"])
    elif k == ActionKind.clipboard_paste:
        if not await _ensure_keyboard_target_is_safe(ctx):
            return
        await inp.key("ctrl+v")


async def _build_state(task: str, ctx: "RunContext | None") -> tuple[ScreenState, bool]:
    killswitch.ensure_disarmed()
    log.info("Starting task: %s", task)

    async def _emit(kind: str, payload: dict | None = None) -> None:
        if ctx is not None:
            await ctx.emit(kind, payload or {})

    await _emit("start", {"task": task})

    active = await hypr.active_window()
    if active and not is_allowed(active):
        log.warning(
            "Active window %r (%s) not in allowlist — refusing",
            active.title,
            active.app_class,
        )
        await _emit(
            "blocked",
            {
                "reason": "window_not_allowlisted",
                "active": active.model_dump(),
            },
        )
        print(
            f"[BLOCKED] Window '{active.title}' ({active.app_class}) is not in the allowlist."
        )
        print("Edit ~/.config/hyprland-agent/allowlist.yaml to add it.")
        return (
            ScreenState(
                screenshot_png=b"",
                width=0,
                height=0,
                active_window=active,
                windows=[],
            ),
            False,
        )

    png = await screen.full()
    mon = await hypr.active_monitor()
    width = mon.width if mon else 1920
    height = mon.height if mon else 1080
    wins = await hypr.clients()

    state = ScreenState(
        screenshot_png=png,
        width=width,
        height=height,
        active_window=active,
        windows=wins,
    )

    await _emit("state", {"active": active.model_dump() if active else None})
    return state, True


async def plan(task: str, brain: Brain, ctx: "RunContext | None" = None) -> None:
    """Plan a task and record the proposed actions without executing them."""

    async def _emit(kind: str, payload: dict | None = None) -> None:
        if ctx is not None:
            await ctx.emit(kind, payload or {})

    state, allowed = await _build_state(task, ctx)
    if not allowed:
        return

    actions = await brain.decide(state, task)
    await _emit("actions", {"count": len(actions)})

    for action in actions:
        await _emit("action", {"kind": action.kind.value, "params": action.params})

    await _emit("done", {})
    log.info("Plan complete.")


async def run(task: str, brain: Brain, ctx: "RunContext | None" = None) -> None:
    """Execute a task. If *ctx* is provided, lifecycle events are emitted via it."""

    async def _emit(kind: str, payload: dict | None = None) -> None:
        if ctx is not None:
            await ctx.emit(kind, payload or {})

    state, allowed = await _build_state(task, ctx)
    if not allowed:
        return

    actions = await brain.decide(state, task)
    await _emit("actions", {"count": len(actions)})

    for action in actions:
        if killswitch.is_stopped():
            log.warning("Kill switch triggered — stopping")
            await _emit("killswitch", {})
            print("[STOPPED] Kill switch detected.")
            return
        log.info("Execute: %s %s", action.kind, action.params)
        await _emit("action", {"kind": action.kind.value, "params": action.params})
        await _execute_action(action, ctx)
        await asyncio.sleep(0.05)

    await _emit("done", {})
    log.info("Task complete.")
