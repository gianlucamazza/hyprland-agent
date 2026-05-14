"""RPC method dispatch — maps RpcMethod → handler coroutine."""

from __future__ import annotations

import logging
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent.daemon.state import AppState
from agent.ipc.protocol import RpcMethod, make_error_response, make_ok_response
from agent.ipc.protocol import ResponseFrame

log = logging.getLogger(__name__)

try:
    _APP_VERSION = version("hyprland-agent")
except PackageNotFoundError:
    _APP_VERSION = "0.0.0+local"

Handler = Any  # async def(state, params) -> dict


async def _run_task(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    task = params.get("task", "")
    brain = params.get("brain", "auto")
    dry_run = bool(params.get("dry_run", False))
    if not task:
        raise ValueError("task must be a non-empty string")
    run_id = await state.executor.submit(task, brain, dry_run)
    return {"run_id": run_id}


async def _cancel_run(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    run_id = params.get("run_id", "")
    ok = await state.executor.cancel(run_id)
    return {"ok": ok}


async def _list_runs(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    limit = int(params.get("limit", 50))
    runs = await state.store.list_runs(limit=limit)
    return {"runs": [r.model_dump() for r in runs]}


async def _get_run(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    run_id = params.get("run_id", "")
    record = await state.store.get_run(run_id)
    if record is None:
        raise KeyError(f"run {run_id!r} not found")
    return {"run": record.model_dump()}


async def _list_windows(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.tools import hypr

    wins = await hypr.clients()
    return {"windows": [w.model_dump() for w in wins]}


async def _screenshot(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    import tempfile

    from agent.tools import screen

    path = params.get("path") or tempfile.mktemp(suffix=".png", prefix="hashot-")
    png = await screen.full()
    import pathlib

    pathlib.Path(path).write_bytes(png)
    return {"path": path}


async def _reload_rules(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.daemon.watcher_service import load_rules

    state.rules = await load_rules()
    return {"rules_count": len(state.rules)}


async def _arm_killswitch(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.safety import killswitch

    killswitch.arm()
    return {"ok": True}


async def _disarm_killswitch(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.safety import killswitch

    killswitch.ensure_disarmed()
    return {"ok": True}


async def _daemon_status(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    active = await state.executor.active_run_ids()
    return {
        "version": _APP_VERSION,
        "uptime_s": time.time() - state.start_time,
        "active_runs": active,
        "rules_count": len(state.rules),
    }


_DISPATCH: dict[RpcMethod, Handler] = {
    RpcMethod.run_task: _run_task,
    RpcMethod.cancel_run: _cancel_run,
    RpcMethod.list_runs: _list_runs,
    RpcMethod.get_run: _get_run,
    RpcMethod.list_windows: _list_windows,
    RpcMethod.screenshot: _screenshot,
    RpcMethod.reload_rules: _reload_rules,
    RpcMethod.arm_killswitch: _arm_killswitch,
    RpcMethod.disarm_killswitch: _disarm_killswitch,
    RpcMethod.daemon_status: _daemon_status,
}


async def dispatch(
    state: AppState,
    request_id: str,
    method: RpcMethod,
    params: dict[str, Any],
) -> ResponseFrame:
    handler = _DISPATCH.get(method)
    if handler is None:
        return make_error_response(
            request_id, f"unknown method: {method}", code="not_implemented"
        )
    try:
        result = await handler(state, params)
        return make_ok_response(request_id, result)
    except KeyError as exc:
        return make_error_response(request_id, str(exc), code="not_found")
    except ValueError as exc:
        return make_error_response(request_id, str(exc), code="invalid_params")
    except Exception as exc:
        log.exception("RPC %s failed", method)
        return make_error_response(request_id, str(exc), code="internal_error")
