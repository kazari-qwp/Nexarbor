"""运行编排器（修订）：串起讨论、执行、整合与验收。

本模块只保存编排状态，并把每一步交给已有下游组件。下游模块编号可配置，
默认兼容旧装配：
* discussion.session：讨论会话；
* collab.board：协作板与任务执行；
* git.integrator：成果整合、成员提交、验收与发布。

它不生成代码、不认领任务，也不重新解释下游协议。
"""

import asyncio
import copy
import time
import uuid

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

ACTIVE_STATUSES = ("discussing", "executing", "reviewing")
MAX_RUNS = 20
MAX_ERRORS = 20
MAX_TASKS = 20
DEFAULT_REVIEW_CHANNELS = ["collaboration.review"]
DEFAULT_SUBMIT_CHANNELS = ["collaboration"]
DEFAULT_ACCEPT_CHANNELS = ["collaboration"]
DEFAULT_REOPEN_REASON = "成员否决后重开验收"
DEFAULT_DISCUSSION_MODULE = "discussion.session.rev_697d80a33d"
DEFAULT_BOARD_MODULE = "collab.board.rev_9191e2380f.rev_96569f0263"
DEFAULT_INTEGRATOR_MODULE = "git.integrator.rev_2863bbe53e.rev_c376775a7e"


class _Fail(Exception):
    """当前操作无法继续；在锁外转成中文错误结果。"""


_INSTANCE_LOCKS = {}


def _instance_lock(ctx):
    """同一模块实例的写操作串行化；状态仍只保存在实例里。"""
    loop = asyncio.get_running_loop()
    key = (id(ctx), id(loop))
    lock = _INSTANCE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _INSTANCE_LOCKS[key] = lock
    return lock


def _plain(value):
    return copy.deepcopy(thaw(value))


def _state(ctx):
    state = ctx.state
    if "run" not in state:
        state["run"] = None
    if "runs" not in state:
        state["runs"] = []
    if "errors" not in state:
        state["errors"] = []
    return state


def _error(state, operation, message):
    entry = {
        "at": time.time(),
        "operation": operation,
        "message": str(message),
    }
    errors = list(state.get("errors") or [])
    errors.append(entry)
    state["errors"] = errors[-MAX_ERRORS:]


def _archive_run(state):
    """把当前运行写入历史；同一 id 只保留一份，最多 20 条。"""
    run = state.get("run")
    if not run:
        return
    snapshot = _plain(run)
    runs = [item for item in (state.get("runs") or [])
            if isinstance(item, dict) and item.get("id") != snapshot.get("id")]
    runs.append(snapshot)
    state["runs"] = runs[-MAX_RUNS:]


def _fail_result(ctx, operation, message):
    state = _state(ctx)
    _error(state, operation, message)
    return ComponentResult(status="error", error=str(message))


def _config_module(ctx, field, default):
    """下游模块编号：配置非空时用配置值，否则沿用旧装配的默认值。"""
    value = ctx.config.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return default


def _discussion_module(ctx):
    return _config_module(ctx, "discussion_module", DEFAULT_DISCUSSION_MODULE)


def _board_module(ctx):
    return _config_module(ctx, "board_module", DEFAULT_BOARD_MODULE)


def _integrator_module(ctx):
    return _config_module(ctx, "integrator_module", DEFAULT_INTEGRATOR_MODULE)


async def _downstream(ctx, field, module, operation, parameters, channels):
    """调用一个下游操作，返回统一结果；异常也变成错误封套。"""
    node = ctx.config.get(field)
    if not isinstance(node, str) or not node.strip():
        return {"status": "error", "error": f"未配置{field}，无法找到下游节点"}
    try:
        result = await ctx.network.call(
            node,
            module,
            operation,
            parameters,
            channels=list(channels),
        )
    except Exception as error:  # 权限、可达性、下游异常都原样报给调用者
        return {"status": "error", "error": str(error)}
    if not isinstance(result, dict):
        return {"status": "error", "error": "下游返回了无法识别的结果"}
    return result


