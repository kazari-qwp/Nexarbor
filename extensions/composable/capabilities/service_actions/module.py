import json
import random

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

RECEIPT_LIMIT = 200


def _error_of(result):
    if not isinstance(result, dict):
        return "记录仓返回了无效结果"
    return str(result.get("error") or "记录仓操作失败")


async def _read_store(ctx, node):
    result = await ctx.network.call(node, "records.store", "read", {})
    if result.get("status") != "ok":
        raise RuntimeError(_error_of(result))
    data = result.get("data") or {}
    values = data.get("values")
    if not isinstance(values, dict):
        raise RuntimeError("记录仓没有返回有效记录")
    return dict(values)


async def _apply_store(ctx, node, deltas, key=None):
    payload = {"deltas": dict(deltas)}
    if key:
        payload["key"] = key
    result = await ctx.network.call(node, "records.store", "apply", payload)
    if result.get("status") != "ok":
        raise RuntimeError(_error_of(result))
    data = result.get("data") or {}
    values = data.get("values")
    if not isinstance(values, dict):
        raise RuntimeError("记录仓没有返回有效记录")
    return dict(values), bool(data.get("duplicate"))


def _merge(target, extra, factor=1):
    for field, amount in extra.items():
        number = amount * factor
        target[field] = target.get(field, 0) + number


def _check_available(label, values, deltas):
    for field, amount in deltas.items():
        if amount >= 0:
            continue
        current = values.get(field, 0)
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            raise RuntimeError(f"{label}的“{field}”不是数字，无法结算")
        if current + amount < 0:
            raise RuntimeError(f"{label}的“{field}”不足")


