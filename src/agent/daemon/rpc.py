"""RPC method dispatch — maps RpcMethod → handler coroutine."""

from __future__ import annotations

import logging
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent.daemon.state import AppState
from agent.ipc.protocol import ResponseFrame, RpcMethod, make_error_response, make_ok_response

log = logging.getLogger(__name__)

try:
    _APP_VERSION = version("hyprland-agent")
except PackageNotFoundError:
    _APP_VERSION = "0.0.0+local"

Handler = Any  # async def(state, params) -> dict


async def _run_task(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    task = params.get("task", "")
    brain = params.get("brain", "auto")
    if not task:
        raise ValueError("task must be a non-empty string")
    run_id = await state.executor.submit(task, brain)
    return {"run_id": run_id}


async def _plan_task(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    task = params.get("task", "")
    brain = params.get("brain", "auto")
    if not task:
        raise ValueError("task must be a non-empty string")
    run_id = await state.executor.submit_plan(task, brain)
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


async def _record_feedback(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    run_id = params.get("run_id", "")
    kind = params.get("kind", "")
    comment = params.get("comment")
    if not run_id or not kind:
        raise ValueError("run_id and kind are required")
    feedback_id = await state.store.insert_feedback(run_id, kind, comment)
    from agent.learning.outcome import feedback_to_outcome

    outcome, score = feedback_to_outcome(kind)
    if outcome != "unknown":
        await state.store.upsert_run_outcome(run_id, outcome, score, "explicit", rationale=comment)
    return {"feedback_id": feedback_id, "outcome": outcome}


async def _runs_analytics(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    days = int(params.get("days", 7))
    return await state.store.list_analytics(days)


async def _learning_list(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.learning.api import list_proposals

    kind = params.get("kind", "skill")
    status = params.get("status") or None
    items = await list_proposals(kind, status, state.store)
    return {"items": items}


async def _learning_approve(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.learning.api import approve

    kind = params.get("kind", "")
    proposal_id = params.get("id", "")
    if not kind or not proposal_id:
        raise ValueError("kind and id are required")
    result = await approve(kind, str(proposal_id), state.store)
    if kind == "rule":
        from agent.daemon.watcher_service import load_rules

        state.rules = await load_rules()
    return result


async def _learning_reject(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.learning.api import reject

    kind = params.get("kind", "")
    proposal_id = params.get("id", "")
    reason = params.get("reason")
    if not kind or not proposal_id:
        raise ValueError("kind and id are required")
    return await reject(kind, str(proposal_id), state.store, reason=reason)


async def _learning_explain(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    from agent.learning.api import explain

    kind = params.get("kind", "")
    proposal_id = params.get("id", "")
    if not kind or not proposal_id:
        raise ValueError("kind and id are required")
    return await explain(kind, str(proposal_id), state.store)


async def _memory_search(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    query = params.get("query", "")
    top_k = int(params.get("top_k", 5))
    if not query:
        raise ValueError("query is required")
    episodes = await state.episodic.recall(query, k=top_k, filter_failure=False)
    return {
        "episodes": [
            {
                "id": ep.run_id,
                "task": ep.task,
                "outcome": ep.outcome,
                "summary": ep.summary,
                "context_class": ep.context_class,
                "score": 1.0 - (ep.distance or 0.0),
            }
            for ep in episodes
        ]
    }


async def _memory_get(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    episode_id = params.get("episode_id", "")
    if not episode_id:
        raise ValueError("episode_id is required")
    episode = await state.store.get_episode(episode_id)
    return {"episode": episode}


async def _daemon_status(state: AppState, params: dict[str, Any]) -> dict[str, Any]:
    active = await state.executor.active_run_ids()
    return {
        "version": _APP_VERSION,
        "uptime_s": time.time() - state.start_time,
        "active_runs": active,
        "rules_count": len(state.rules),
    }


_DISPATCH: dict[RpcMethod, Handler] = {
    RpcMethod.plan_task: _plan_task,
    RpcMethod.run_task: _run_task,
    RpcMethod.cancel_run: _cancel_run,
    RpcMethod.list_runs: _list_runs,
    RpcMethod.get_run: _get_run,
    RpcMethod.list_windows: _list_windows,
    RpcMethod.screenshot: _screenshot,
    RpcMethod.reload_rules: _reload_rules,
    RpcMethod.arm_killswitch: _arm_killswitch,
    RpcMethod.daemon_status: _daemon_status,
    RpcMethod.record_feedback: _record_feedback,
    RpcMethod.runs_analytics: _runs_analytics,
    RpcMethod.learning_list: _learning_list,
    RpcMethod.learning_approve: _learning_approve,
    RpcMethod.learning_reject: _learning_reject,
    RpcMethod.learning_explain: _learning_explain,
    RpcMethod.memory_search: _memory_search,
    RpcMethod.memory_get: _memory_get,
}


async def dispatch(
    state: AppState,
    request_id: str,
    method: RpcMethod,
    params: dict[str, Any],
) -> ResponseFrame:
    handler = _DISPATCH.get(method)
    if handler is None:
        return make_error_response(request_id, f"unknown method: {method}", code="not_implemented")
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