def _ok_data(result, operation):
    if result.get("status") != "ok":
        message = result.get("error") or f"{operation} 失败"
        raise _Fail(f"{operation}失败：{message}")
    data = result.get("data")
    if not isinstance(data, dict):
        raise _Fail(f"{operation}返回结果缺少有效数据")
    return data


def _configured_channels(ctx, field, defaults):
    return list(ctx.filter_channels(field, defaults))


def _review_channels(ctx):
    return _configured_channels(ctx, "review_channel", DEFAULT_REVIEW_CHANNELS)




def _accept_channels(ctx):
    return _configured_channels(ctx, "accept_channel", DEFAULT_ACCEPT_CHANNELS)


async def _safe_target(ctx, operation, field, module, call_operation,
                       parameters, channels):
    result = await _downstream(
        ctx, field, module, call_operation, parameters, channels
    )
    if result.get("status") != "ok":
        message = result.get("error") or f"{call_operation} 失败"
        _error(_state(ctx), operation, message)
        return {"status": "error", "error": message}
    return result.get("data")


async def _start(ctx, params):
    task = params.get("task")
    rounds = params.get("rounds")
    key = params.get("key")
    state = _state(ctx)
    run = state.get("run")
    if isinstance(run, dict) and run.get("status") in ACTIVE_STATUSES:
        if key is not None and run.get("key") == key:
            return ComponentResult(data={"run": _plain(run), "duplicate": True})
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
        ctx,
        "discussion_node",
        _discussion_module(ctx),
        "start",
        discussion_parameters,
        ["discussion"],
    )
    data = _ok_data(result, "启动讨论会话")
    # 讨论会话 0.1.0 实际返回 data.run；优先使用旧返回的 data.session_id。
    discussion_run = data.get("session_id")
    if not isinstance(discussion_run, str) or not discussion_run.strip():
        discussion_run = data.get("run")
    if not isinstance(discussion_run, str) or not discussion_run.strip():
        raise _Fail("启动讨论会话失败：讨论节点没有返回 session_id 或 run")

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
    return ComponentResult(data={"run": _plain(new_run), "duplicate": False})


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _task_paths(value):
    if not isinstance(value, (list, tuple)):
        return []
    return [str(path) for path in value if isinstance(path, str) and path.strip()]


def _normalize_task(item, artifact, run, index):
    """把讨论成果中的任务映射成协作板接受的 {title, paths, detail}。"""
    plain = _plain(item) if isinstance(item, dict) else {}
    title = _text(plain.get("title"))
    if not title:
        title = _text(artifact.get("title")) or _text(run.get("task")) or f"任务 {index}"
    # 同时存在 detail 与 description 时优先 detail；只有 description 时转成 detail。
    detail = _text(plain.get("detail")) or _text(plain.get("description"))
    if not detail:
        detail = title
    return {
        "title": title[:120],
        "paths": _task_paths(plain.get("paths")),
        "detail": detail[:2000],
    }


def _raw_tasks(value):
    return list(value) if isinstance(value, (list, tuple)) else []


def _normalize_tasks(artifact, decision, run):
    """按下游真实接口选择任务来源。

    discussion.session 0.1.0 的 status.artifact 只有 run/title/at，
    任务列表实际落在 status.decision.tasks，因此顺序为：
    1) artifact.tasks 非空数组；2) decision.tasks；3) 用成果标题生成一个回退任务。
    """
    raw_tasks = _raw_tasks(artifact.get("tasks"))
    if not raw_tasks:
        raw_tasks = _raw_tasks(decision.get("tasks"))
    tasks = []
    for index, item in enumerate(raw_tasks[:MAX_TASKS], start=1):
        if isinstance(item, dict):
            tasks.append(_normalize_task(item, artifact, run, index))
    if not tasks:
        title = _text(artifact.get("title")) or _text(run.get("task")) or "讨论成果"
        summary = _text(artifact.get("summary")) or _text(artifact.get("body"))
        tasks = [{
            "title": title[:120],
            "paths": [],
            "detail": (summary or title)[:2000],
        }]
    return tasks


