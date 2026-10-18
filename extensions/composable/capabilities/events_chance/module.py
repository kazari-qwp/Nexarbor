import random

from datanet.core.module_protocol import ComponentResult


def _event_entries(config):
    """读取并校验事件配置，返回普通 Python 列表。"""
    events = config.get("events", [])
    if not isinstance(events, (list, tuple)):
        raise ValueError("事件配置必须是数组")

    normalized = []
    seen = set()
    for index, raw in enumerate(events, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 项事件必须是对象")
        event_id = raw.get("id")
        text = raw.get("text")
        probability = raw.get("probability", 0)
        limit = raw.get("limit")
        rewards = raw.get("rewards", {})

        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"第 {index} 项事件缺少有效的事件标识")
        if event_id in seen:
            raise ValueError(f"事件标识重复：{event_id}")
        if not isinstance(text, str) or not text:
            raise ValueError(f"事件 {event_id} 缺少有效的事件文字")
        if (
            not isinstance(probability, (int, float))
            or isinstance(probability, bool)
            or probability < 0
            or probability > 1
        ):
            raise ValueError(f"事件 {event_id} 的触发概率必须在 0 到 1 之间")
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
        ):
            raise ValueError(f"事件 {event_id} 的成功次数上限必须是正整数或 null")
        if not isinstance(rewards, dict):
            raise ValueError(f"事件 {event_id} 的奖励必须是数字映射")

        clean_rewards = {}
        for field, amount in rewards.items():
            if (
                not isinstance(field, str)
                or not field
                or not isinstance(amount, (int, float))
                or isinstance(amount, bool)
                or amount < 0
            ):
                raise ValueError(f"事件 {event_id} 的奖励字段和数值必须是非负数字映射")
            clean_rewards[field] = amount

        seen.add(event_id)
        normalized.append(
            {
                "id": event_id,
                "text": text,
                "probability": probability,
                "limit": limit,
                "rewards": clean_rewards,
            }
        )
    return normalized


def _node_entry_id(entry):
    if not isinstance(entry, dict):
        return None
    for key in ("id", "node_id"):
        value = entry.get(key)
        if isinstance(value, str):
            return value
    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        for key in ("id", "node_id"):
            value = metadata.get(key)
            if isinstance(value, str):
                return value
    return None


def _node_entry_type(entry):
    if not isinstance(entry, dict):
        return None
    value = entry.get("node_type")
    if isinstance(value, str):
        return value
    for key in ("metadata", "node"):
        nested = entry.get(key)
        if isinstance(nested, dict):
            value = nested.get("node_type")
            if isinstance(value, str):
                return value
    return None


async def _requester_node_type(ctx, requester_id):
    """从可达节点资料中确认请求者的真实核心节点类型。"""
    nodes = await ctx.network.nodes()
    if isinstance(nodes, dict):
        for node_id, entry in nodes.items():
            if node_id == requester_id:
                if isinstance(entry, dict):
                    node_type = _node_entry_type(entry)
                    if node_type is None and entry.get("id") == requester_id:
                        node_type = entry.get("node_type")
                    return node_type
                return None
        return None
    for entry in nodes or []:
        if _node_entry_id(entry) == requester_id:
            return _node_entry_type(entry)
    return None


async def _sample(ctx):
    events = _event_entries(ctx.config)

    requester_id = getattr(ctx, "requester_id", None)
    if not isinstance(requester_id, str) or not requester_id:
        raise ValueError("缺少真实请求者，不能抽取地点事件")
    if requester_id == ctx.node_id:
        raise PermissionError("请求者不能是地点事件节点自身")

    requester_type = await _requester_node_type(ctx, requester_id)
    if requester_type != "agent":
        raise PermissionError("只有真实 Agent 请求者才能抽取地点事件")

    observations = []
    rewards = {}

    async with ctx.network.lock_nodes([ctx.node_id, requester_id], timeout=20):
        # 锁内重新读取配置与计数；次数、随机和奖励都在同一事务中完成。
        events = _event_entries(ctx.config)
        counts = ctx.state.setdefault("counts", {})
        if not isinstance(counts, dict):
            raise ValueError("事件次数状态必须是对象")
        for event in events:
            counts.setdefault(event["id"], 0)

        for event in events:
            event_id = event["id"]
            used = counts.get(event_id, 0)
            if (
                not isinstance(used, int)
                or isinstance(used, bool)
                or used < 0
            ):
                raise ValueError(f"事件 {event_id} 的成功次数状态非法")
            limit = event["limit"]
            if limit is not None and used >= limit:
                continue
            if random.random() >= event["probability"]:
                continue

            counts[event_id] = used + 1
            observations.append(event["text"])
            for field, amount in event["rewards"].items():
                rewards[field] = rewards.get(field, 0) + amount

        if rewards:
            applied = await ctx.network.call(
                requester_id,
                "records.store",
                "apply",
                {"deltas": dict(rewards)},
            )
            if not isinstance(applied, dict) or applied.get("status") != "ok":
                error = (
                    applied.get("error")
                    if isinstance(applied, dict)
                    else "请求者记录仓返回了无法识别的结果"
                )
                raise RuntimeError(f"发放事件奖励失败：{error}")

        final_counts = {
            event["id"]: int(counts.get(event["id"], 0)) for event in events
        }

    return {
        "observations": observations,
        "rewards": rewards,
        "counts": final_counts,
    }


async def execute(ctx, activation):
    if activation.kind != "access" or activation.operation != "sample":
        return ComponentResult(status="error", error="不支持的操作，只提供 sample")

    try:
        data = await _sample(ctx)
    except Exception as error:
        return ComponentResult(status="error", error=str(error))
    return ComponentResult(data=data)
