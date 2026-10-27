"""讨论运行、回执和成果格式。"""

import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from app.transactions.locks import require_transaction_node
from domain.json_values import thaw
from domain.core.channel_filters import normalize_channels

def _member_channels(module):
    channels = normalize_channels(module.config.get("member_channel", [DEFAULT_MEMBER_CHANNEL]))
    mode = module.config.get("channel_modes", {}).get("member_channel", "allow")
    if not channels and mode == "allow":
        raise ValueError("参与者发现频道为空，请检查 member_channel 与应用授权")
    return channels


ACTIVE_STATUSES = ("discussing", "deciding", "drafting")


ROLES = ("leader", "recorder", "member")


DEFAULT_MEMBER_CHANNEL = "discussion"


MAX_ERRORS = 20


MAX_RECEIPTS = 300


MAX_EVENTS = 200


def _plain(value):
    """配置、参数与调用结果可能是冻结 JSON，转换成可安全修改的普通副本。"""
    return deepcopy(thaw(value))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_run_id():
    return "disc-" + secrets.token_hex(4)


def _new_speech_id():
    return "sp-" + secrets.token_hex(4)


def _fingerprint(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _positive_int(config, key, default, low, high):
    value = config.get(key, default)
    if type(value) is not int or value < low or value > high:
        raise ValueError(f"配置 {key} 必须是 {low} 到 {high} 之间的整数")
    return value


def _config(module):
    return {
        "rounds": _positive_int(module.config, "rounds", 3, 1, 20),
        "max_speech_chars": _positive_int(module.config, "max_speech_chars", 4000, 100, 8000),
        "max_speeches": _positive_int(module.config, "max_speeches", 500, 10, 5000),
        "max_runs": _positive_int(module.config, "max_runs", 20, 1, 50),
        "member_channel": _member_channels(module),
    }


def _state(module):
    defaults = {
        "run": None,
        "participants": [],
        "speeches": [],
        "decision": None,
        "draft": {"sections": []},
        "artifact": None,
        "runs": [],
        "errors": [],
        "receipts": [],
        "events": [],
    }
    state = module.state
    for key, value in defaults.items():
        if key not in state:
            require_transaction_node(module._access_origin.info.node_id)
            state[key] = deepcopy(value)
    return state


def _record_error(module, operation, message):
    require_transaction_node(module._access_origin.info.node_id)
    state = _state(module)
    errors = [dict(item) for item in state.get("errors", [])]
    errors.append({"at": _now(), "operation": str(operation or ""), "message": str(message)})
    state["errors"] = errors[-MAX_ERRORS:]


def _record_event(module, kind, member, text):
    """记录讨论事件；退出等成员变化要能在读取结果中看到。"""
    state = _state(module)
    events = [dict(item) for item in state.get("events", [])]
    events.append({
        "at": _now(),
        "kind": str(kind),
        "member": member,
        "text": str(text),
    })
    state["events"] = events[-MAX_EVENTS:]


def _mark_failed(module, operation, message):
    """基础设施或意外异常时保留失败报告；普通业务校验不改变运行。"""
    state = _state(module)
    run = state.get("run")
    if run and run.get("status") in ACTIVE_STATUSES:
        require_transaction_node(module._access_origin.info.node_id)
        run["status"] = "failed"
        run["phase"] = "failed"
        run["ended_at"] = _now()
        run["error"] = str(message)
        _archive(module, run)


def _archive(module, run):
    state = _state(module)
    max_runs = _positive_int(module.config, "max_runs", 20, 1, 50)
    summary = {
        "id": run["id"],
        "task": run["task"],
        "status": run["status"],
        "round": run["round"],
        "started_at": run["started_at"],
        "ended_at": run.get("ended_at"),
        "error": run.get("error"),
    }
    runs = [dict(item) for item in state.get("runs", []) if item.get("id") != run["id"]]
    runs.append(summary)
    state["runs"] = runs[-max_runs:]


def _participant(state, member):
    for participant in state.get("participants", []):
        if participant.get("id") == member:
            return participant
    return None


def _active_participants(state):
    return [p for p in state.get("participants", []) if p.get("status") == "active"]


def _waiting_for(state, run, round_no):
    active = _active_participants(state)
    spoken = {
        speech.get("member")
        for speech in state.get("speeches", [])
        if speech.get("run") == run["id"] and speech.get("round") == round_no
    }
    return [p["id"] for p in active if p["id"] not in spoken]


def _advance_after_complete(module, state, run, round_no, *, force=False):
    """本轮齐备时推进一次；返回信号描述。调用方必须持有节点锁。"""
    missing = _waiting_for(state, run, round_no)
    if missing and not force:
        return None, missing
    active_ids = [p["id"] for p in _active_participants(state)]
    if round_no < run["rounds"]:
        run["round"] = round_no + 1
        run["status"] = "discussing"
        run["phase"] = "discussing"
        return ("discussion.round", {
            "run": run["id"],
            "round": run["round"],
            "phase": "discussing",
            "task": run["task"],
            "expected": active_ids,
        }), missing
    run["status"] = "deciding"
    run["phase"] = "deciding"
    return ("discussion.decision", {
        "run": run["id"],
        "round": run["round"],
        "phase": "deciding",
        "task": run["task"],
    }), missing


def _find_receipt(state, operation, key, run_id, member=None, round_no=None):
    for receipt in reversed(state.get("receipts", [])):
        if (receipt.get("op") == operation
                and receipt.get("key") == key
                and receipt.get("run") == run_id
                and receipt.get("member") == member
                and receipt.get("round") == round_no):
            return receipt
    return None


def _put_receipt(state, operation, key, fingerprint, run_id, member=None, round_no=None):
    receipts = [dict(item) for item in state.get("receipts", [])]
    receipts.append({
        "op": operation,
        "key": str(key),
        "fingerprint": str(fingerprint),
        "run": str(run_id),
        "member": member,
        "round": round_no,
        "at": _now(),
    })
    state["receipts"] = receipts[-MAX_RECEIPTS:]


def _normalize_tasks(items):
    tasks = []
    for item in _plain(items):
        task = {
            "title": str(item["title"]),
            "paths": [str(path) for path in item.get("paths", [])],
        }
        detail = item.get("detail")
        if detail is not None:
            task["detail"] = str(detail)
        tasks.append(task)
    return tasks


def _summary(module, reason=None):
    state = _state(module)
    run = state.get("run")
    if not run:
        return {
            "run": None,
            "status": "idle",
            "phase": "idle",
            "speeches": 0,
            "decision": None,
            "draft": None,
            "artifact": None,
            "started_at": None,
            "ended_at": None,
            "reason": reason,
        }
    decision = state.get("decision")
    sections = state.get("draft", {}).get("sections", [])
    artifact = state.get("artifact")
    return {
        "run": run["id"],
        "status": run["status"],
        "phase": run["phase"],
        "speeches": len(state.get("speeches", [])),
        "decision": ({"text": decision["text"], "tasks": decision["tasks"]}
                     if decision else None),
        "draft": ({"sections": [section["name"] for section in sections]}
                  if sections else None),
        "artifact": ({"run": artifact["run"], "title": artifact["title"], "at": artifact["at"]}
                     if artifact else None),
        "started_at": run["started_at"],
        "ended_at": run.get("ended_at"),
        "reason": reason,
    }


def _markdown(run, title, decision, sections, participants):
    names = "、".join(
        f'{item.get("name") or item.get("id")}（{item.get("role")}）'
        for item in participants
    ) or "（无）"
    lines = [
        f"# {title}",
        "",
        f"- 讨论任务：{run['task']}",
        f"- 运行：{run['id']}",
        f"- 轮次：{run['rounds']}",
        f"- 参与者：{names}",
        "",
        "## 讨论任务",
        "",
        run["task"],
        "",
        "## Leader 决策",
        "",
        decision["text"],
        "",
        "## 任务清单",
        "",
    ]
    if decision["tasks"]:
        for index, task in enumerate(decision["tasks"], 1):
            lines.append(f"### {index}. {task['title']}")
            if task.get("paths"):
                lines.append("- 路径：" + "、".join(task["paths"]))
            if task.get("detail"):
                lines.append("- 说明：" + task["detail"])
            lines.append("")
    else:
        lines.extend(["（无）", ""])
    lines.append("## Recorder 成果")
    lines.append("")
    for section in sections:
        lines.append(f"### {section['name']}")
        lines.append("")
        lines.append(section["text"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
