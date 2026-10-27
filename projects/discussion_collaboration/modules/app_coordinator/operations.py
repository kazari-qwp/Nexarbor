"""原讨论→执行→整合→验收编排；下游方法直接返回业务数据。"""

import time
import json
import uuid
from .state import (
    ACTIVE_STATUSES,
    DEFAULT_REOPEN_REASON,
    _Fail,
    _accept_channels,
    _archive_run,
    _board_module,
    _discussion_module,
    _error,
    _integrate_reason,
    _integrator_module,
    _normalize_tasks,
    _plain,
    _promotion_failed,
    _review_channels,
    _state,
    _text,
)

_LABELS = {
    ("discussion_node", "start"):"启动讨论会话",
    ("discussion_node", "status"):"读取讨论会话状态",
    ("board_node", "open"):"打开协作板",
    ("integrator_node", "read"):"读取整合器",
    ("integrator_node", "integrate"):"整合成果",
    ("integrator_node", "reopen"):"重开验收",
    ("integrator_node", "promote"):"发布候选",
}

async def _downstream(module, field, module_id, operation, parameters, channels):
    try:
        return await module.downstream(field, module_id, operation, parameters, channels)
    except Exception as error:
        raise _Fail(f"{_LABELS.get((field, operation), operation)}失败：{error}") from error


async def _safe_target(module, operation, field, module_id, call_operation, parameters, channels):
    try:
        return await module.downstream(field, module_id, call_operation, parameters, channels)
    except Exception as error:
        _error(_state(module), operation, str(error))
        return {"status":"error", "error":str(error)}


async def _stop_target(module, field, module_id, operation, parameters, channels):
    try:
        return {"status":"ok", "data":await module.downstream(field, module_id, operation, parameters, channels)}
    except Exception as error:
        _error(_state(module), "stop", str(error))
        return {"status":"error", "error":str(error)}

async def _start(module, params):
    task = params.get("task")
    rounds = params.get("rounds")
    key = params.get("key")
    state = _state(module)
    run = state.get("run")
    if isinstance(run, dict) and run.get("status") in ACTIVE_STATUSES:
        if key is not None and run.get("key") == key:
            return {"run": _plain(run), "duplicate": True}
        raise _Fail(
            f"已有进行中的运行（{run.get('id')}，状态 {run.get('status')}），"
            "请先结束或停止后再启动"
        )

    discussion_parameters = {"task": task}
    if rounds is not None:
        discussion_parameters["rounds"] = rounds
    if key is not None:
        discussion_parameters["key"] = key
    result = await _downstream(
        module,
        "discussion_node",
        _discussion_module(module),
        "start",
        discussion_parameters,
        ["discussion"],
    )
    data = result
    discussion_run = data["run"]

    _archive_run(state)
    new_run = {
        "id": "run-" + uuid.uuid4().hex[:16],
        "status": "discussing",
        "task": task,
        "discussion_run": discussion_run,
        "execution_run": None,
        "candidate": None,
        "artifact_title": "",
        "started_at": time.time(),
        "ended_at": None,
        "error": None,
        "key": key,
    }
    state["run"] = new_run
    return {"run": _plain(new_run), "duplicate": False}


async def _handoff(module):
    state = _state(module)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") != "discussing":
        raise _Fail("当前没有处于讨论阶段的运行，不能交接")

    result = await _downstream(
        module,
        "discussion_node",
        _discussion_module(module),
        "status",
        {},
        ["discussion"],
    )
    data = result
    discussion_status = data.get("status")
    if discussion_status != "completed":
        raise _Fail(
            f"讨论尚未完成（当前状态：{discussion_status or '未知'}），不能交接"
        )
    artifact = data.get("artifact")
    if not isinstance(artifact, dict):
        raise _Fail("讨论已结束但没有可交接的成果 artifact")
    decision = data.get("decision")
    if not isinstance(decision, dict):
        decision = {}

    tasks = _normalize_tasks(artifact, decision, run)
    if module.config.get("cooperative_module"):
        board_data = await _downstream(module, "board_node", module.config["cooperative_module"], "start",
                                       {"task": json.dumps(dict(task=run["task"], artifact=artifact, tasks=tasks), ensure_ascii=False)}, ["collaboration"])
        execution_run = board_data["run_id"]
    else:
        board_data = await _downstream(module, "board_node", _board_module(module), "open", {"tasks": tasks}, ["collaboration"])
        execution_run = board_data["run"]["id"]

    run["execution_run"] = execution_run
    run["artifact_title"] = (
        _text(artifact.get("title")) or _text(run.get("task"))
    )
    run["status"] = "executing"
    return {
        "run": _plain(run),
        "execution_run": execution_run,
        "tasks": _plain(tasks),
    }


async def _read_candidate(module):
    """读取整合器当前候选；用于验收阶段判断是否需要先重开。"""
    result = await _downstream(
        module,
        "integrator_node",
        _integrator_module(module),
        "read",
        {"include_history": False},
        ["collaboration"],
    )
    data = result
    candidate = data.get("candidate")
    return candidate if isinstance(candidate, dict) else None


