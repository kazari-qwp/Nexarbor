import json

from datanet.core.module_protocol import ComponentResult

MAX_RECEIPTS = 200


class TransferFailure(Exception):
    """可回滚的业务失败。"""


class DuplicateRequest(Exception):
    """命中已有成功回执，直接返回旧结果。"""

    def __init__(self, result):
        super().__init__("重复请求")
        self.result = result


def _fingerprint(recipient, resource, quantity, cost, same_location):
    payload = {
        "recipient": recipient,
        "resource": resource,
        "quantity": quantity,
        "cost": cost,
        "same_location": same_location,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _find_receipt(ctx, key):
    receipts = ctx.state.get("receipts") or []
    for receipt in receipts:
        if receipt.get("key") == key:
            return receipt
    return None


def _remember_receipt(ctx, key, fingerprint, result):
    receipts = list(ctx.state.get("receipts") or [])
    receipts.append({"key": key, "fingerprint": fingerprint, "result": result})
    ctx.state["receipts"] = receipts[-MAX_RECEIPTS:]


def _as_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TransferFailure(f"{label}不是有效数字")
    return value


async def _read_location(ctx, node_id):
    result = await ctx.network.call(node_id, "place.info", "read", {})
    if result.get("status") != "ok":
        raise TransferFailure(f"读取地点失败：{result.get('error', '未知错误')}")
    data = result.get("data") or {}
    location = data.get("location")
    if location is not None and not isinstance(location, str):
        raise TransferFailure("地点资料格式无效")
    return location or ""


async def _read_values(ctx, node_id):
    result = await ctx.network.call(node_id, "records.store", "read", {})
    if result.get("status") != "ok":
        raise TransferFailure(f"读取记录失败：{result.get('error', '未知错误')}")
    data = result.get("data") or {}
    values = data.get("values")
    if not isinstance(values, dict):
        raise TransferFailure("记录仓返回格式无效")
    return values


async def _apply(ctx, node_id, deltas, expected, key):
    parameters = {"deltas": deltas}
    if expected:
        parameters["expected"] = expected
    if key:
        parameters["key"] = key
    result = await ctx.network.call(node_id, "records.store", "apply", parameters)
    if result.get("status") != "ok":
        raise TransferFailure(f"记账失败：{result.get('error', '未知错误')}")
    data = result.get("data") or {}
    values = data.get("values")
    if not isinstance(values, dict):
        raise TransferFailure("记录仓记账返回格式无效")
    return data


def _duplicate_result(receipt):
    result = dict(receipt.get("result") or {})
    result["duplicate"] = True
    return result


async def _give(ctx, activation):
    if ctx.requester_id != ctx.node_id:
        raise TransferFailure("只有资源所有者本人可以发起转交")

    metadata = ctx.metadata()
    if (metadata or {}).get("node_type") != "agent":
        raise TransferFailure("转交只能由真实 Agent 发起")

    parameters = activation.parameters
    recipient = parameters.get("recipient")
    resource = parameters.get("resource")
    quantity = parameters.get("quantity")
    user_key = parameters.get("key")

    config = ctx.config
    cost = config.get("cost", 1)
    same_location = config.get("same_location", True)
    fingerprint = _fingerprint(recipient, resource, quantity, cost, bool(same_location))
    base_key = f"{ctx.module_id}:{ctx.node_id}:{ctx.requester_id}:give"
    internal_key = f"{base_key}:{user_key}" if user_key else None

    if internal_key:
        existing = _find_receipt(ctx, internal_key)
        if existing:
            if existing.get("fingerprint") != fingerprint:
                raise TransferFailure("该幂等键已用于不同参数的转交")
            raise DuplicateRequest(_duplicate_result(existing))

    if recipient == ctx.node_id:
        raise TransferFailure("收件人必须是另一位真实 Agent")

    nodes = await ctx.network.nodes()
    target_metadata = None
    for node in nodes:
        metadata = node.get("metadata") or {}
        if node.get("id") == recipient or metadata.get("node_id") == recipient:
            target_metadata = metadata
            break
    if target_metadata is None:
        raise TransferFailure("收件人当前不可达")
    if target_metadata.get("node_type") != "agent":
        raise TransferFailure("收件人不是真实 Agent")

    try:
        async with ctx.network.lock_nodes([ctx.node_id, recipient], timeout=20):
            if internal_key:
                existing = _find_receipt(ctx, internal_key)
                if existing:
                    if existing.get("fingerprint") != fingerprint:
                        raise TransferFailure("该幂等键已用于不同参数的转交")
                    raise DuplicateRequest(_duplicate_result(existing))

            own_location = await _read_location(ctx, ctx.node_id)
            target_location = await _read_location(ctx, recipient)
            if same_location:
                if not own_location or not target_location:
                    raise TransferFailure("双方地点信息为空，无法进行同地点转交")
                if own_location != target_location:
                    raise TransferFailure("双方不在同一地点，无法转交")

            values = await _read_values(ctx, ctx.node_id)
            current_resource = _as_number(values.get(resource, 0), "自己的资源数量")
            current_ap = _as_number(values.get("ap", 0), "自己的行动点")

            if resource == "ap":
                if current_resource < quantity + cost:
                    if cost > 0:
                        raise TransferFailure("资源或行动点不足")
                    raise TransferFailure("资源不足")
            else:
                if current_resource < quantity:
                    raise TransferFailure("资源不足")
                if current_ap < cost:
                    raise TransferFailure("行动点不足")

            deltas = {resource: -quantity}
            expected = {resource: current_resource}
            if resource == "ap":
                # 同一字段必须合并，不能用自己的扣减覆盖行动点成本。
                deltas["ap"] = deltas.get("ap", 0) - cost
            else:
                if "ap" in values:
                    expected["ap"] = current_ap
                if cost:
                    deltas["ap"] = -cost

            sender_key = f"{internal_key}:sender" if internal_key else None
            recipient_key = f"{internal_key}:recipient" if internal_key else None

            sender_data = await _apply(ctx, ctx.node_id, deltas, expected, sender_key)
            if sender_data.get("duplicate"):
                raise TransferFailure("发送方记账出现重复，已取消转交")
            sender_values = sender_data.get("values") or {}
            remaining_ap = _as_number(
                sender_values.get("ap", current_ap - (cost if resource != "ap" else 0)),
                "剩余行动点",
            )

            recipient_data = await _apply(
                ctx, recipient, {resource: quantity}, {}, recipient_key
            )
            if recipient_data.get("duplicate"):
                raise TransferFailure("收件方记账出现重复，已取消转交")

            result = {
                "from": ctx.node_id,
                "to": recipient,
                "resource": resource,
                "quantity": quantity,
                "ap": remaining_ap,
                "duplicate": False,
            }
            if internal_key:
                _remember_receipt(ctx, internal_key, fingerprint, result)
            return ComponentResult(data=result)
    except DuplicateRequest:
        raise
    except TransferFailure:
        raise
    except Exception as error:
        raise TransferFailure(str(error)) from error


async def execute(ctx, activation):
    if activation.kind != "access" or activation.operation != "give":
        return ComponentResult(status="error", error="不支持的请求")
    try:
        return await _give(ctx, activation)
    except DuplicateRequest as duplicate:
        return ComponentResult(data=duplicate.result)
    except TransferFailure as error:
        return ComponentResult(status="error", error=str(error))
    except Exception as error:
        return ComponentResult(status="error", error=str(error))
