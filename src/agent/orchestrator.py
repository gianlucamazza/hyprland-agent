"""Main agent loop — ties brain, tools, events, and safety together."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from agent.brain.base import Brain
from agent.safety import confirm, killswitch
from agent.safety.allowlist import is_allowed
from agent.schemas import Action, ActionKind, ScreenState
from agent.tools import hypr, input as inp, screen

if TYPE_CHECKING:
    from agent.daemon.run_executor import RunContext

log = logging.getLogger(__name__)


async def _execute_action(action: Action, dry_run: bool) -> None:
    k = action.kind
    p = action.params

    if k == ActionKind.screenshot:
        return  # brain handles its own screenshotting
    if dry_run:
        log.info("[dry-run] %s %s", k, p)
        return

    if k == ActionKind.type_text:
        await inp.type_text(p["text"])
    elif k == ActionKind.key:
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
        await inp.key("ctrl+v")


async def run(
    task: str, brain: Brain, dry_run: bool = False, ctx: "RunContext | None" = None
) -> None:
    """Execute a task. If *ctx* is provided, lifecycle events are emitted via it."""
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
        return

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
        await _execute_action(action, dry_run=dry_run)
        await asyncio.sleep(0.05)

    await _emit("done", {})
    log.info("Task complete.")