async def _handoff(ctx):
    state = _state(ctx)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") != "discussing":
        raise _Fail("当前没有处于讨论阶段的运行，不能交接")

    result = await _downstream(
        ctx,
        "discussion_node",
        _discussion_module(ctx),
        "status",
        {},
        ["discussion"],
    )
    data = _ok_data(result, "读取讨论会话状态")
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
    board_result = await _downstream(
        ctx,
        "board_node",
        _board_module(ctx),
        "open",
        {"tasks": tasks},
        ["collaboration"],
    )
    board_data = _ok_data(board_result, "打开协作板")
    execution_run = board_data.get("execution_run_id")
    if not isinstance(execution_run, str) or not execution_run.strip():
        board_run = board_data.get("run")
        if isinstance(board_run, dict):
            execution_run = board_run.get("id")
    if not isinstance(execution_run, str) or not execution_run.strip():
        raise _Fail(
            "打开协作板失败：协作板没有返回执行批次编号"
            "（execution_run_id 或 run.id）"
        )

    run["execution_run"] = execution_run
    run["artifact_title"] = (
        _text(artifact.get("title")) or _text(run.get("task"))
    )
    run["status"] = "executing"
    return ComponentResult(data={
        "run": _plain(run),
        "execution_run": execution_run,
        "tasks": _plain(tasks),
    })


def _integrate_reason(params):
    """integrate 的可选 reason：缺省返回 None，非法值直接报错。"""
    reason = params.get("reason")
    if reason is None:
        return None
    if not isinstance(reason, str):
        raise _Fail("整合参数 reason 必须是字符串")
    if len(reason) > 500:
        raise _Fail("整合参数 reason 不能超过 500 个字符")
    return reason


async def _read_candidate(ctx):
    """读取整合器当前候选；用于验收阶段判断是否需要先重开。"""
    result = await _downstream(
        ctx,
        "integrator_node",
        _integrator_module(ctx),
        "read",
        {"include_history": False},
        ["collaboration"],
    )
    data = _ok_data(result, "读取整合器")
    candidate = data.get("candidate")
    return candidate if isinstance(candidate, dict) else None


def _candidate_label(candidate, run):
    candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        candidate_id = run.get("candidate")
    if isinstance(candidate_id, str) and candidate_id.strip():
        return candidate_id
    return "当前候选"


def _promotion_failed(candidate, run):
    raise _Fail(
        f"候选 {_candidate_label(candidate, run)} 已获全员认可，但推进整合分支失败"
        "（promotion_failed），不能再次整合，请改用 promote 重试"
    )


async def _reopen_candidate(ctx, candidate, reason):
    """用验收频道重开被否决的候选，保留同一候选编号。"""
    arguments = {"reason": reason}
    candidate_id = candidate.get("id")
    if isinstance(candidate_id, str) and candidate_id.strip():
        arguments["candidate_id"] = candidate_id
    result = await _downstream(
        ctx,
        "integrator_node",
        _integrator_module(ctx),
        "reopen",
        arguments,
        _accept_channels(ctx),
    )
    return _ok_data(result, "重开验收")


