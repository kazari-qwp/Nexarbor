"""双节点资源转交；成本与收据和双方记录一起提交或回滚。"""

from copy import deepcopy
import json
from pathlib import Path

from app.runtime.requester import requester_id
from domain.core import CallableTool, Module, access

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))

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


def _find_receipt(module, key):
    receipts = module.state.get("receipts") or []
    for receipt in receipts:
        if receipt.get("key") == key:
            return receipt
    return None


def _remember_receipt(module, key, fingerprint, result):
    receipts = list(module.state.get("receipts") or [])
    receipts.append({"key": key, "fingerprint": fingerprint, "result": result})
    module.state["receipts"] = receipts[-MAX_RECEIPTS:]


def _as_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TransferFailure(f"{label}不是有效数字")
    return value


def _duplicate_result(receipt):
    result = dict(receipt.get("result") or {})
    result["duplicate"] = True
    return result



async def _read_location(node):
    location = (await node.modules.get('place.info').read()).get('location')
    if location is not None and not isinstance(location, str):raise TransferFailure('地点资料格式无效')
    return location or ''


async def _read_values(node):
    return (await node.modules.get('records.store').read())['values']


async def _apply(node, deltas, expected, key):
    parameters = {'deltas':deltas}
    if expected:parameters['expected'] = expected
    if key:parameters['key'] = key
    return await node.modules.get('records.store').apply(**parameters)


class RecordsTransferModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('records.transfer', **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec['id'], self.give, spec['description'], deepcopy(spec['parameters'])))

    @access()
    async def _participants(self, node):
        return node

    async def give(self, recipient, resource, quantity, key=None):
        try:
            return next(iter((await self._give(dict(recipient=recipient, resource=resource, quantity=quantity, key=key))).values()))
        except DuplicateRequest as duplicate:
            return duplicate.result

    @access(channels=())
    async def _give(self, node, parameters):
        actor = requester_id.get() or node.info.node_id
        if actor != node.info.node_id:
            raise TransferFailure("只有资源所有者本人可以发起转交")

        if node.node_type != "agent":
            raise TransferFailure("转交只能由真实 Agent 发起")

        recipient = parameters.get("recipient")
        resource = parameters.get("resource")
        quantity = parameters.get("quantity")
        user_key = parameters.get("key")

        config = self.config
        cost = config.get("cost", 1)
        same_location = config.get("same_location", True)
        fingerprint = _fingerprint(recipient, resource, quantity, cost, bool(same_location))
        base_key = f"{self.module_id}:{node.info.node_id}:{actor}:give"
        internal_key = f"{base_key}:{user_key}" if user_key else None

        if internal_key:
            existing = _find_receipt(self, internal_key)
            if existing:
                if existing.get("fingerprint") != fingerprint:
                    raise TransferFailure("该幂等键已用于不同参数的转交")
                raise DuplicateRequest(_duplicate_result(existing))

        if recipient == node.info.node_id:
            raise TransferFailure("收件人必须是另一位真实 Agent")

        participants = await self._participants()
        target = participants.get(recipient)
        if target is None:raise TransferFailure('收件人当前不可达')
        if target.node_type != 'agent':raise TransferFailure('收件人不是真实 Agent')

        try:
            async with self.transaction([node.info.node_id, recipient], timeout=20):
                if internal_key:
                    existing = _find_receipt(self, internal_key)
                    if existing:
                        if existing.get("fingerprint") != fingerprint:
                            raise TransferFailure("该幂等键已用于不同参数的转交")
                        raise DuplicateRequest(_duplicate_result(existing))

                own_location = await _read_location(node)
                target_location = await _read_location(target)
                if same_location:
                    if not own_location or not target_location:
                        raise TransferFailure("双方地点信息为空，无法进行同地点转交")
                    if own_location != target_location:
                        raise TransferFailure("双方不在同一地点，无法转交")

                values = await _read_values(node)
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

                sender_data = await _apply(node, deltas, expected, sender_key)
                if sender_data.get("duplicate"):
                    raise TransferFailure("发送方记账出现重复，已取消转交")
                sender_values = sender_data.get("values") or {}
                remaining_ap = _as_number(
                    sender_values.get("ap", current_ap - (cost if resource != "ap" else 0)),
                    "剩余行动点",
                )

                recipient_data = await _apply(
                    target, {resource: quantity}, {}, recipient_key
                )
                if recipient_data.get("duplicate"):
                    raise TransferFailure("收件方记账出现重复，已取消转交")

                result = {
                    "from": node.info.node_id,
                    "to": recipient,
                    "resource": resource,
                    "quantity": quantity,
                    "ap": remaining_ap,
                    "duplicate": False,
                }
                if internal_key:
                    _remember_receipt(self, internal_key, fingerprint, result)
                return result
        except DuplicateRequest:
            raise
        except TransferFailure:
            raise
        except Exception as error:
            raise TransferFailure(str(error)) from error
