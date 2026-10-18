import json
from collections.abc import Mapping

from datanet.core.module_protocol import ComponentResult

OPENING_INPUT_ID = "agents.context.opening"


def _error(message):
    return ComponentResult(status="error", error=message)


def _plain(value):
    """把冻结的 JSON 配置/结果转成普通可序列化的值。"""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


async def _call(ctx, node_id, module_id, operation, parameters=None):
    result = await ctx.network.call(node_id, module_id, operation, parameters or {})
    if result.get("status") != "ok":
        raise RuntimeError(result.get("error") or f"无法调用 {module_id}.{operation}")
    return _plain(result.get("data") or {})


async def _memory_values(ctx):
    records = await _call(ctx, ctx.node_id, "records.store", "read")
    values = records.get("values")
    if not isinstance(values, dict):
        values = {}
    return values


async def _place_values(ctx):
    place = await _call(ctx, ctx.node_id, "place.info", "read")
    if not isinstance(place, dict):
        place = {}
    return place


async def _nearby_values(ctx):
    raw = await ctx.network.nodes(channels=["movement"])
    if isinstance(raw, Mapping):
        raw = raw.get("nodes", [])
    entries = list(raw or [])
    nearby = []
    for entry in entries:
        item = _plain(entry)
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        path = item.get("path")
        if not isinstance(path, list):
            path = []
        node_id = item.get("id") or item.get("node_id") or (path[-1] if path else "")
        if not node_id or str(node_id) == ctx.node_id:
            continue
        name = metadata.get("name") or metadata.get("title") or str(node_id)
        strength = item.get("strength", 0)
        if not isinstance(strength, (int, float)) or isinstance(strength, bool):
            strength = 0
        nearby.append(
            {
                "id": str(node_id),
                "name": str(name),
                "path": [str(part) for part in path],
                "strength": strength,
            }
        )
    nearby.sort(key=lambda item: (item["name"], item["id"]))
    return nearby


async def _clock_values(ctx, config):
    clock_id = config.get("clock")
    if not clock_id:
        return None
    data = await _call(ctx, str(clock_id), "clock.counter", "read")
    tick = data.get("tick", 0)
    day = data.get("day", 1)
    slot = data.get("slot", "")
    if not isinstance(tick, int) or isinstance(tick, bool):
        tick = 0
    if not isinstance(day, int) or isinstance(day, bool):
        day = 1
    return {"tick": tick, "day": day, "slot": str(slot)}


def _system_prompt(config):
    parts = []
    for key in ("persona", "common"):
        text = config.get(key) or ""
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def _context(config):
    map_text = config.get("map") or ""
    if isinstance(map_text, str) and map_text.strip():
        return [{"id": "map", "text": map_text}]
    return []


def _tail(records, place, nearby, clock):
    try:
        account = json.dumps(records, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        account = "无法显示"
    if records:
        tail = [f"个人记录：{account}"]
    else:
        tail = ["个人记录：暂无"]

    location = place.get("location")
    tail.append(f"当前位置：{location}" if location else "当前位置：未知")

    if nearby:
        descriptions = []
        for item in nearby:
            path_text = "→".join(item["path"]) if item["path"] else item["id"]
            descriptions.append(
                f"{item['name']}（{item['id']}，路径 {path_text}，强度 {item['strength']}）"
            )
        tail.append("附近可达：" + "；".join(descriptions))
    else:
        tail.append("附近可达：无可达地点")

    if clock is not None:
        tail.append(f"当前时间：第{clock['day']}天 {clock['slot']}（计数 {clock['tick']}）")
    return tail


async def _snapshot(ctx):
    config = ctx.config
    records = await _memory_values(ctx)
    place = await _place_values(ctx)
    nearby = await _nearby_values(ctx)
    clock = await _clock_values(ctx, config)
    memories = _plain(ctx.state.get("memories", []))
    if not isinstance(memories, list):
        memories = []
    return {
        "system_prompt": _system_prompt(config),
        "context": _context(config),
        "tail": _tail(records, place, nearby, clock),
        "location": place.get("location") if isinstance(place.get("location"), str) else None,
        "nearby": nearby,
        "clock": clock,
        "records": records,
        "memories": memories,
        "opening_queued": bool(ctx.state.get("opening_queued", False)),
    }


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
            return ComponentResult(data=await _snapshot(ctx))
        except RuntimeError as exc:
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
