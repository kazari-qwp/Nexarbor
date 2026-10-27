"""协作板操作；认领与修改由所在节点事务串行提交。"""

from uuid import uuid4
from .state import (
    BoardError,
    COMMIT_RE,
    _caller,
    _config,
    _conflict_error,
    _conflicts,
    _copy,
    _event,
    _fingerprint,
    _new_tasks,
    _now,
    _open_duplicate,
    _overview,
    _require_control,
    _require_member,
    _require_running,
    _seen_lookup,
    _seen_remember,
    _state,
    _task_or_error,
)


async def _open(module, node, parameters):
    parameters = parameters
    specs = _copy(parameters["tasks"])
    fingerprint = _fingerprint({
        "run_id": parameters.get("run_id"),
        "tasks": specs,
    })
    key = parameters.get("key")
    duplicate = _open_duplicate(module, fingerprint, key)
    if duplicate is not None:
        return duplicate

    cfg = _config(module)
    members = await module.members()

    try:
        async with module.transaction([module._access_origin.info.node_id], timeout=20):
            duplicate = _open_duplicate(module, fingerprint, key)
            if duplicate is not None:
                return duplicate
            state = _state(module)
            tasks = _new_tasks(specs, cfg["max_tasks"])
            run_id = parameters.get("run_id") or ("run-" + uuid4().hex[:12])
            run = {
                "id": run_id,
                "status": "running",
                "task_count": len(tasks),
                "started_at": _now(),
                "ended_at": None,
            }
            state["run"] = run
            state["tasks"] = tasks
            state["shared"] = []
            state["members"] = members
            state["events"] = []
            state["seen"] = {}
            _event(module, "open", None, "开启协作轮次 %s，共 %d 项任务、%d 位成员" % (
                run_id, len(tasks), len(members)))
            result = {
                "run": _copy(run),
                "duplicate": False,
                "tasks": [_copy(task) for task in tasks.values()],
                "members": _copy(members),
            }
            _seen_remember(module, "open", key, fingerprint, result)
    except BoardError:
        raise
    except Exception as error:
        raise BoardError("开启协作轮次失败：%s" % (str(error) or "未知错误")) from error

    try:
        module.emit(node, access_strength=module.strength,
            timeout_seconds=module.config.get("activity_timeout_seconds", 86400),
            node_timeout_seconds=module.config.get("activity_timeout_seconds", 86400),
            channels=["collaboration.work"],
            strength=2,
            content={
                "run": run["id"],
                "phase": "working",
                "tasks": list(tasks.keys()),
            },
            kind="collaboration.work",
        )
    except Exception as error:
        # 状态已经提交；通知失败不应让调用者误以为 open 失败并重复创建。
        result["signal_error"] = str(error) or "工作信号发送失败"
    return result


def _list(module, parameters):
    parameters = parameters or {}
    include_closed = parameters.get("include_closed", True)
    state = _state(module)
    run = _copy(state["run"]) if state.get("run") else None
    if run and run.get("status") == "closed" and not include_closed:
        tasks = []
        shared = []
    else:
        tasks = [_copy(task) for task in state["tasks"].values()]
        shared = _copy(state["shared"])
    return {
        "run": run,
        "tasks": tasks,
        "members": _copy(state["members"]),
        "shared": shared,
        "overview": _overview(state["tasks"]),
    }


def _claim_locked(module, parameters):
    state = _state(module)
    member = _caller(module)
    task_id = parameters["task"]
    paths = list(parameters["paths"])
    key = parameters.get("key")
    fingerprint = _fingerprint({"task": task_id, "paths": paths})
    duplicate = _seen_lookup(module, "claim", key, fingerprint)
    if duplicate is not None:
        return duplicate

    run = _require_running(state)
    _require_member(state, member)
    task = _task_or_error(state, task_id)
    if task.get("status") == "completed":
        raise BoardError("任务“%s”已完成，不能再认领" % task_id)
    existing = next((claim for claim in task["claims"] if claim["member"] == member), None)
    if existing is not None:
        raise BoardError("你已认领任务“%s”，请用 extend 补充路径" % task_id)
    conflicts = _conflicts(state, task, paths, member)
    if conflicts:
        raise BoardError(_conflict_error(conflicts))

    now = _now()
    claim = {
        "member": member,
        "paths": paths,
        "claimed_at": now,
        "updated_at": now,
    }
    task["claims"].append(claim)
    task["status"] = "claimed"
    _event(module, "claim", member, "认领任务 %s：%s" % (task_id, "、".join(paths)))
    result = {
        "task": task_id,
        "member": member,
        "paths": list(paths),
        "claimed": True,
        "claim": _copy(claim),
        "duplicate": False,
    }
    _seen_remember(module, "claim", key, fingerprint, result)
    return result


