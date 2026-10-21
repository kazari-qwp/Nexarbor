"""讨论会话：管理一次讨论的运行身份、轮次、发言、决策、草稿与最终成果。

参与者是真实 Agent 上另行安装的 discussion.seat 席位；本模块只在配置频道里
发现席位、调用 describe 读取身份，再用信号推进轮次与决策，不运行模型、不拼装提示词。
"""

import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

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


def _config(ctx):
    return {
        "rounds": _positive_int(ctx.config, "rounds", 3, 1, 20),
        "max_speech_chars": _positive_int(ctx.config, "max_speech_chars", 4000, 100, 8000),
        "max_speeches": _positive_int(ctx.config, "max_speeches", 500, 10, 5000),
        "max_runs": _positive_int(ctx.config, "max_runs", 20, 1, 50),
        "member_channel": _member_channels(ctx),
    }


def _member_channels(ctx):
    channels = ctx.filter_channels("member_channel", [DEFAULT_MEMBER_CHANNEL])
    channels = [str(item) for item in channels if str(item)]
    if not channels:
        raise ValueError("参与者发现频道为空，请检查 member_channel 与应用授权")
    return channels


def _state(ctx):
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
    state = ctx.state
    for key, value in defaults.items():
        if key not in state:
            state[key] = deepcopy(value)
    return state


def _record_error(ctx, operation, message):
    state = _state(ctx)
    errors = [dict(item) for item in state.get("errors", [])]
    errors.append({"at": _now(), "operation": str(operation or ""), "message": str(message)})
    state["errors"] = errors[-MAX_ERRORS:]


def _error(ctx, operation, message):
    _record_error(ctx, operation, message)
    return ComponentResult(status="error", error=str(message))


def _record_event(ctx, kind, member, text):
    """记录讨论事件；退出等成员变化要能在读取结果中看到。"""
    state = _state(ctx)
    events = [dict(item) for item in state.get("events", [])]
    events.append({
        "at": _now(),
        "kind": str(kind),
        "member": member,
        "text": str(text),
    })
    state["events"] = events[-MAX_EVENTS:]


def _mark_failed(ctx, operation, message):
    """基础设施或意外异常时保留失败报告；普通业务校验不改变运行。"""
    state = _state(ctx)
    run = state.get("run")
    if run and run.get("status") in ACTIVE_STATUSES:
        run["status"] = "failed"
        run["phase"] = "failed"
        run["ended_at"] = _now()
        run["error"] = str(message)
        _archive(ctx, run)


def _archive(ctx, run):
    state = _state(ctx)
    max_runs = _positive_int(ctx.config, "max_runs", 20, 1, 50)
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


def _advance_after_complete(ctx, state, run, round_no, *, force=False):
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


async def _emit(ctx, descriptor):
    channel, content = descriptor
    # 网络 emit 是同步排队入口；信号传播由核心继续调度，不在这里持锁等待。
    ctx.network.emit(channels=[channel], strength=1, content=content, kind=channel, timeout_seconds=ctx.config.get("activity_timeout_seconds", 86400), node_timeout_seconds=ctx.config.get("activity_timeout_seconds", 86400))


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


def _summary(ctx, reason=None):
    state = _state(ctx)
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


