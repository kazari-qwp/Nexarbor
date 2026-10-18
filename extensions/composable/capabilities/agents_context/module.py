import json
from collections.abc import Mapping

from datanet.core.module_protocol import ComponentResult

OPENING_INPUT_ID = "agents.context.opening"
PUBLIC_FIELD_LABELS = {
    "name": "姓名",
    "gender": "性别",
    "profession": "职业",
    "age_group": "年龄段",
}


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


def _public_fields(config):
    fields = config.get("public_fields")
    if not isinstance(fields, (list, tuple)):
        fields = ["name", "gender", "profession", "age_group"]
    return [field for field in fields if isinstance(field, str) and field]


def _public_profile(records, config):
    """只从自己的记录中挑选配置的公开字段，其他记录一律不发布。"""
    profile = {}
    for field in _public_fields(config):
        if field in records:
            profile[field] = _plain(records[field])
    return profile


def _profile_from_metadata(metadata, config):
    """只采集其他节点在本模块命名空间发布的配置字段。"""
    if not isinstance(metadata, Mapping):
        return {}
    extensions = metadata.get("extensions")
    if not isinstance(extensions, Mapping):
        return {}
    namespace = extensions.get("agents.context")
    if not isinstance(namespace, Mapping):
        return {}
    profile = {}
    for field in _public_fields(config):
        if field in namespace:
            profile[field] = _plain(namespace[field])
    return profile


async def _nearby_values(ctx):
    raw = await ctx.network.nodes(channels=["movement"])
    entries = list(raw or [])
    nearby = []
    for entry in entries:
        item = _plain(entry)
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, list):
            path = []
        node_id = item.get("id") or item.get("node_id") or (path[-1] if path else "")
        if not node_id or str(node_id) == ctx.node_id:
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        profile = _profile_from_metadata(metadata, ctx.config)
        host_name = ""
        # Agent 的名称只能来自其公开资料；地点等普通节点可显示宿主节点名。
        if metadata.get("node_type") != "agent":
            node_name = metadata.get("name")
            if isinstance(node_name, str):
                host_name = node_name
        profile_name = profile.get("name")
        if not isinstance(profile_name, str):
            profile_name = ""
        strength = item.get("strength", 0)
        if not isinstance(strength, (int, float)) or isinstance(strength, bool):
            strength = 0
        nearby.append(
            {
                "id": str(node_id),
                "name": profile_name or host_name,
                "path": [str(part) for part in path],
                "strength": strength,
                "profile": profile,
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
    map_text = config.get("map") or ""
    if isinstance(map_text, str) and map_text.strip():
        context.append({"id": "map", "text": map_text})
    context.extend(_knowledge_context(config, records))
    return context


def _display_value(value):
    if isinstance(value, str):
        return value
    try:
        return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return "无法显示"


def _display_profile(profile):
    parts = []
    for field, value in profile.items():
        label = PUBLIC_FIELD_LABELS.get(field, field)
        parts.append(f"{label}：{_display_value(value)}")
    return "；".join(parts)


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
            label = item["name"] or item["id"]
            profile_text = _display_profile(item.get("profile") or {})
            if profile_text:
                descriptions.append(
                    f"{label}（{profile_text}；路径 {path_text}，强度 {item['strength']}）"
                )
            else:
                descriptions.append(
                    f"{label}（公开资料未提供；路径 {path_text}，强度 {item['strength']}）"
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
        "context": _context(config, records),
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
