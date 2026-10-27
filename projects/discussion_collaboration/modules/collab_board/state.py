"""协作任务、路径冲突与幂等回执规则。"""

import json
import re
import time
from copy import deepcopy
from uuid import uuid4
from app.runtime.requester import requester_id, caller_id
from app.transactions.locks import require_transaction_node
from domain.json_values import thaw
from domain.core.channel_filters import normalize_channels

def _caller(module):
    return requester_id.get() or caller_id.get() or module._access_origin.info.node_id


def _channels(module, field, default):
    return normalize_channels(module.config.get(field, default))


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


def _state(module):
    state = module.state
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
            require_transaction_node(module._access_origin.info.node_id)
            state[key] = value
    return state


def _config(module):
    channels = _channels(module, "member_channel", list(DEFAULT_MEMBER_CHANNEL))
    if not channels and module.config.get("channel_modes", {}).get("member_channel", "allow") == "allow":
        raise BoardError("成员发现频道为空；请检查 member_channel 与 channel_modes")
    max_tasks = module.config.get("max_tasks", 100)
    if type(max_tasks) is not int or not 1 <= max_tasks <= 500:
        raise BoardError("配置 max_tasks 必须是 1 到 500 的整数")
    max_shared = module.config.get("max_shared", 500)
    if type(max_shared) is not int or not 10 <= max_shared <= 2000:
        raise BoardError("配置 max_shared 必须是 10 到 2000 的整数")
    return {
        "member_channel": list(channels),
        "max_tasks": max_tasks,
        "max_shared": max_shared,
    }


def _control_allowed(module, state):
    """控制方是协作板所在节点，或不属于本轮成员的独立控制节点。

    核心访问激活不携带本次请求实际使用的频道；频道本身仍由操作声明的
    collab.claim／collab.admin 约束。这里再按成员身份阻止成员拿 member
    参数代他人操作，避免把 admin 频道误当成成员自助入口。
    """
    caller = _caller(module)
    if caller == module._access_origin.info.node_id:
        return True
    entry = _member_entry(state, caller)
    return entry is None or entry.get("status") != "active"


def _require_control(module, state):
    if not _control_allowed(module, state):
        raise BoardError(
            "带 member 需要 collab.admin 频道并由控制方调用；"
            "成员请省略 member 操作自己的认领或退出"
        )


def _event(module, kind, member, text):
    events = _state(module)["events"]
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


def _seen_key(module, operation, key):
    if key is None:
        return None
    return json.dumps(
        [module.module_id, module._access_origin.info.node_id, _caller(module), operation, key],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _seen_lookup(module, operation, key, fingerprint):
    if key is None:
        return None
    state = _state(module)
    record = state["seen"].get(_seen_key(module, operation, key))
    if record is None:
        return None
    if record.get("fingerprint") != fingerprint:
        raise BoardError("相同幂等键已用于不同参数的请求，已拒绝")
    result = _copy(record.get("result") or {})
    result["duplicate"] = True
    return result


def _seen_remember(module, operation, key, fingerprint, result):
    if key is None:
        return
    state = _state(module)
    internal = _seen_key(module, operation, key)
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


def _open_duplicate(module, fingerprint, key):
    state = _state(module)
    run = state.get("run")
    if not run or run.get("status") != "running":
        return None
    stored = _seen_lookup(module, "open", key, fingerprint)
    if stored is not None and stored.get("run", {}).get("id") == run["id"]:
        return stored
    raise BoardError("已有正在进行的协作轮次；如需新轮次请先 close")
