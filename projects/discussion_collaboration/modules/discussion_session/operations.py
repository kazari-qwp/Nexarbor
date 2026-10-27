"""讨论操作：短事务更新状态，提交后排队下一阶段信号。"""

from app.runtime.requester import requester_id, caller_id
from .state import (
    ACTIVE_STATUSES,
    _active_participants,
    _advance_after_complete,
    _archive,
    _config,
    _find_receipt,
    _fingerprint,
    _markdown,
    _new_run_id,
    _new_speech_id,
    _normalize_tasks,
    _now,
    _participant,
    _plain,
    _put_receipt,
    _record_event,
    _state,
    _summary,
    _waiting_for,
)

async def _emit(module, node, descriptor):
    channel, content = descriptor
    module.emit(node, access_strength=module.strength, channels=[channel], strength=1,
                content=content, kind=channel,
                timeout_seconds=module.config.get("activity_timeout_seconds", 86400),
                node_timeout_seconds=module.config.get("activity_timeout_seconds", 86400))


async def _start(module, node, params):
    config = _config(module)
    task = params["task"]
    rounds = params.get("rounds", config["rounds"])
    key = params.get("key")
    participants = await module.discover()
    fingerprint = _fingerprint({"task": task, "rounds": rounds})
    emission = None
    result = None
    try:
        async with module.transaction([node.info.node_id], timeout=20):
            state = _state(module)
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
                    _archive(module, run)
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
        await _emit(module, node, emission)
    return result


async def _speak(module, node, params):
    config = _config(module)
    text = params["text"]
    if len(text) > config["max_speech_chars"]:
        raise ValueError(
            f"单条发言最多 {config['max_speech_chars']} 个字符，当前 {len(text)} 个")
    key = params.get("key")
    hint_round = params.get("round")
    if hint_round is None:
        current = module.state.get("run")
        hint_round = current.get("round") if current else None
    fingerprint = _fingerprint({"text": text})
    emission = None
    result = None
    async with module.transaction([node.info.node_id], timeout=20):
        state = _state(module)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = (requester_id.get() or caller_id.get() or node.info.node_id)
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
                emission, _ = _advance_after_complete(module, state, run, requested)
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
        await _emit(module, node, emission)
    return result


async def _read(module, node, params):
    state = _state(module)
    round_filter = params.get("round")
    limit = params.get("limit", 20)
    speeches = [dict(item) for item in state.get("speeches", [])]
    if round_filter is not None:
        speeches = [item for item in speeches if item.get("round") == round_filter]
    # 读取频道只授予参与者与控制方；participants 名单用于说明谁在讨论中，
    # 非参与者由外部授权作为控制方读取。
    return {
        "run": _plain(state.get("run")),
        "participants": _plain(state.get("participants", [])),
        "speeches": _plain(speeches[-limit:]),
        "decision": _plain(state.get("decision")),
        "draft": _plain(state.get("draft", {"sections": []})),
        "artifact": _plain(state.get("artifact")),
        "errors": _plain(state.get("errors", [])),
        "events": _plain(state.get("events", [])),
    }


async def _decide(module, node, params):
    decision_text = params["decision"]
    tasks = _normalize_tasks(params.get("tasks", []))
    key = params.get("key")
    fingerprint = _fingerprint({"decision": decision_text, "tasks": tasks})
    emission = None
    result = None
    async with module.transaction([node.info.node_id], timeout=20):
        state = _state(module)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = (requester_id.get() or caller_id.get() or node.info.node_id)
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
        await _emit(module, node, emission)
    return result


async def _draft(module, node, params):
    section_name = params["section"]
    text = params["text"]
    key = params.get("key")
    fingerprint = _fingerprint({"section": section_name, "text": text})
    result = None
    async with module.transaction([node.info.node_id], timeout=20):
        state = _state(module)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = (requester_id.get() or caller_id.get() or node.info.node_id)
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
    return result


async def _finish(module, node, params):
    title = params.get("title")
    async with module.transaction([node.info.node_id], timeout=20):
        state = _state(module)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        member = (requester_id.get() or caller_id.get() or node.info.node_id)
        participant = _participant(state, member)
        if participant is None or participant.get("status") != "active":
            raise ValueError("只有当前讨论的 active 参与者可以生成成果")
        if participant.get("role") != "recorder":
            raise ValueError("只有 Recorder 可以生成成果")
        artifact = state.get("artifact")
        if run.get("status") == "completed" and artifact and artifact.get("run") == run["id"]:
            return {"run": run["id"], "artifact": _plain(artifact)}
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
        _archive(module, run)
        return {"run": run["id"], "artifact": _plain(artifact)}


async def _advance(module, node, params):
    emission = None
    missing = []
    result = None
    async with module.transaction([node.info.node_id], timeout=20):
        state = _state(module)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        if run.get("phase") != "discussing":
            raise ValueError(f"当前阶段为 {run.get('phase')}，只有 discussing 阶段可以推进轮次")
        emission, missing = _advance_after_complete(
            module, state, run, run["round"], force=True)
        result = {
            "run": run["id"],
            "round": run["round"],
            "phase": run["phase"],
            "missing": missing,
        }
    if emission is not None:
        await _emit(module, node, emission)
    return result


async def _leave(module, node, params):
    target_id = params.get("member") or (requester_id.get() or caller_id.get() or node.info.node_id)
    reason = params.get("reason")
    emission = None
    result = None
    async with module.transaction([node.info.node_id], timeout=20):
        state = _state(module)
        run = state.get("run")
        if not run:
            raise ValueError("当前没有讨论运行，请先 start")
        target = _participant(state, target_id)
        if target is None:
            raise ValueError(f"成员“{target_id}”不在当前参与者名单中")
        caller_participant = _participant(state, (requester_id.get() or caller_id.get() or node.info.node_id))
        if target_id != (requester_id.get() or caller_id.get() or node.info.node_id) and caller_participant is not None:
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
                module, "leave", target_id,
                f"{target.get('name') or target_id} {note}")
            missing = []
            if run.get("phase") == "discussing":
                if not _active_participants(state):
                    run["status"] = "stopped"
                    run["phase"] = "stopped"
                    run["ended_at"] = _now()
                    run["error"] = "所有成员均已退出"
                    _archive(module, run)
                else:
                    emission, missing = _advance_after_complete(
                        module, state, run, run["round"])
            result = {
                "run": run["id"],
                "round": run["round"],
                "phase": run["phase"],
                "member": target_id,
                "missing": missing,
                "duplicate": False,
            }
    if emission is not None:
        await _emit(module, node, emission)
    return result


async def _stop(module, node, params):
    reason = params.get("reason")
    async with module.transaction([node.info.node_id], timeout=20):
        state = _state(module)
        run = state.get("run")
        if run and run.get("status") in ACTIVE_STATUSES:
            run["status"] = "stopped"
            run["phase"] = "stopped"
            run["ended_at"] = _now()
            run["error"] = reason or None
            _archive(module, run)
        result = _summary(module, reason)
    return result


async def _status(module, node, params):
    include_history = bool(params.get("include_history", False))
    state = _state(module)
    run = state.get("run")
    decision = state.get("decision")
    sections = state.get("draft", {}).get("sections", [])
    artifact = state.get("artifact")
    return {
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
    }