async def _integrate(ctx, params):
    state = _state(ctx)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") not in (
        "executing", "reviewing",
    ):
        raise _Fail("当前没有处于执行或验收阶段的运行，不能整合")
    reason = _integrate_reason(params)

    if run.get("status") == "reviewing":
        # 验收阶段再次整合：先看当前候选，否决的先重开，推进失败的不重复整合。
        current = await _read_candidate(ctx)
        status = current.get("status") if isinstance(current, dict) else None
        if status == "promotion_failed":
            _promotion_failed(current, run)
        if status == "vetoed":
            await _reopen_candidate(
                ctx, current, reason if reason else DEFAULT_REOPEN_REASON
            )

    result = await _downstream(
        ctx,
        "integrator_node",
        _integrator_module(ctx),
        "integrate",
        {},
        ["collaboration"],
    )
    data = _ok_data(result, "整合成果")
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
    channels = _review_channels(ctx)
    try:
        ctx.network.emit(
            timeout_seconds=ctx.config.get("activity_timeout_seconds", 86400),
            node_timeout_seconds=ctx.config.get("activity_timeout_seconds", 86400),
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
    return ComponentResult(data=payload)


async def _promote(ctx):
    state = _state(ctx)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") != "reviewing":
        raise _Fail("当前没有处于验收阶段的运行，不能发布")
    candidate_id = run.get("candidate")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise _Fail("当前运行没有待发布的候选")

    result = await _downstream(
        ctx,
        "integrator_node",
        _integrator_module(ctx),
        "promote",
        {"candidate_id": candidate_id},
        ["collaboration"],
    )
    data = _ok_data(result, "发布候选")
    candidate = data.get("candidate")
    if not isinstance(candidate, dict):
        candidate = {"id": candidate_id}

    run["status"] = "completed"
    run["ended_at"] = time.time()
    _archive_run(state)
    return ComponentResult(data={
        "run": _plain(run),
        "candidate": _plain(candidate),
    })


async def _status(ctx):
    summary = {}
    summary["discussion"] = await _safe_target(
        ctx, "status", "discussion_node",
        _discussion_module(ctx), "status", {}, ["discussion"]
    )
    summary["board"] = await _safe_target(
        ctx, "status", "board_node",
        _board_module(ctx), "status", {}, ["collaboration"]
    )
    summary["integration"] = await _safe_target(
        ctx, "status", "integrator_node",
        _integrator_module(ctx), "read", {"include_history": False}, ["collaboration"]
    )
    run = _state(ctx).get("run")
    return ComponentResult(data={
        "run": _plain(run) if isinstance(run, dict) else None,
        **summary,
        "errors": _plain(_state(ctx).get("errors") or []),
    })


async def _stop(ctx, params):
    state = _state(ctx)
    run = state.get("run")
    if not isinstance(run, dict) or run.get("status") not in ACTIVE_STATUSES:
        raise _Fail("当前没有进行中的运行，无法停止")

    reason = params.get("reason")
    result = {"discussion": None, "board": None}
    if run.get("status") == "discussing":
        down = await _downstream(
            ctx, "discussion_node", _discussion_module(ctx), "stop",
            ({"reason": reason} if reason else {}),
            ["discussion"],
        )
        if down.get("status") != "ok":
            _error(state, "stop", down.get("error") or "停止讨论会话失败")
        result["discussion"] = down
    elif run.get("status") == "executing":
        down = await _downstream(
            ctx, "board_node", _board_module(ctx), "close", {},
            ["collaboration"],
        )
        if down.get("status") != "ok":
            _error(state, "stop", down.get("error") or "关闭协作板失败")
        result["board"] = down

    run["status"] = "stopped"
    run["ended_at"] = time.time()
    _archive_run(state)
    return ComponentResult(data={
        "run": _plain(run),
        "reason": reason,
        "discussion": result["discussion"],
        "board": result["board"],
    })










async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="运行编排器只处理访问请求")
    operation = activation.operation
    params = activation.parameters

    handlers = {
        "start": lambda: _start(ctx, params),
        "handoff": lambda: _handoff(ctx),
        "integrate": lambda: _integrate(ctx, params),
        "promote": lambda: _promote(ctx),
        "status": lambda: _status(ctx),
        "stop": lambda: _stop(ctx, params),
    }
    handler = handlers.get(operation)
    if handler is None:
        return ComponentResult(status="error", error="不支持的请求")

    if operation in ("status", "read"):
        try:
            return await handler()
        except _Fail as error:
            return _fail_result(ctx, operation, error)
        except Exception as error:
            return _fail_result(ctx, operation, f"操作失败：{error}")

    try:
        async with _instance_lock(ctx):
            return await handler()
    except _Fail as error:
        return _fail_result(ctx, operation, error)
    except Exception as error:
        return _fail_result(ctx, operation, f"操作失败：{error}")