async def _discover(ctx):
    channels = _member_channels(ctx)
    endpoints = _plain(await ctx.network.modules("discussion.seat", channels=channels))
    if not endpoints:
        raise ValueError(
            "未发现 discussion.seat 席位；请确认席位模块已安装，并通过频道 "
            + "、".join(channels) + " 可达"
        )
    found = []
    failures = []
    for endpoint in endpoints:
        node_id = endpoint.get("node_id")
        if not node_id:
            failures.append("端点缺少 node_id")
            continue
        result = await ctx.network.call(
            node_id, "discussion.seat", "describe", {}, channels=channels)
        if not isinstance(result, dict) or result.get("status") != "ok":
            error = result.get("error") if isinstance(result, dict) else "describe 返回非对象"
            failures.append(f"{node_id}：{error or 'describe 失败'}")
            continue
        data = _plain(result.get("data") or {})
        member_id = str(data.get("id") or node_id)
        name = str(data.get("name") or node_id)
        role = str(data.get("role") or "")
        if role not in ROLES:
            failures.append(f"{member_id}：角色“{role or '空'}”不是 leader/recorder/member")
            continue
        if any(item["id"] == member_id for item in found):
            failures.append(f"{member_id}：席位 id 重复")
            continue
        found.append({"id": member_id, "name": name, "role": role, "status": "active"})
    leaders = [item for item in found if item["role"] == "leader"]
    recorders = [item for item in found if item["role"] == "recorder"]
    members = [item for item in found if item["role"] == "member"]
    problems = []
    if len(leaders) != 1:
        problems.append(f"需要恰好 1 名 leader，实际 {len(leaders)} 名")
    if len(recorders) != 1:
        problems.append(f"需要恰好 1 名 recorder，实际 {len(recorders)} 名")
    if not members:
        problems.append("需要至少 1 名 member，实际 0 名")
    if failures:
        problems.append("部分席位无法读取：" + "；".join(failures))
    if problems:
        listing = "；".join(
            f'{item["name"]}({item["id"]})={item["role"]}' for item in found
        ) or "无"
        raise ValueError("参与者发现不符合要求：" + "；".join(problems) + "。发现结果：" + listing)
    return found


async def _start(ctx, params):
    config = _config(ctx)
    task = params["task"]
    rounds = params.get("rounds", config["rounds"])
    key = params.get("key")
    participants = await _discover(ctx)
    fingerprint = _fingerprint({"task": task, "rounds": rounds})
    emission = None
    result = None
    try:
        async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
            state = _state(ctx)
            run = state.get("run")
            active = bool(run and run.get("status") in ACTIVE_STATUSES)
            duplicate = False
            if active:
                receipt = _find_receipt(state, "start", key, run["id"], round_no=1) if key else None
                if receipt:
                    if receipt["fingerprint"] != fingerprint:
                        raise ValueError(f"去重键“{key}”已用于不同请求")
                    duplicate = True
                    result = {
                        "run": run["id"],
                        "status": run["status"],
                        "round": run["round"],
                        "participants": _plain(state["participants"]),
                        "duplicate": True,
                    }
                elif key is not None:
                    raise ValueError(
                        f"已有进行中的讨论运行“{run['id']}”；请先 stop 或使用相同去重键")
                else:
                    raise ValueError(
                        f"已有进行中的讨论运行“{run['id']}”；请先 stop 或携带相同去重键")
            if not duplicate:
                if run:
                    _archive(ctx, run)
                run_id = _new_run_id()
                now = _now()
                state["run"] = {
                    "id": run_id,
                    "status": "discussing",
                    "task": task,
                    "phase": "discussing",
                    "round": 1,
                    "rounds": rounds,
                    "started_at": now,
                    "ended_at": None,
                    "error": None,
                }
                state["participants"] = participants
                state["speeches"] = []
                state["decision"] = None
                state["draft"] = {"sections": []}
                state["artifact"] = None
                if key is not None:
                    receipts = [
                        item for item in state.get("receipts", [])
                        if not (item.get("op") == "start" and item.get("key") == key)
                    ]
                    state["receipts"] = receipts
                    _put_receipt(state, "start", key, fingerprint, run_id, round_no=1)
                emission = ("discussion.round", {
                    "run": run_id,
                    "round": 1,
                    "phase": "discussing",
                    "task": task,
                    "expected": [item["id"] for item in participants],
                })
                result = {
                    "run": run_id,
                    "status": "discussing",
                    "round": 1,
                    "participants": _plain(participants),
                    "duplicate": False,
                }
    except ValueError:
        raise
    if emission is not None:
        await _emit(ctx, emission)
    return ComponentResult(data=result)