def _extend_locked(module, parameters):
    state = _state(module)
    member = _caller(module)
    task_id = parameters["task"]
    paths = list(parameters["paths"])
    key = parameters.get("key")
    fingerprint = _fingerprint({"task": task_id, "paths": paths})
    duplicate = _seen_lookup(module, "extend", key, fingerprint)
    if duplicate is not None:
        return duplicate

    _require_running(state)
    _require_member(state, member)
    task = _task_or_error(state, task_id)
    if task.get("status") == "completed":
        raise BoardError("任务“%s”已完成，不能补充路径" % task_id)
    claim = next((item for item in task["claims"] if item["member"] == member), None)
    if claim is None:
        raise BoardError("你尚未认领任务“%s”，不能补充路径" % task_id)
    conflicts = _conflicts(state, task, paths, member)
    if conflicts:
        raise BoardError(_conflict_error(conflicts))

    for path in paths:
        if path not in claim["paths"]:
            claim["paths"].append(path)
    claim["updated_at"] = _now()
    task["status"] = "claimed"
    _event(module, "extend", member, "补充任务 %s 路径：%s" % (task_id, "、".join(paths)))
    result = {
        "task": task_id,
        "member": member,
        "paths": list(claim["paths"]),
        "added": list(paths),
        "duplicate": False,
    }
    _seen_remember(module, "extend", key, fingerprint, result)
    return result


def _complete_locked(module, parameters):
    state = _state(module)
    member = _caller(module)
    task_id = parameters["task"]
    commit = parameters["commit"]
    summary = parameters["summary"]
    key = parameters.get("key")
    if not COMMIT_RE.match(commit):
        raise BoardError("提交标识必须是 7 到 64 位十六进制字符")
    fingerprint = _fingerprint({"task": task_id, "commit": commit, "summary": summary})
    duplicate = _seen_lookup(module, "complete", key, fingerprint)
    if duplicate is not None:
        return duplicate

    _require_running(state)
    _require_member(state, member)
    task = _task_or_error(state, task_id)
    if task.get("status") == "completed":
        raise BoardError("任务“%s”已经完成" % task_id)
    claim = next((item for item in task["claims"] if item["member"] == member), None)
    if claim is None:
        raise BoardError("你尚未认领任务“%s”，不能标记完成" % task_id)

    task["status"] = "completed"
    task["commit"] = commit
    task["summary"] = summary
    task["completed_at"] = _now()
    _event(module, "complete", member, "完成任务 %s，提交 %s" % (task_id, commit))
    result = {
        "task": task_id,
        "status": "completed",
        "commit": commit,
        "summary": summary,
        "duplicate": False,
    }
    _seen_remember(module, "complete", key, fingerprint, result)
    return result


def _share(module, parameters, kind):
    parameters = parameters
    state = _state(module)
    member = _caller(module)
    fingerprint = _fingerprint({
        "kind": kind,
        "task": parameters.get("task"),
        "text": parameters["text"],
    })
    key = parameters.get("key")
    duplicate = _seen_lookup(module, kind, key, fingerprint)
    if duplicate is not None:
        return duplicate

    _require_running(state)
    _require_member(state, member)
    task_id = parameters.get("task")
    if task_id is not None:
        _task_or_error(state, task_id)
    limit = _config(module)["max_shared"]
    entry = {
        "kind": kind,
        "member": member,
        "task": task_id,
        "text": parameters["text"],
        "at": _now(),
    }
    state["shared"].append(entry)
    if len(state["shared"]) > limit:
        del state["shared"][:-limit]
    label = "发现" if kind == "discovery" else "失败与修改摘要"
    _event(module, kind, member, "共享%s%s" % (
        label, ("（任务 %s）" % task_id) if task_id else ""))
    result = {
        "kind": kind,
        "member": member,
        "task": task_id,
        "at": entry["at"],
        "duplicate": False,
    }
    _seen_remember(module, kind, key, fingerprint, result)
    return result


