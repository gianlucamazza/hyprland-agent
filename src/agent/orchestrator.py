"""Main agent loop — ties brain, tools, events, and safety together."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from agent.awareness.meta_cognition import LoopDetector, PostActionVerifier, StuckError
from agent.awareness.working import WorkingMemory
from agent.awareness.world_context import snapshot as _world_snapshot
from agent.brain.base import Brain
from agent.brain.context import BrainContext
from agent.introspection.self_model import SelfModel
from agent.safety import confirm, killswitch
from agent.safety.allowlist import is_allowed
from agent.schemas import Action, ActionKind, ActionResult, ScreenState
from agent.tools import hypr, screen, terminal
from agent.tools import input as inp

if TYPE_CHECKING:
    from agent.daemon.run_executor import RunContext
    from agent.daemon.state import AppState

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


async def _ensure_keyboard_target_is_safe(ctx: RunContext | None) -> bool:
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


async def _execute_action(
    action: Action,
    ctx: RunContext | None,
    app_state: AppState | None = None,
) -> ActionResult:
    k = action.kind
    p = action.params
    base = ActionResult(kind=k.value)

    if k == ActionKind.screenshot:
        return base  # brain handles its own screenshotting

    if k == ActionKind.terminal_command:
        run_id = ctx.run_id if ctx is not None else "local"
        visible = bool(p.get("visible", True))
        code, stdout, stderr = await terminal.run_command(
            p["command"],
            run_id=run_id,
            emit=ctx.emit if ctx else None,
            hold_s=float(p.get("hold_s", 0)),
            visible=visible,
        )
        return ActionResult(
            kind=k.value,
            returncode=code,
            stdout=stdout or None,
            stderr=stderr or None,
        )

    if k == ActionKind.type_text:
        if not await _ensure_keyboard_target_is_safe(ctx):
            return ActionResult(kind=k.value, blocked="control_terminal")
        await inp.type_text(p["text"])
        return base

    if k == ActionKind.key:
        if not await _ensure_keyboard_target_is_safe(ctx):
            return ActionResult(kind=k.value, blocked="control_terminal")
        await inp.key(p["combo"])
        return base

    if k == ActionKind.mouse_move:
        await inp.move(p["x"], p["y"])
        return base

    if k == ActionKind.click:
        await inp.click(p.get("button", "left"))
        return base

    if k == ActionKind.scroll:
        await inp.scroll(p["amount"], p.get("horizontal", False))
        return base

    if k == ActionKind.focus_window:
        response = await hypr.dispatch(f"focuswindow address:{p['address']}")
        return ActionResult(kind=k.value, dispatch_response=response)

    if k == ActionKind.dispatch:
        cmd = p["cmd"]
        if confirm.is_destructive_dispatch(cmd):
            ok = await confirm.confirm(f"Hyprland dispatch: {cmd!r}")
            if not ok:
                log.warning("User rejected dispatch %r", cmd)
                return ActionResult(kind=k.value, rejected=cmd)
        response = await hypr.dispatch(cmd)
        return ActionResult(kind=k.value, dispatch_response=response)

    if k in (ActionKind.notify, ActionKind.update_status):
        if app_state is not None:
            result = await app_state.integrations.handle(action)
            if result is not None:
                return result
        return base

    return base


async def _build_state(task: str, ctx: RunContext | None) -> tuple[ScreenState, bool]:
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
        print(f"[BLOCKED] Window '{active.title}' ({active.app_class}) is not in the allowlist.")
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


async def _assemble_brain_context(
    screen_state: ScreenState,
    brain: Brain,
    task: str,
    app_state: AppState | None = None,
) -> BrainContext:
    brain_name = type(brain).__name__
    self_model = SelfModel(brain_name=brain_name)
    world = await _world_snapshot(
        active_window=screen_state.active_window,
        monitor_width=screen_state.width,
        monitor_height=screen_state.height,
        windows=screen_state.windows,
    )
    if app_state is not None:
        world.integrations = app_state.integrations.status()
        from agent.learning.api import inject_context

        return await inject_context(app_state, task, self_model, world)
    return BrainContext(self_model=self_model, world=world, working=WorkingMemory())


async def plan(
    task: str,
    brain: Brain,
    ctx: RunContext | None = None,
    app_state: AppState | None = None,
) -> None:
    """Plan a task and record the proposed actions without executing them."""

    async def _emit(kind: str, payload: dict | None = None) -> None:
        if ctx is not None:
            await ctx.emit(kind, payload or {})

    state, allowed = await _build_state(task, ctx)
    if not allowed:
        return

    brain_ctx = await _assemble_brain_context(state, brain, task, app_state)
    actions = await brain.decide(state, task, brain_ctx)
    await _emit("actions", {"count": len(actions)})

    for action in actions:
        await _emit("action", {"kind": action.kind.value, "params": action.params})

    await _emit("done", {})
    log.info("Plan complete.")


async def run(
    task: str,
    brain: Brain,
    ctx: RunContext | None = None,
    app_state: AppState | None = None,
) -> None:
    """Execute a task. If *ctx* is provided, lifecycle events are emitted via it."""

    async def _emit(kind: str, payload: dict | None = None) -> None:
        if ctx is not None:
            await ctx.emit(kind, payload or {})

    state, allowed = await _build_state(task, ctx)
    if not allowed:
        return

    brain_ctx = await _assemble_brain_context(state, brain, task, app_state)
    actions = await brain.decide(state, task, brain_ctx)
    await _emit("actions", {"count": len(actions)})

    loop_detector = LoopDetector()
    verifier = PostActionVerifier()

    for action in actions:
        if killswitch.is_stopped():
            log.warning("Kill switch triggered — stopping")
            await _emit("killswitch", {})
            print("[STOPPED] Kill switch detected.")
            return
        log.info("Execute: %s %s", action.kind, action.params)
        await _emit("action", {"kind": action.kind.value, "params": action.params})

        pre_hash: str | None = None
        if verifier.needs(action.kind):
            try:
                pre_hash = verifier.phash(state.screenshot_png)
            except Exception as exc:
                log.debug("pre-hash capture failed: %s", exc)

        result = await _execute_action(action, ctx, app_state)

        if pre_hash is not None:
            try:
                post_png = await screen.full()
                post_hash = verifier.phash(post_png)
                result = verifier.annotate(result, pre_hash, post_hash)
            except Exception as exc:
                log.debug("post-hash capture failed: %s", exc)

        brain_ctx.working.record(action.kind.value, action.params)

        if (
            result.dispatch_response
            or result.blocked
            or result.rejected
            or result.stdout
            or result.stderr
            or result.pre_hash
        ):
            result_data = {k: v for k, v in result.model_dump().items() if v is not None}
            await _emit("action_result", result_data)

        if loop_detector.observe(action):
            log.warning("Stuck detected — aborting")
            await _emit("stuck", {"action": action.model_dump()})
            raise StuckError(f"Stuck repeating action: {action.kind.value}")

        await asyncio.sleep(0.05)

    await _emit("done", {})
    log.info("Task complete.")