def _fingerprint(actor, action, quantity):
    return json.dumps(
        {"actor": actor, "action": action, "quantity": quantity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _store_key(ctx, requester, key, step):
    # 记录仓的去重键必须区分模块实例、服务节点、原始请求者、用户键和结算步骤，
    # 否则同一 Agent 在两家商店使用相同用户键，或两个 Agent 使用相同键时会错误复用回执。
    return json.dumps(
        [ctx.module_id, ctx.node_id, requester, key, step],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _find_action(ctx, action_id):
    for raw in ctx.config.get("actions", ()) or ():
        action = thaw(raw)
        if action.get("id") == action_id:
            return action
    raise RuntimeError(f"未配置动作“{action_id}”")


async def _check_location(ctx, requester, address):
    if not address:
        return
    result = await ctx.network.call(requester, "place.info", "read", {})
    if result.get("status") != "ok":
        raise RuntimeError("无法核验请求者位置：" + _error_of(result))
    data = result.get("data") or {}
    location = data.get("location")
    if location != address:
        raise RuntimeError(f"当前位置“{location or '未知'}”不是业务地址“{address}”")


async def _requester(ctx):
    requester = getattr(ctx, "requester_id", None)
    if not isinstance(requester, str) or not requester:
        raise RuntimeError("无法确认请求者 Agent 身份")
    if requester == ctx.node_id:
        raise RuntimeError("请求者不能是业务服务节点本身")
    try:
        metadata = await ctx.network.metadata(requester)
    except Exception as error:
        raise RuntimeError("无法核验请求者 Agent 身份：" + str(error)) from error
    if not isinstance(metadata, dict) or metadata.get("node_type") != "agent":
        raise RuntimeError("请求者不是可识别的 Agent")
    return requester


async def _perform_locked(ctx, parameters):
    requester = await _requester(ctx)
    action_id = parameters["action"]
    quantity = parameters.get("quantity", 1)
    key = parameters.get("key")

    action = _find_action(ctx, action_id)
    fingerprint = _fingerprint(requester, action_id, quantity)

    receipts = list(ctx.state.get("receipts") or [])
    if key:
        for receipt in reversed(receipts):
            if receipt.get("key") != key:
                continue
            old = thaw(receipt.get("result") or {})
            # 本地回执按原始请求者和用户键隔离；其他 Agent 使用相同用户键互不冲突。
            if old.get("actor") != requester:
                continue
            if receipt.get("fingerprint") != fingerprint:
                raise RuntimeError("幂等键已用于不同的动作、数量或请求者")
            old["duplicate"] = True
            return old

    address = ctx.config.get("address")
    await _check_location(ctx, requester, address)

    actor_values = await _read_store(ctx, requester)
    local_values = await _read_store(ctx, ctx.node_id)

    required_home = action.get("required_home")
    if required_home and actor_values.get("home") != required_home:
        raise RuntimeError(f"该动作要求住所“{required_home}”")

    actor_deltas = {}
    local_deltas = {}
    _merge(actor_deltas, action.get("actor_deltas") or {}, quantity)
    _merge(local_deltas, action.get("local_deltas") or {}, quantity)

    cost = action.get("cost", 1)
    per_unit = bool(action.get("per_unit_cost", False))
    total_cost = cost * quantity if per_unit else cost
    if total_cost:
        actor_deltas["ap"] = actor_deltas.get("ap", 0) - total_cost

    _check_available("请求者记录", actor_values, actor_deltas)
    _check_available("场所库存", local_values, local_deltas)

    event_counts = dict(ctx.state.get("event_counts") or {})
    triggered = []
    reward_deltas = {}
    for raw in ctx.config.get("events", ()) or ():
        event = thaw(raw)
        event_id = event["id"]
        limit = event.get("limit")
        used = int(event_counts.get(event_id, 0))
        if limit is not None and used >= limit:
            continue
        probability = event.get("probability", 0)
        if random.random() < probability:
            triggered.append(event)
            event_counts[event_id] = used + 1
            _merge(reward_deltas, event.get("rewards") or {}, quantity)
    _merge(actor_deltas, reward_deltas)

    _check_available("请求者记录", actor_values, actor_deltas)

    # 先写入事件计数再执行两次记录仓变更；任何一次失败都会抛出并从锁内整体回滚。
    ctx.state["event_counts"] = event_counts
    local_key = _store_key(ctx, requester, key, "local") if key else None
    actor_key = _store_key(ctx, requester, key, "actor") if key else None
    _, local_duplicate = await _apply_store(
        ctx,
        ctx.node_id,
        local_deltas,
        local_key,
    )
    final_values, actor_duplicate = await _apply_store(
        ctx,
        requester,
        actor_deltas,
        actor_key,
    )

    title = action.get("title") or action_id
    observation = [f"完成“{title}”×{quantity}"]
    if total_cost:
        observation.append(f"消耗行动点{total_cost}")
    for event in triggered:
        observation.append(str(event.get("text") or ""))
    if reward_deltas:
        pieces = [f"{field}{amount:+g}" for field, amount in reward_deltas.items()]
        observation.append("事件奖励：" + "，".join(pieces))

    response = {
        "action": action_id,
        "quantity": quantity,
        "actor": requester,
        "values": final_values,
        "observation": observation,
        "duplicate": bool(local_duplicate or actor_duplicate),
    }

    if key:
        receipts.append({"key": key, "fingerprint": fingerprint, "result": response})
        ctx.state["receipts"] = receipts[-RECEIPT_LIMIT:]
    return response


async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="不支持的请求")

    if activation.operation == "inspect":
        try:
            inventory = await _read_store(ctx, ctx.node_id)
        except Exception as error:
            return ComponentResult(status="error", error=str(error))
        return ComponentResult(
            data={
                "actions": [thaw(action) for action in (ctx.config.get("actions", ()) or ())],
                "inventory": inventory,
            }
        )

    if activation.operation == "perform":
        parameters = activation.parameters
        try:
            requester = await _requester(ctx)
            lock_nodes = sorted({ctx.node_id, requester})
            async with ctx.network.lock_nodes(lock_nodes, timeout=20):
                response = await _perform_locked(ctx, parameters)
        except Exception as error:
            return ComponentResult(status="error", error=str(error))
        return ComponentResult(data=response)

    return ComponentResult(status="error", error="不支持的请求")
