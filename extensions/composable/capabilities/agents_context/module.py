"""角色身份装配与按需只读查询；私人记忆只由 recall 检索。"""
import json
from collections.abc import Mapping
from datanet.core.module_protocol import ComponentResult
from .scene import scene, inspect_place, map_graph, plain as _plain
from .map_image import render_map

OPENING_INPUT_ID = "agents.context.opening"
PUBLIC_FIELD_LABELS = {"name": "姓名", "gender": "性别", "profession": "职业", "age_group": "年龄段"}


def _error(message):
    return ComponentResult(status="error", error=message)


def _public_profile(records, config):
    return {field: _plain(records[field]) for field in config.get("public_fields", ("name", "gender", "profession", "age_group")) if field in records}


def _system_prompt(config):
    parts = []
    for key in ("persona", "common"):
        text = config.get(key) or ""
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def _knowledge_context(config, records):
    knowledge = config.get("knowledge")
    if not isinstance(knowledge, (list, tuple)):
        return []
    entries = []
    seen = set()
    for entry in knowledge:
        if not isinstance(entry, Mapping):
            continue
        knowledge_id = entry.get("id")
        if not isinstance(knowledge_id, str) or not knowledge_id or knowledge_id in seen:
            continue
        when = entry.get("when")
        if not isinstance(when, Mapping):
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        if all(field in records and records[field] == value for field, value in when.items()):
            # 前缀保证与固定地图条目区分，同时保持配置 id 稳定可追踪。
            entries.append({"id": f"knowledge:{knowledge_id}", "text": text})
            seen.add(knowledge_id)
    return entries


def _context(config, records):
    context = []
    context.extend(_knowledge_context(config, records))
    return context


def _tail(current):
    location = current["location"]
    tail = ["个人记录：" + json.dumps(current["records"], ensure_ascii=False, sort_keys=True),
            "当前位置：" + (location["name"] + "（" + location["id"] + "）" if location else "未知"),
            "可直接前往：" + ("、".join(item["name"] + "（" + item["id"] + "）" for item in current["exits"]) or "暂无"),
            "同地人物：" + (json.dumps(current["people"], ensure_ascii=False) if current["people"] else "暂无")]
    clock = current["clock"]
    if clock is not None:
        tail.append(f"当前时间：第{clock['day']}天 {clock['slot']}（计数 {clock['tick']}）")
    return tail


async def _snapshot(ctx):
    current = await scene(ctx)
    return {"system_prompt": _system_prompt(ctx.config), "context": _context(ctx.config, current["records"]),
            "tail": _tail(current), "location": current["location"]["id"] if current["location"] else None,
            "nearby": current["exits"] + current["people"], "clock": current["clock"], "records": current["records"],
            "memories": _plain(ctx.state.get("memories", [])), "opening_queued": bool(ctx.state.get("opening_queued", False))}


def _memory_result(memories, duplicate=False):
    return {
        "duplicate": duplicate,
        "memories": _plain(memories),
        "count": len(memories),
    }


def _check_identity(ctx):
    if ctx.requester_id != ctx.node_id:
        return _error("只能操作自己的角色上下文和私人记忆")
    return None


async def execute(ctx, activation):
    if activation.kind != "access":
        return _error("不支持的请求")

    denied = _check_identity(ctx)
    if denied is not None:
        return denied

    operation = activation.operation
    parameters = activation.parameters or {}

    if operation == "prepare":
        try:
            snapshot = await _snapshot(ctx)
            ctx.publish_metadata(_public_profile(snapshot["records"], ctx.config))
            inputs = None
            if not ctx.state.get("opening_queued", False):
                opening = ctx.config.get("opening") or ""
                if isinstance(opening, str) and opening.strip():
                    inputs = [{"id": OPENING_INPUT_ID, "text": opening}]
            payload = {
                "system_prompt": snapshot["system_prompt"],
                "context": snapshot["context"],
                "tail": snapshot["tail"],
            }
            if inputs is not None:
                payload["inputs"] = inputs
            ctx.update_inputs(payload)
            if inputs is not None:
                ctx.state["opening_queued"] = True
                snapshot["opening_queued"] = True
            return ComponentResult(data=snapshot)
        except RuntimeError as exc:
            return _error(str(exc))

    if operation == "look":
        try:
            return ComponentResult(data=await scene(ctx))
        except RuntimeError as exc:
            return _error(str(exc))

    if operation == "place":
        try:
            return ComponentResult(data=await inspect_place(ctx, parameters.get("place")))
        except (RuntimeError, ValueError) as exc:
            return _error(str(exc))

    if operation == "map":
        try:
            graph = await map_graph(ctx)
            if not graph["places"]:
                return _error("当前授权范围内没有可绘制的地点")
            image = render_map(graph, _plain(ctx.config))
            labels = "；".join(item["name"] + "=" + item["id"] for item in graph["places"])
            return ComponentResult(data={"format": "nexarbor-tool-content/v1", "content": [
                {"type": "text", "text": "地点道路图。线段为道路，箭头为单向通行；示意位置不代表距离。地点编号：" + labels},
                {"type": "image", "name": "地点道路图.png", "mediaType": "image/png", "data": image}]})
        except (RuntimeError, ValueError) as exc:
            return _error(str(exc))

    if operation == "remember":
        text = parameters.get("text")
        key = parameters.get("key")
        memories = [dict(item) for item in ctx.state.get("memories", []) if isinstance(item, dict)]
        if key is not None:
            for item in memories:
                if item.get("key") == key:
                    if item.get("text") == text:
                        return ComponentResult(data=_memory_result(memories, duplicate=True))
                    return _error("相同记忆键已经记录了不同内容，不能覆盖")
        entry = {"text": text}
        if key is not None:
            entry["key"] = key
        memories.append(entry)
        limit = ctx.config.get("max_memories", 100)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            limit = 100
        if len(memories) > limit:
            memories = memories[-limit:]
        ctx.state["memories"] = memories
        return ComponentResult(data=_memory_result(memories))

    if operation == "recall":
        query = parameters.get("query") or ""
        needle = str(query).casefold()
        memories = []
        for item in ctx.state.get("memories", []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", ""))
            if not needle or needle in text.casefold():
                memories.append(dict(item))
        return ComponentResult(
            data={"query": str(query), "memories": _plain(memories), "count": len(memories)}
        )

    return _error("不支持的操作")
