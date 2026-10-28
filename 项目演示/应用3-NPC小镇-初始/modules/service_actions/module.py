"""原服务动作结算、事件与后续钩子；整单失败由双节点事务回滚。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.requester import as_caller, requester_id
from domain.core import CallableTool, Module, access
from domain.json_values import thaw

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))

import random

RECEIPT_LIMIT = 200

def _merge(target, extra, factor=1):
    for field, amount in extra.items():
        number = amount * factor
        target[field] = target.get(field, 0) + number


def _number(value, label, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{label}的“{field}”不是数字，无法结算")
    return value


def _project(values, sets, deltas):
    # 与 records.store.apply 一致：先写入 set，再按 deltas 在原值上增减。
    projected = dict(values)
    projected.update(sets)
    for field, amount in deltas.items():
        current = _number(projected.get(field, 0), "请求者记录", field)
        projected[field] = current + amount
    return projected


def _check_available(label, values, deltas, sets=None):
    projected = dict(values)
    if sets:
        projected.update(sets)
    for field, amount in deltas.items():
        if amount >= 0:
            continue
        current = _number(projected.get(field, 0), label, field)
        if current + amount < 0:
            raise RuntimeError(f"{label}的“{field}”不足")


def _same_value(left, right):
    # 按 JSON 含义比较，避免 True 与 1、字符串与数字等被 Python 宽松判等。
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _same_value(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _same_value(first, second) for first, second in zip(left, right)
        )
    return type(left) is type(right) and left == right


def _fingerprint(actor, action, quantity):
    return json.dumps(
        {"actor": actor, "action": action, "quantity": quantity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _store_key(module, node, requester, key, step):
    # 记录仓的去重键必须区分模块实例、服务节点、原始请求者、用户键和结算步骤，
    # 否则同一 Agent 在两家商店使用相同用户键，或两个 Agent 使用相同键时会错误复用回执。
    return json.dumps(
        [module.module_id, node.info.node_id, requester, key, step],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _find_action(module, action_id):
    for raw in module.config.get("actions", ()) or ():
        action = thaw(raw)
        if action.get("id") == action_id:
            return action
    raise RuntimeError(f"未配置动作“{action_id}”")



async def _read_store(participants, node_id):
    return dict((await participants[node_id].modules.get('records.store').read())['values'])


async def _apply_store(participants, node_id, deltas, key=None, sets=None):
    payload = {'deltas':dict(deltas)}
    if sets:payload['set'] = dict(sets)
    if key:payload['key'] = key
    data = await participants[node_id].modules.get('records.store').apply(**payload)
    return dict(data['values']), bool(data.get('duplicate'))


async def _check_location(participants, requester, address):
    if not address:return
    location = (await participants[requester].modules.get('place.info').read()).get('location')
    if location != address:raise RuntimeError(f"当前位置“{location or '未知'}”不是业务地址“{address}”")


async def _run_after_hooks(module, node, participants, requester, action_id):
    results = []
    for raw in module.config.get('after_hooks', ()) or ():
        hook = thaw(raw)
        actions = list(hook.get('actions') or ())
        if actions and action_id not in actions:continue
        target = hook.get('target')
        if target == 'local':node_id = node.info.node_id
        elif target == 'requester':node_id = requester
        else:raise RuntimeError(f'后续钩子目标“{target}”无效，只能是 local 或 requester')
        arguments = thaw(hook.get('arguments') or {})
        if not isinstance(arguments, dict):raise RuntimeError('后续钩子参数必须是普通对象')
        component = hook.get('module');operation = hook.get('operation')
        try:
            with as_caller(node.info.node_id):
                data = await getattr(participants[node_id].modules.get(component), operation)(**arguments)
        except Exception as error:
            raise RuntimeError(f'后续钩子“{component}.{operation}”执行失败：{error}') from error
        results.append(dict(target=target,module=component,operation=operation,data=thaw(data)))
    return results


async def _perform_locked(module, node, participants, parameters, requester):
    action_id = parameters["action"]
    quantity = parameters.get("quantity", 1)
    key = parameters.get("key")

    action = _find_action(module, action_id)
    fingerprint = _fingerprint(requester, action_id, quantity)

    receipts = list(module.state.get("receipts") or [])
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
            old["after_results"] = thaw(old.get("after_results") or [])
            old["duplicate"] = True
            return old

    address = module.config.get("address")
    await _check_location(participants, requester, address)

    actor_values = await _read_store(participants, requester)
    local_values = await _read_store(participants, node.info.node_id)

    required_home = action.get("required_home")
    if required_home and actor_values.get("home") != required_home:
        raise RuntimeError(f"该动作要求住所“{required_home}”")

    require_values = thaw(action.get("require_values") or {})
    for field, expected in require_values.items():
        if field not in actor_values or not _same_value(actor_values[field], expected):
            raise RuntimeError(
                f"该动作要求请求者记录的“{field}”为 {expected!r}，当前不满足"
            )

    require_items = thaw(action.get("require_items") or {})
    for field, amount in require_items.items():
        needed = amount * quantity
        if needed <= 0:
            continue
        current = _number(actor_values.get(field, 0), "请求者记录", field)
        if current < needed:
            raise RuntimeError(
                f"该动作需要物品“{field}”至少{needed:g}，当前只有{current:g}"
            )

    actor_sets = thaw(action.get("actor_set") or {})

    actor_deltas = {}
    local_deltas = {}
    _merge(actor_deltas, action.get("actor_deltas") or {}, quantity)
    _merge(local_deltas, action.get("local_deltas") or {}, quantity)

    cost = action.get("cost", 1)
    per_unit = bool(action.get("per_unit_cost", False))
    total_cost = cost * quantity if per_unit else cost
    if total_cost:
        actor_deltas["ap"] = actor_deltas.get("ap", 0) - total_cost

    _check_available("请求者记录", actor_values, actor_deltas, actor_sets)
    _check_available("场所库存", local_values, local_deltas)

    event_counts = dict(module.state.get("event_counts") or {})
    triggered = []
    reward_deltas = {}
    for raw in module.config.get("events", ()) or ():
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

    # 上限按与记录仓 apply 相同的“先 set 后 deltas”顺序算出最终值，事件奖励也必须计入。
    actor_final = _project(actor_values, actor_sets, actor_deltas)
    maximums = thaw(action.get("actor_maximums") or {})
    for field, cap in maximums.items():
        final = _number(actor_final.get(field, 0), "请求者记录", field)
        if final > cap:
            raise RuntimeError(
                f"请求者记录的“{field}”最终为{final:g}，超过上限{cap:g}"
            )

    # 所有检查通过后才写入事件计数，再执行两次记录仓变更；任何一次失败都会抛出并从锁内整体回滚。
    module.state["event_counts"] = event_counts
    local_key = _store_key(module, node, requester, key, "local") if key else None
    actor_key = _store_key(module, node, requester, key, "actor") if key else None
    _, local_duplicate = await _apply_store(
        participants,
        node.info.node_id,
        local_deltas,
        local_key,
    )
    final_values, actor_duplicate = await _apply_store(
        participants,
        requester,
        actor_deltas,
        actor_key,
        actor_sets,
    )

    # 本地与请求者记录都已成功写入后，仍在锁内按顺序执行后续钩子；
    # 钩子失败会抛出异常，连同业务变更、事件计数和记录仓写入一起回滚。
    after_results = await _run_after_hooks(module, node, participants, requester, action_id)

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
        "after_results": after_results,
    }

    if key:
        receipts.append({"key": key, "fingerprint": fingerprint, "result": response})
        module.state["receipts"] = receipts[-RECEIPT_LIMIT:]
    return response


class ServiceActionsModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('service.actions', **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec['id'], getattr(self, spec['operation']), spec['description'], deepcopy(spec['parameters'])))

    def _bind(self, node):
        super()._bind(node)
        source_id = sha256((node.info.node_id + '\0' + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = 'mod_' + sha256((source_id + '\0' + spec['id']).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + ' · ' + spec['name'] + ' · ' + spec['description']

    @access()
    async def _participants(self, node):
        return node


    async def inspect(self):
        return next(iter((await self._inspect()).values()))

    @access(channels=())
    async def _inspect(self, node):
        return {'actions':[thaw(action) for action in self.config.get('actions',()) or ()], 'inventory':(await node.modules.get('records.store').read())['values']}

    async def perform(self, action, quantity=1, key=None):
        return next(iter((await self._perform(dict(action=action,quantity=quantity,key=key))).values()))

    @access(channels=())
    async def _perform(self, node, parameters):
        requester = requester_id.get()
        if not isinstance(requester, str) or not requester:raise RuntimeError('无法确认请求者 Agent 身份')
        if requester == node.info.node_id:raise RuntimeError('请求者不能是业务服务节点本身')
        participants = await self._participants()
        if participants[requester].node_type != 'agent':raise RuntimeError('请求者不是可识别的 Agent')
        async with self.transaction(sorted({node.info.node_id,requester}),timeout=20):
            return await _perform_locked(self,node,participants,parameters,requester)
