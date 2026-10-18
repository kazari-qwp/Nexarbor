import json
import uuid
from collections.abc import Mapping

from datanet.core.module_protocol import ComponentResult


def _node_type(metadata):
    """从宿主元数据中取出核心节点类型；未知时返回 None。"""
    if not isinstance(metadata, Mapping):
        return None
    if "node_type" in metadata:
        return metadata.get("node_type")
    for field in ("metadata", "node", "info"):
        inner = metadata.get(field)
        if isinstance(inner, Mapping) and "node_type" in inner:
            return inner.get("node_type")
    return None


async def _read_metadata(ctx, node_id):
    """只通过 ctx 读取节点公开元数据；查询失败由调用方按拒绝处理。"""
    if node_id == ctx.node_id:
        value = ctx.metadata()
    else:
        value = ctx.network.metadata(node_id)
    if hasattr(value, "__await__"):
        value = await value
    return value


def _clip(value, maximum):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return maximum
    return min(value, maximum)


async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="消息与讨论箱只处理访问请求")

    operation = activation.operation
    parameters = activation.parameters
    config = ctx.config

    read_policy = config.get("read_policy", "self")
    send_cost = config.get("send_cost", 0)
    max_messages = _clip(config.get("max_messages", 200), 1000000)
    require_agent = config.get("require_agent", True)
    seen_limit = max(max_messages, 200)

    if operation == "read":
        limit = parameters.get("limit", 20)
        requester = ctx.requester_id
        if read_policy != "reachable" and requester != ctx.node_id:
            return ComponentResult(
                status="error",
                error="该消息箱仅允许所在节点自己读取",
            )
        messages = list(ctx.state.get("messages", []))
        return ComponentResult(
            data={"messages": [dict(message) for message in messages[-limit:]]}
        )

    if operation == "clear":
        if ctx.requester_id != ctx.node_id:
            return ComponentResult(
                status="error",
                error="只有消息箱所在节点可以清理本地消息",
            )
        try:
            async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
                messages = list(ctx.state.get("messages", []))
                cleared = len(messages)
                ctx.state["messages"] = []
                ctx.state["seen"] = []
        except Exception as error:
            return ComponentResult(status="error", error=str(error))
        return ComponentResult(data={"cleared": cleared})

    if operation != "send":
        return ComponentResult(status="error", error="不支持的消息箱操作")

    sender = ctx.requester_id
    if not sender:
        return ComponentResult(status="error", error="无法确认消息发送者")

    text = parameters.get("text")
    topic = parameters.get("topic", "")
    request_key = parameters.get("key")
    if not isinstance(text, str) or not text:
        return ComponentResult(status="error", error="消息正文不能为空")
    if not isinstance(topic, str):
        return ComponentResult(status="error", error="话题必须是字符串")
    if request_key is not None and not isinstance(request_key, str):
        return ComponentResult(status="error", error="去重键必须是字符串")

    fingerprint = json.dumps(
        {"text": text, "topic": topic},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    dedupe_key = None
    if request_key is not None:
        dedupe_key = json.dumps(
            [sender, request_key],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    result = None
    try:
        lock_ids = [ctx.node_id]
        if send_cost > 0 and sender != ctx.node_id:
            lock_ids.append(sender)

        async with ctx.network.lock_nodes(lock_ids, timeout=20):
            metadata = await _read_metadata(ctx, sender)
            if metadata is None:
                raise RuntimeError("无法确认消息发送者，拒绝发送")
            if require_agent and _node_type(metadata) != "agent":
                raise RuntimeError("只有真实 Agent 节点可以发送消息")

            messages = list(ctx.state.get("messages", []))
            seen = list(ctx.state.get("seen", []))

            if dedupe_key is not None:
                for receipt in reversed(seen):
                    if receipt.get("key") != dedupe_key:
                        continue
                    if receipt.get("fingerprint") != fingerprint:
                        raise RuntimeError("相同去重键不能发送不同内容")
                    result = {
                        "id": receipt.get("id"),
                        "from": sender,
                        "to": ctx.node_id,
                        "text": text,
                        "topic": topic,
                        "duplicate": True,
                        "ap": None,
                    }
                    break

            if result is None:
                message_id = uuid.uuid4().hex
                ap = None
                if send_cost > 0:
                    account = await ctx.network.call(
                        sender, "records.store", "read", {}
                    )
                    if account.get("status") != "ok":
                        raise RuntimeError(
                            account.get("error", "读取行动点失败")
                        )
                    available = account.get("data", {}).get("values", {}).get("ap")
                    if (
                        not isinstance(available, (int, float))
                        or isinstance(available, bool)
                        or available < send_cost
                    ):
                        raise RuntimeError("行动点不足，无法发送消息")

                    record_key = json.dumps(
                        [
                            ctx.module_id,
                            ctx.node_id,
                            sender,
                            "send",
                            request_key if request_key is not None else message_id,
                        ],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    charged = await ctx.network.call(
                        sender,
                        "records.store",
                        "apply",
                        {
                            "deltas": {"ap": -send_cost},
                            "key": record_key,
                        },
                    )
                    if charged.get("status") != "ok":
                        raise RuntimeError(charged.get("error", "扣除行动点失败"))
                    values = charged.get("data", {}).get("values", {})
                    ap = values.get("ap")

                message = {
                    "id": message_id,
                    "from": sender,
                    "to": ctx.node_id,
                    "text": text,
                    "topic": topic,
                }
                messages.append(message)
                if len(messages) > max_messages:
                    messages = messages[-max_messages:]
                if dedupe_key is not None:
                    seen.append(
                        {
                            "key": dedupe_key,
                            "fingerprint": fingerprint,
                            "id": message_id,
                        }
                    )
                    if len(seen) > seen_limit:
                        seen = seen[-seen_limit:]
                ctx.state["messages"] = messages
                ctx.state["seen"] = seen
                result = {
                    "id": message_id,
                    "from": sender,
                    "to": ctx.node_id,
                    "text": text,
                    "topic": topic,
                    "duplicate": False,
                    "ap": ap,
                }
    except Exception as error:
        return ComponentResult(status="error", error=str(error))

    return ComponentResult(data=result)