async def _reopen_candidate(module, candidate, reason):
    """用验收频道重开被否决的候选，保留同一候选编号。"""
    arguments = {"reason": reason}
    candidate_id = candidate.get("id")
    if isinstance(candidate_id, str) and candidate_id.strip():
        arguments["candidate_id"] = candidate_id
    result = await _downstream(
        module,
        "integrator_node",
        _integrator_module(module),
        "reopen",
        arguments,
        _accept_channels(module),
    )
    return result


async def _integrate(module, node, params):
    state = _state(module)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") not in (
        "executing", "reviewing",
    ):
        raise _Fail("当前没有处于执行或验收阶段的运行，不能整合")
    reason = _integrate_reason(params)

    if run.get("status") == "reviewing":
        # 验收阶段再次整合：先看当前候选，否决的先重开，推进失败的不重复整合。
        current = await _read_candidate(module)
        status = current.get("status") if isinstance(current, dict) else None
        if status == "promotion_failed":
            _promotion_failed(current, run)
        if status == "vetoed":
            await _reopen_candidate(
                module, current, reason if reason else DEFAULT_REOPEN_REASON
            )

    result = await _downstream(
        module,
        "integrator_node",
        _integrator_module(module),
        "integrate",
        {},
        ["collaboration"],
    )
    data = result
    candidate = data.get("candidate")
    if not isinstance(candidate, dict):
        raise _Fail("整合失败：整合器没有返回候选")
    if candidate.get("status") == "promotion_failed":
        _promotion_failed(candidate, run)
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise _Fail("整合失败：整合器返回的候选缺少 id")

    run["candidate"] = candidate_id
    run["status"] = "reviewing"
    signal_error = None
    channels = _review_channels(module)
    try:
        module.emit(node, access_strength=module.strength,
            timeout_seconds=module.config.get("activity_timeout_seconds", 86400),
            node_timeout_seconds=module.config.get("activity_timeout_seconds", 86400),
            channels=channels,
            strength=2,
            content={"candidate": candidate_id, "run": _plain(run)},
        )
    except Exception as error:
        signal_error = str(error)
        _error(state, "integrate", f"候选已生成，但验收信号发送失败：{error}")
    payload = {
        "run": _plain(run),
        "candidate": _plain(candidate),
    }
    if signal_error is not None:
        payload["signal_error"] = signal_error
    return payload


async def _promote(module):
    state = _state(module)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") != "reviewing":
        raise _Fail("当前没有处于验收阶段的运行，不能发布")
    candidate_id = run.get("candidate")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise _Fail("当前运行没有待发布的候选")

    result = await _downstream(
        module,
        "integrator_node",
        _integrator_module(module),
        "promote",
        {"candidate_id": candidate_id},
        ["collaboration"],
    )
    data = result
    candidate = data.get("candidate")
    if not isinstance(candidate, dict):
        candidate = {"id": candidate_id}

    run["status"] = "completed"
    run["ended_at"] = time.time()
    _archive_run(state)
    return {
        "run": _plain(run),
        "candidate": _plain(candidate),
    }


async def _status(module):
    if module.config.get("cooperative_module"):
        cooperation = await _safe_target(module, "status", "board_node", module.config["cooperative_module"], "status", {}, ["collaboration"])
        discussion = await _safe_target(module, "status", "discussion_node", _discussion_module(module), "status", {}, ["discussion"])
        return {"run": _plain(_state(module).get("run")), "discussion": discussion, "cooperation": cooperation, "errors": _plain(module.state.get("errors", []))}
    summary = {}
    summary["discussion"] = await _safe_target(
        module, "status", "discussion_node",
        _discussion_module(module), "status", {}, ["discussion"]
    )
    summary["board"] = await _safe_target(
        module, "status", "board_node",
        _board_module(module), "status", {}, ["collaboration"]
    )
    summary["integration"] = await _safe_target(
        module, "status", "integrator_node",
        _integrator_module(module), "read", {"include_history": False}, ["collaboration"]
    )
    run = _state(module).get("run")
    return {
        "run": _plain(run) if isinstance(run, dict) else None,
        **summary,
        "errors": _plain(_state(module).get("errors") or []),
    }


async def _stop(module, params):
    state = _state(module)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") not in ACTIVE_STATUSES:
        raise _Fail("当前没有进行中的运行，无法停止")
    reason = params.get("reason")
    result = {"discussion":None, "board":None}
    if run.get("status") == "discussing":
        result["discussion"] = await _stop_target(module, "discussion_node", _discussion_module(module),
                                                  "stop", {"reason":reason} if reason else {}, ["discussion"])
    elif module.config.get("cooperative_module"):
        result["board"] = await _stop_target(module, "board_node", module.config["cooperative_module"], "stop", {"failure":reason}, ["collaboration"])
    elif run.get("status") == "executing":
        result["board"] = await _stop_target(module, "board_node", _board_module(module),
                                             "close", {}, ["collaboration"])
    run["status"] = "stopped"
    run["ended_at"] = time.time()
    _archive_run(state)
    return {"run":_plain(run), "reason":reason, **result}