async def _speak(ctx, params):
    config = _config(ctx)
    text = params["text"]
    if len(text) > config["max_speech_chars"]:
        raise ValueError(
            f"单条发言最多 {config['max_speech_chars']} 个字符，当前 {len(text)} 个")
    key = params.get("key")
    hint_round = params.get("round")
    if hint_round is None:
        current = ctx.state.get("run")
        hint_round = current.get("round") if current else None
    fingerprint = _fingerprint({"text": text})
    emission = None
    result = None
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        state = _state(ctx)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = ctx.caller_id
        participant = _participant(state, member)
        if participant is not None and key is not None and hint_round is not None:
            receipt = _find_receipt(
                state, "speak", key, run["id"], member, hint_round)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise ValueError(f"去重键“{key}”已用于不同发言")
                result = {
                    "run": run["id"],
                    "round": run["round"],
                    "accepted_round": hint_round,
                    "phase": run["phase"],
                    "recorded": True,
                    "waiting_for": _waiting_for(state, run, run["round"]),
                }
        if result is None:
            if participant is None or participant.get("status") != "active":
                raise ValueError("只有当前讨论中状态为 active 的参与者可以发言")
            if run.get("status") not in ("discussing", "deciding"):
                raise ValueError(f"当前运行状态为 {run.get('status')}，不能继续发言")
            requested = hint_round if hint_round is not None else run["round"]
            current = run["round"]
            if requested > current:
                raise ValueError(f"轮次不是当前轮：当前第 {current} 轮，收到第 {requested} 轮发言")
            if requested < current - 1:
                raise ValueError(f"轮次已过期：当前第 {current} 轮，收到第 {requested} 轮发言")
            speech = {
                "id": _new_speech_id(),
                "run": run["id"],
                "round": requested,
                "member": member,
                "role": participant["role"],
                "text": text,
                "at": _now(),
            }
            state["speeches"] = (list(state.get("speeches", [])) + [speech])[-config["max_speeches"]:]
            if requested == current and run.get("status") == "discussing":
                emission, _ = _advance_after_complete(ctx, state, run, requested)
            if key is not None:
                _put_receipt(
                    state, "speak", key, fingerprint, run["id"], member, requested)
            result = {
                "run": run["id"],
                "round": run["round"],
                "accepted_round": requested,
                "phase": run["phase"],
                "recorded": True,
                "waiting_for": _waiting_for(state, run, run["round"]),
            }
    if emission is not None:
        await _emit(ctx, emission)
    return ComponentResult(data=result)


async def _read(ctx, params):
    state = _state(ctx)
    round_filter = params.get("round")
    limit = params.get("limit", 20)
    speeches = [dict(item) for item in state.get("speeches", [])]
    if round_filter is not None:
        speeches = [item for item in speeches if item.get("round") == round_filter]
    # 读取频道只授予参与者与控制方；participants 名单用于说明谁在讨论中，
    # 非参与者由外部授权作为控制方读取。
    return ComponentResult(data={
        "run": _plain(state.get("run")),
        "participants": _plain(state.get("participants", [])),
        "speeches": _plain(speeches[-limit:]),
        "decision": _plain(state.get("decision")),
        "draft": _plain(state.get("draft", {"sections": []})),
        "artifact": _plain(state.get("artifact")),
        "errors": _plain(state.get("errors", [])),
        "events": _plain(state.get("events", [])),
    })


async def _decide(ctx, params):
    decision_text = params["decision"]
    tasks = _normalize_tasks(params.get("tasks", []))
    key = params.get("key")
    fingerprint = _fingerprint({"decision": decision_text, "tasks": tasks})
    emission = None
    result = None
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        state = _state(ctx)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = ctx.caller_id
        participant = _participant(state, member)
        if participant is None or participant.get("status") != "active":
            raise ValueError("只有当前讨论的 active 参与者可以提交决策")
        if participant.get("role") != "leader":
            raise ValueError("只有 Leader 可以提交决策")
        if run.get("phase") != "deciding":
            raise ValueError(f"当前阶段为 {run.get('phase')}，只有 deciding 阶段可以决策")
        if key is not None:
            receipt = _find_receipt(state, "decide", key, run["id"], member, None)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise ValueError(f"去重键“{key}”已用于不同决策")
                result = {
                    "run": run["id"],
                    "phase": run["phase"],
                    "tasks": _plain(state["decision"]["tasks"]),
                }
        if result is None:
            decision = {
                "text": decision_text,
                "tasks": tasks,
                "member": member,
                "at": _now(),
            }
            state["decision"] = decision
            run["status"] = "drafting"
            run["phase"] = "drafting"
            if key is not None:
                _put_receipt(state, "decide", key, fingerprint, run["id"], member)
            emission = ("discussion.record", {
                "run": run["id"],
                "phase": "drafting",
                "task": run["task"],
                "decision": decision_text,
            })
            result = {
                "run": run["id"],
                "phase": "drafting",
                "tasks": _plain(tasks),
            }
    if emission is not None:
        await _emit(ctx, emission)
    return ComponentResult(data=result)