def _release_locked(module, parameters):
    parameters = parameters
    state = _state(module)
    task_id = parameters["task"]
    requested_member = parameters.get("member")
    caller = _caller(module)
    if requested_member is not None:
        _require_control(module, state)
        member = requested_member
    else:
        member = caller
    reason = parameters.get("reason") or "主动释放认领"

    _require_running(state)
    _require_member(state, member)
    task = _task_or_error(state, task_id)
    if task.get("status") == "completed":
        raise BoardError("任务“%s”已完成，不能释放认领" % task_id)
    claim = next((item for item in task["claims"] if item["member"] == member), None)
    if claim is None:
        raise BoardError("成员“%s”没有认领任务“%s”" % (member, task_id))
    paths = list(claim["paths"])
    task["claims"] = [item for item in task["claims"] if item["member"] != member]
    if not task["claims"] and task.get("status") == "claimed":
        task["status"] = "open"
    _event(module, "release", member, "释放任务 %s 的认领：%s；%s" % (
        task_id, "、".join(paths), reason))
    return {
        "task": task_id,
        "member": member,
        "released": True,
        "released_paths": paths,
        "reason": reason,
        "duplicate": False,
    }


def _leave_locked(module, parameters):
    parameters = parameters or {}
    state = _state(module)
    requested_member = parameters.get("member")
    caller = _caller(module)
    if requested_member is not None:
        _require_control(module, state)
        member = requested_member
    else:
        member = caller
    reason = parameters.get("reason") or "主动退出"

    _require_running(state)
    entry = _require_member(state, member, active=False)
    if entry.get("status") == "left":
        return {
            "member": member,
            "released_tasks": [],
            "released_paths": {},
            "duplicate": True,
        }

    released = []
    released_paths = {}
    for task_id, task in state["tasks"].items():
        if task.get("status") == "completed":
            continue
        claim = next((item for item in task["claims"] if item["member"] == member), None)
        if claim is None:
            continue
        released.append(task_id)
        released_paths[task_id] = list(claim["paths"])
        task["claims"] = [item for item in task["claims"] if item["member"] != member]
        if not task["claims"] and task.get("status") == "claimed":
            task["status"] = "open"
    entry["status"] = "left"
    entry["left_reason"] = reason
    _event(module, "leave", member, "成员退出；释放任务 %s；%s" % (
        "、".join(released) if released else "无", reason))
    return {
        "member": member,
        "released_tasks": released,
        "released_paths": released_paths,
        "duplicate": False,
    }


def _status(module, parameters):
    parameters = parameters or {}
    state = _state(module)
    result = {
        "run": _copy(state["run"]) if state.get("run") else None,
        "overview": _overview(state["tasks"]),
        "members": _copy(state["members"]),
        "shared": _copy(state["shared"]),
        "event_count": len(state["events"]),
    }
    result["events"] = _copy(state["events"][-20:]) if parameters.get("include_events", True) else []
    return result


def _close_locked(module, parameters):
    parameters = parameters or {}
    state = _state(module)
    run = state.get("run")
    if not run:
        raise BoardError("当前还没有协作轮次，无法结束")
    if run.get("status") == "closed":
        raise BoardError("当前协作轮次已经结束")
    run["status"] = "closed"
    run["ended_at"] = _now()
    summary = parameters.get("summary") or "轮次结束，保留全部任务、认领与共享记录"
    _event(module, "close", None, summary)
    return {"run": _copy(run), "closed": True}
