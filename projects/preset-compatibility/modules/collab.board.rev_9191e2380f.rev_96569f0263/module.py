"""认领协作板：平等成员自主认领任务路径，共享进度，保留退出与结束后的记录。

职责边界：
* 只读写本节点状态，不执行 Git、不做验收、不调度 Agent；
* 成员由成员发现频道上的真实 Agent 节点组成；
* 认领检查与写入在同一节点事务锁内完成，冲突时状态完全不变；
* 成员退出可在锁释放后同步给同节点配置的整合器，失败不会改写板状态；
* 发现、失败、修改摘要和事件都有上限，避免状态无限增长。
"""

import json
import re
import time
from copy import deepcopy
from uuid import uuid4

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

DEFAULT_MEMBER_CHANNEL = ["collaboration"]
DEFAULT_INTEGRATOR_CHANNELS = ["collaboration"]
MAX_EVENTS = 200
MAX_SEEN = 1000
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


class BoardError(Exception):
    """可以安全返回给调用者的业务错误。"""


def _copy(value):
    """状态与参数是冻结 JSON；读取时取可变副本。"""
    return deepcopy(thaw(value))


def _now():
    return time.time()


def _state(ctx):
    state = ctx.state
    defaults = {
        "run": None,
        "tasks": {},
        "shared": [],
        "members": [],
        "events": [],
        "seen": {},
    }
    for key, value in defaults.items():
        if key not in state:
            state[key] = value
    return state


def _config(ctx):
    channels = ctx.filter_channels("member_channel", list(DEFAULT_MEMBER_CHANNEL))
    if not channels:
        raise BoardError("成员发现频道为空；请检查 member_channel 与 channel_modes")
    max_tasks = ctx.config.get("max_tasks", 100)
    if type(max_tasks) is not int or not 1 <= max_tasks <= 500:
        raise BoardError("配置 max_tasks 必须是 1 到 500 的整数")
    max_shared = ctx.config.get("max_shared", 500)
    if type(max_shared) is not int or not 10 <= max_shared <= 2000:
        raise BoardError("配置 max_shared 必须是 10 到 2000 的整数")
    return {
        "member_channel": list(channels),
        "max_tasks": max_tasks,
        "max_shared": max_shared,
    }


def _caller(ctx):
    value = getattr(ctx, "requester_id", None) or getattr(ctx, "caller_id", None)
    return value or ctx.node_id


def _control_allowed(ctx, state):
    """控制方是协作板所在节点，或不属于本轮成员的独立控制节点。

    核心访问激活不携带本次请求实际使用的频道；频道本身仍由操作声明的
    collab.claim／collab.admin 约束。这里再按成员身份阻止成员拿 member
    参数代他人操作，避免把 admin 频道误当成成员自助入口。
    """
    caller = _caller(ctx)
    if caller == ctx.node_id:
        return True
    entry = _member_entry(state, caller)
    return entry is None or entry.get("status") != "active"


def _require_control(ctx, state):
    if not _control_allowed(ctx, state):
        raise BoardError(
            "带 member 需要 collab.admin 频道并由控制方调用；"
            "成员请省略 member 操作自己的认领或退出"
        )


def _event(ctx, kind, member, text):
    events = _state(ctx)["events"]
    events.append({"at": _now(), "kind": kind, "member": member, "text": text})
    if len(events) > MAX_EVENTS:
        del events[:-MAX_EVENTS]


def _member_entry(state, member_id):
    return next((item for item in state["members"] if item.get("id") == member_id), None)


def _require_member(state, member_id, *, active=True):
    entry = _member_entry(state, member_id)
    if entry is None:
        raise BoardError("成员“%s”不在本轮协作中" % member_id)
    if active and entry.get("status") != "active":
        raise BoardError("成员“%s”已退出，不能继续操作" % member_id)
    return entry


def _require_running(state):
    run = state.get("run")
    if not run:
        raise BoardError("当前还没有协作轮次，请先 open")
    if run.get("status") != "running":
        raise BoardError("当前协作轮次已结束，不能继续修改进度")
    return run


def _task_or_error(state, task_id):
    task = state["tasks"].get(task_id)
    if task is None:
        raise BoardError("任务“%s”不存在" % task_id)
    return task


def _normalize_path(value):
    text = str(value).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    return text or "/"


def _overlap(left, right):
    a = _normalize_path(left)
    b = _normalize_path(right)
    if a == b:
        return True
    if a == "/" or b == "/":
        return True
    return a.startswith(b + "/") or b.startswith(a + "/")


def _conflicts(state, task, paths, member_id):
    found = []
    for claim in task.get("claims", []):
        claimed_member = claim.get("member")
        if claimed_member != member_id:
            entry = _member_entry(state, claimed_member)
            if entry is None or entry.get("status") != "active":
                continue
        for existing in claim.get("paths", []):
            for requested in paths:
                if _overlap(existing, requested):
                    found.append({
                        "member": claimed_member,
                        "path": existing,
                        "requested": requested,
                        "self": claimed_member == member_id,
                    })
    return found