async def _draft(ctx, params):
    section_name = params["section"]
    text = params["text"]
    key = params.get("key")
    fingerprint = _fingerprint({"section": section_name, "text": text})
    result = None
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        state = _state(ctx)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = ctx.caller_id
        participant = _participant(state, member)
        if participant is None or participant.get("status") != "active":
            raise ValueError("只有当前讨论的 active 参与者可以写草稿")
        if participant.get("role") != "recorder":
            raise ValueError("只有 Recorder 可以写草稿")
        if run.get("phase") != "drafting":
            raise ValueError(f"当前阶段为 {run.get('phase')}，只有 drafting 阶段可以写草稿")
        if key is not None:
            receipt = _find_receipt(state, "draft", key, run["id"], member, None)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise ValueError(f"去重键“{key}”已用于不同草稿")
                result = {
                    "run": run["id"],
                    "phase": run["phase"],
                    "sections": _plain(state["draft"]["sections"]),
                }
        if result is None:
            sections = [dict(item) for item in state.get("draft", {}).get("sections", [])]
            now = _now()
            for section in sections:
                if section["name"] == section_name:
                    section["text"] = text
                    section["updated_at"] = now
                    break
            else:
                sections.append({"name": section_name, "text": text, "updated_at": now})
            state["draft"] = {"sections": sections}
            if key is not None:
                _put_receipt(state, "draft", key, fingerprint, run["id"], member)
            result = {
                "run": run["id"],
                "phase": run["phase"],
                "sections": _plain(sections),
            }
    return ComponentResult(data=result)


async def _finish(ctx, params):
    title = params.get("title")
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        state = _state(ctx)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = ctx.caller_id
        participant = _participant(state, member)
        if participant is None or participant.get("status") != "active":
            raise ValueError("只有当前讨论的 active 参与者可以生成成果")
        if participant.get("role") != "recorder":
            raise ValueError("只有 Recorder 可以生成成果")
        artifact = state.get("artifact")
        if run.get("status") == "completed" and artifact and artifact.get("run") == run["id"]:
            return ComponentResult(data={"run": run["id"], "artifact": _plain(artifact)})
        if run.get("phase") != "drafting":
            raise ValueError(f"当前阶段为 {run.get('phase')}，只有 drafting 阶段可以生成成果")
        decision = state.get("decision")
        if not decision:
            raise ValueError("尚未收到 Leader 决策，不能生成成果")
        sections = state.get("draft", {}).get("sections", [])
        if not sections:
            raise ValueError("草稿还没有任何章节，不能生成成果")
        final_title = title or f"讨论成果：{run['task']}"
        final_title = final_title[:200]
        content = _markdown(
            run, final_title, decision, sections, state.get("participants", []))
        artifact = {
            "run": run["id"],
            "title": final_title,
            "content": content,
            "tasks": _plain(decision["tasks"]),
            "at": _now(),
        }
        state["artifact"] = artifact
        run["status"] = "completed"
        run["phase"] = "completed"
        run["ended_at"] = _now()
        run["error"] = None
        _archive(ctx, run)
        return ComponentResult(data={"run": run["id"], "artifact": _plain(artifact)})


async def _advance(ctx, params):
    emission = None
    missing = []
    result = None
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        state = _state(ctx)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        if run.get("phase") != "discussing":
            raise ValueError(f"当前阶段为 {run.get('phase')}，只有 discussing 阶段可以推进轮次")
        emission, missing = _advance_after_complete(
            ctx, state, run, run["round"], force=True)
        result = {
            "run": run["id"],
            "round": run["round"],
            "phase": run["phase"],
            "missing": missing,
        }
    if emission is not None:
        await _emit(ctx, emission)
    return ComponentResult(data=result)


async def _leave(ctx, params):
    target_id = params.get("member") or ctx.caller_id
    reason = params.get("reason")
    emission = None
    result = None
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        state = _state(ctx)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        target = _participant(state, target_id)
        if target is None:
            raise ValueError(f"成员“{target_id}”不在当前参与者名单中")
        caller_participant = _participant(state, ctx.caller_id)
        if target_id != ctx.caller_id and caller_participant is not None:
            raise ValueError(
                "参与者只能让本人退出；代其他成员退出需要控制方经 discussion.control 频道发起")
        if target.get("status") != "active":
            # 重复退出是幂等成功：不重复写事件，也不改变本轮等待名单。
            missing = (_waiting_for(state, run, run["round"])
                       if run.get("phase") == "discussing" else [])
            result = {
                "run": run["id"],
                "round": run["round"],
                "phase": run["phase"],
                "member": target_id,
                "missing": missing,
                "duplicate": True,
            }
        else:
            target["status"] = "left"
            note = "退出讨论"
            if reason:
                note += f"：{reason}"
            _record_event(
                ctx, "leave", target_id,
                f"{target.get('name') or target_id} {note}")
            missing = []
            if run.get("phase") == "discussing":
                if not _active_participants(state):
                    run["status"] = "stopped"
                    run["phase"] = "stopped"
                    run["ended_at"] = _now()
                    run["error"] = "所有成员均已退出"
                    _archive(ctx, run)
                else:
                    emission, missing = _advance_after_complete(
                        ctx, state, run, run["round"])
            result = {
                "run": run["id"],
                "round": run["round"],
                "phase": run["phase"],
                "member": target_id,
                "missing": missing,
                "duplicate": False,
            }
    if emission is not None:
        await _emit(ctx, emission)
    return ComponentResult(data=result)


async def _stop(ctx, params):
    reason = params.get("reason")
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        state = _state(ctx)
        run = state.get("run")
        if run and run.get("status") in ACTIVE_STATUSES:
            run["status"] = "stopped"
            run["phase"] = "stopped"
            run["ended_at"] = _now()
            run["error"] = reason or None
            _archive(ctx, run)
        result = _summary(ctx, reason)
    return ComponentResult(data=result)


async def _status(ctx, params):
    include_history = bool(params.get("include_history", False))
    state = _state(ctx)
    run = state.get("run")
    decision = state.get("decision")
    sections = state.get("draft", {}).get("sections", [])
    artifact = state.get("artifact")
    return ComponentResult(data={
        "run": run["id"] if run else None,
        "status": run["status"] if run else "idle",
        "phase": run["phase"] if run else "idle",
        "round": run["round"] if run else 0,
        "participants": _plain(state.get("participants", [])),
        "speeches": len(state.get("speeches", [])),
        "decision": ({"text": decision["text"], "tasks": _plain(decision["tasks"])}
                     if decision else None),
        "draft": ({"sections": [section["name"] for section in sections]}
                  if sections else None),
        "artifact": ({"run": artifact["run"], "title": artifact["title"], "at": artifact["at"]}
                     if artifact else None),
        "errors": _plain(state.get("errors", [])),
        "runs": _plain(state.get("runs", [])) if include_history else [],
    })


_HANDLERS = {
    "start": _start,
    "speak": _speak,
    "read": _read,
    "decide": _decide,
    "draft": _draft,
    "finish": _finish,
    "advance": _advance,
    "leave": _leave,
    "stop": _stop,
    "status": _status,
}


async def execute(ctx, activation):
    _state(ctx)
    if activation.kind == "signal":
        return ComponentResult(data={"ignored": True})
    if activation.kind != "access":
        return ComponentResult(status="error", error="讨论会话只接受访问请求")
    operation = activation.operation
    handler = _HANDLERS.get(operation)
    if handler is None:
        return _error(ctx, operation, "不支持的讨论会话操作")
    try:
        return await handler(ctx, activation.parameters or {})
    except ValueError as error:
        return _error(ctx, operation, str(error))
    except Exception as error:  # 锁等待、信号发送等意外失败保留失败报告
        _mark_failed(ctx, operation, str(error))
        return _error(ctx, operation, str(error))