def _conflict_error(conflicts):
    parts = []
    for item in conflicts:
        if item["self"]:
            parts.append("你已认领 %s（与 %s 重叠）" % (item["path"], item["requested"]))
        else:
            parts.append("成员 %s 已认领 %s（与 %s 重叠）" % (
                item["member"], item["path"], item["requested"]))
    return "路径冲突：" + "；".join(parts) + "。未修改认领状态"


def _seen_key(ctx, operation, key):
    if key is None:
        return None
    return json.dumps(
        [ctx.module_id, ctx.node_id, _caller(ctx), operation, key],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _seen_lookup(ctx, operation, key, fingerprint):
    if key is None:
        return None
    state = _state(ctx)
    record = state["seen"].get(_seen_key(ctx, operation, key))
    if record is None:
        return None
    if record.get("fingerprint") != fingerprint:
        raise BoardError("相同幂等键已用于不同参数的请求，已拒绝")
    result = _copy(record.get("result") or {})
    result["duplicate"] = True
    return result


def _seen_remember(ctx, operation, key, fingerprint, result):
    if key is None:
        return
    state = _state(ctx)
    internal = _seen_key(ctx, operation, key)
    state["seen"][internal] = {
        "fingerprint": fingerprint,
        "result": _copy(result),
        "at": _now(),
    }
    while len(state["seen"]) > MAX_SEEN:
        state["seen"].pop(next(iter(state["seen"])))


def _fingerprint(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _overview(tasks):
    values = list(tasks.values())
    return {
        "total": len(values),
        "unfinished": sum(1 for item in values if item.get("status") != "completed"),
        "completed": sum(1 for item in values if item.get("status") == "completed"),
        "open": sum(1 for item in values if item.get("status") == "open"),
        "claimed": sum(1 for item in values if item.get("status") == "claimed"),
    }


async def _discover_members(ctx, channels):
    try:
        nodes = await ctx.network.nodes(channels=list(channels))
    except Exception as error:
        raise BoardError("无法沿成员发现频道查找成员：%s" % (str(error) or "请求失败")) from error
    members = []
    seen = set()
    for node in nodes or []:
        metadata = node.metadata
        if not isinstance(metadata, dict):
            continue
        if metadata.get("node_type") != "agent":
            continue
        node_id = metadata.get("node_id")
        if not isinstance(node_id, str) or not node_id or node_id in seen:
            continue
        seen.add(node_id)
        name = metadata.get("name") or metadata.get("display_name") or node_id
        members.append({
            "id": node_id,
            "name": str(name),
            "status": "active",
            "left_reason": None,
        })
    if not members:
        raise BoardError(
            "没有发现可参与的 Agent 成员；请检查成员发现频道、节点类型和连接"
        )
    return members


def _new_tasks(specs, max_tasks):
    if len(specs) > max_tasks:
        raise BoardError("任务数量 %d 超过上限 %d" % (len(specs), max_tasks))
    given = {item.get("id") for item in specs if item.get("id") is not None}
    tasks = {}
    counter = 0
    for spec in specs:
        task_id = spec.get("id")
        if task_id is None:
            while True:
                counter += 1
                task_id = "task-%d" % counter
                if task_id not in given and task_id not in tasks:
                    break
        if task_id in tasks:
            raise BoardError("任务 ID“%s”重复" % task_id)
        tasks[task_id] = {
            "id": task_id,
            "title": spec["title"],
            "detail": spec.get("detail", ""),
            "paths": list(spec.get("paths", [])),
            "status": "open",
            "claims": [],
            "commit": None,
            "summary": None,
            "completed_at": None,
        }
    return tasks


def _open_duplicate(ctx, fingerprint, key):
    state = _state(ctx)
    run = state.get("run")
    if not run or run.get("status") != "running":
        return None
    stored = _seen_lookup(ctx, "open", key, fingerprint)
    if stored is not None and stored.get("run", {}).get("id") == run["id"]:
        return stored
    raise BoardError("已有正在进行的协作轮次；如需新轮次请先 close")


async def _open(ctx, activation):
    parameters = activation.parameters
    specs = _copy(parameters["tasks"])
    fingerprint = _fingerprint({
        "run_id": parameters.get("run_id"),
        "tasks": specs,
    })
    key = parameters.get("key")
    duplicate = _open_duplicate(ctx, fingerprint, key)
    if duplicate is not None:
        return duplicate

    cfg = _config(ctx)
    members = await _discover_members(ctx, cfg["member_channel"])

    try:
        async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
            duplicate = _open_duplicate(ctx, fingerprint, key)
            if duplicate is not None:
                return duplicate
            state = _state(ctx)
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
            _event(ctx, "open", None, "开启协作轮次 %s，共 %d 项任务、%d 位成员" % (
                run_id, len(tasks), len(members)))
            result = {
                "run": _copy(run),
                "duplicate": False,
                "tasks": [_copy(task) for task in tasks.values()],
                "members": _copy(members),
            }
            _seen_remember(ctx, "open", key, fingerprint, result)
    except BoardError:
        raise
    except Exception as error:
        raise BoardError("开启协作轮次失败：%s" % (str(error) or "未知错误")) from error

    try:
        await ctx.network.emit(
            timeout_seconds=ctx.config.get("activity_timeout_seconds", 86400),
            node_timeout_seconds=ctx.config.get("activity_timeout_seconds", 86400),
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


def _list(ctx, activation):
    parameters = activation.parameters or {}
    include_closed = parameters.get("include_closed", True)
    state = _state(ctx)
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


def _claim_locked(ctx, parameters):
    state = _state(ctx)
    member = _caller(ctx)
    task_id = parameters["task"]
    paths = list(parameters["paths"])
    key = parameters.get("key")
    fingerprint = _fingerprint({"task": task_id, "paths": paths})
    duplicate = _seen_lookup(ctx, "claim", key, fingerprint)
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
    _event(ctx, "claim", member, "认领任务 %s：%s" % (task_id, "、".join(paths)))
    result = {
        "task": task_id,
        "member": member,
        "paths": list(paths),
        "claimed": True,
        "claim": _copy(claim),
        "duplicate": False,
    }
    _seen_remember(ctx, "claim", key, fingerprint, result)
    return result


def _extend_locked(ctx, parameters):
    state = _state(ctx)
    member = _caller(ctx)
    task_id = parameters["task"]
    paths = list(parameters["paths"])
    key = parameters.get("key")
    fingerprint = _fingerprint({"task": task_id, "paths": paths})
    duplicate = _seen_lookup(ctx, "extend", key, fingerprint)
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
    _event(ctx, "extend", member, "补充任务 %s 路径：%s" % (task_id, "、".join(paths)))
    result = {
        "task": task_id,
        "member": member,
        "paths": list(claim["paths"]),
        "added": list(paths),
        "duplicate": False,
    }
    _seen_remember(ctx, "extend", key, fingerprint, result)
    return result


def _complete_locked(ctx, parameters):
    state = _state(ctx)
    member = _caller(ctx)
    task_id = parameters["task"]
    commit = parameters["commit"]
    summary = parameters["summary"]
    key = parameters.get("key")
    if not COMMIT_RE.match(commit):
        raise BoardError("提交标识必须是 7 到 64 位十六进制字符")
    fingerprint = _fingerprint({"task": task_id, "commit": commit, "summary": summary})
    duplicate = _seen_lookup(ctx, "complete", key, fingerprint)
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
    _event(ctx, "complete", member, "完成任务 %s，提交 %s" % (task_id, commit))
    result = {
        "task": task_id,
        "status": "completed",
        "commit": commit,
        "summary": summary,
        "duplicate": False,
    }
    _seen_remember(ctx, "complete", key, fingerprint, result)
    return result


def _share(ctx, activation, kind):
    parameters = activation.parameters
    state = _state(ctx)
    member = _caller(ctx)
    fingerprint = _fingerprint({
        "kind": kind,
        "task": parameters.get("task"),
        "text": parameters["text"],
    })
    key = parameters.get("key")
    duplicate = _seen_lookup(ctx, kind, key, fingerprint)
    if duplicate is not None:
        return duplicate

    _require_running(state)
    _require_member(state, member)
    task_id = parameters.get("task")
    if task_id is not None:
        _task_or_error(state, task_id)
    limit = _config(ctx)["max_shared"]
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
    _event(ctx, kind, member, "共享%s%s" % (
        label, ("（任务 %s）" % task_id) if task_id else ""))
    result = {
        "kind": kind,
        "member": member,
        "task": task_id,
        "at": entry["at"],
        "duplicate": False,
    }
    _seen_remember(ctx, kind, key, fingerprint, result)
    return result


def _release_locked(ctx, activation):
    parameters = activation.parameters
    state = _state(ctx)
    task_id = parameters["task"]
    requested_member = parameters.get("member")
    caller = _caller(ctx)
    if requested_member is not None:
        _require_control(ctx, state)
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
    _event(ctx, "release", member, "释放任务 %s 的认领：%s；%s" % (
        task_id, "、".join(paths), reason))
    return {
        "task": task_id,
        "member": member,
        "released": True,
        "released_paths": paths,
        "reason": reason,
        "duplicate": False,
    }


def _leave_locked(ctx, activation):
    parameters = activation.parameters or {}
    state = _state(ctx)
    requested_member = parameters.get("member")
    caller = _caller(ctx)
    if requested_member is not None:
        _require_control(ctx, state)
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
    _event(ctx, "leave", member, "成员退出；释放任务 %s；%s" % (
        "、".join(released) if released else "无", reason))
    return {
        "member": member,
        "released_tasks": released,
        "released_paths": released_paths,
        "duplicate": False,
    }


def _integrator_config(ctx):
    """整合器调用参数；未配置 integrator_module 时返回空模块，不解析频道。"""
    value = ctx.config.get("integrator_module", "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise BoardError("配置 integrator_module 必须是字符串")
    module = value.strip()
    if not module:
        return "", []
    channels = list(ctx.filter_channels(
        "integrator_channel", list(DEFAULT_INTEGRATOR_CHANNELS)))
    if not channels:
        raise BoardError(
            "整合器调用频道为空；请检查 integrator_channel、channel_modes 与节点授权")
    return module, channels


async def _propagate_leave(ctx, activation, data):
    """在协作板事务锁释放后，把退出同步给同节点整合器。

    板状态已经提交；整合器失败只写入 integrator_error，不改写板状态。
    """
    data["integrator"] = None
    data["integrator_error"] = None
    try:
        module, channels = _integrator_config(ctx)
    except Exception as error:
        data["integrator_error"] = str(error) or "整合器配置无效"
        return data
    if not module:
        return data

    parameters = activation.parameters or {}
    reason = parameters.get("reason") or "主动退出"
    try:
        result = await ctx.network.call(
            ctx.node_id,
            module,
            "leave",
            {"member": data["member"], "reason": reason},
            channels=list(channels),
        )
    except Exception as error:
        data["integrator_error"] = str(error) or "整合器 leave 调用失败"
        return data
    if not isinstance(result, dict):
        data["integrator_error"] = "整合器返回了无法识别的结果"
        return data
    if result.get("status") != "ok":
        data["integrator_error"] = result.get("error") or "整合器 leave 操作失败"
        return data
    data["integrator"] = result.get("data")
    return data


def _status(ctx, activation):
    parameters = activation.parameters or {}
    state = _state(ctx)
    result = {
        "run": _copy(state["run"]) if state.get("run") else None,
        "overview": _overview(state["tasks"]),
        "members": _copy(state["members"]),
        "shared": _copy(state["shared"]),
        "event_count": len(state["events"]),
    }
    result["events"] = _copy(state["events"][-20:]) if parameters.get("include_events", True) else []
    return result


def _close_locked(ctx, activation):
    parameters = activation.parameters or {}
    state = _state(ctx)
    run = state.get("run")
    if not run:
        raise BoardError("当前还没有协作轮次，无法结束")
    if run.get("status") == "closed":
        raise BoardError("当前协作轮次已经结束")
    run["status"] = "closed"
    run["ended_at"] = _now()
    summary = parameters.get("summary") or "轮次结束，保留全部任务、认领与共享记录"
    _event(ctx, "close", None, summary)
    return {"run": _copy(run), "closed": True}


async def _locked(ctx, handler, *args):
    try:
        async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
            return handler(ctx, *args)
    except BoardError:
        raise
    except Exception as error:
        raise BoardError("协作板操作失败：%s" % (str(error) or "未知错误")) from error


async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="认领协作板只处理访问请求")
    operation = activation.operation
    try:
        if operation == "open":
            return ComponentResult(data=await _open(ctx, activation))
        if operation == "list":
            return ComponentResult(data=_list(ctx, activation))
        if operation == "claim":
            return ComponentResult(data=await _locked(ctx, _claim_locked, activation.parameters))
        if operation == "extend":
            return ComponentResult(data=await _locked(ctx, _extend_locked, activation.parameters))
        if operation == "release":
            return ComponentResult(data=await _locked(ctx, _release_locked, activation))
        if operation == "complete":
            return ComponentResult(data=await _locked(ctx, _complete_locked, activation.parameters))
        if operation == "discover":
            return ComponentResult(data=_share(ctx, activation, "discovery"))
        if operation == "fail":
            return ComponentResult(data=_share(ctx, activation, "failure"))
        if operation == "leave":
            data = await _locked(ctx, _leave_locked, activation)
            return ComponentResult(data=await _propagate_leave(ctx, activation, data))
        if operation == "status":
            return ComponentResult(data=_status(ctx, activation))
        if operation == "close":
            return ComponentResult(data=await _locked(ctx, _close_locked, activation))
        return ComponentResult(status="error", error="不支持的协作板操作：%s" % operation)
    except BoardError as error:
        return ComponentResult(status="error", error=str(error))
    except Exception as error:
        return ComponentResult(status="error", error="协作板操作失败：%s" % (
            str(error) or "未知错误"))
