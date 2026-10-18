import copy
import json
import math

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

CHANNELS = ('records',)
MAX_RECEIPTS = 200
LOCK_TIMEOUT = 20


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _json_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_number(left) or _is_number(right):
        return _is_number(left) and _is_number(right) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False
        return all(_json_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    return False


def _fingerprint(request):
    return json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def _config_value(ctx, name, default):
    value = ctx.config.get(name)
    return default if value is None else thaw(value)


def _normalize_references(items, label):
    """把引用数组规范成私有字典副本，并拒绝重复键或非法节点 ID。"""
    if not isinstance(items, (list, tuple)):
        raise ValueError(f'{label} 必须是数组')
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f'{label} 的每一项必须是包含 key 和 node_id 的对象')
        key = item.get('key')
        node_id = item.get('node_id')
        if not isinstance(key, str) or not key:
            raise ValueError(f'{label} 中的 key 必须是非空字符串')
        if key in seen:
            raise ValueError(f'{label} 中的引用键“{key}”重复')
        if node_id is not None:
            if not isinstance(node_id, str) or not node_id:
                raise ValueError(
                    f'{label} 中引用键“{key}”的 node_id 必须是节点 ID 字符串或 null'
                )
        result.append({'key': key, 'node_id': node_id})
        seen.add(key)
    return result


def _config_references(ctx):
    references = _config_value(ctx, 'references', [])
    return _normalize_references(references, '配置 references')


def _load_state_references(ctx):
    raw = thaw(ctx.state.get('references', []))
    return _normalize_references(raw, '状态 references')


def _load_records(ctx):
    """读取普通 values 与显式 references 的私有副本；首次使用时从 config 深拷贝。"""
    initial = _config_value(ctx, 'initial', {})
    if not isinstance(initial, dict):
        raise ValueError('配置 initial 必须是 JSON 对象')

    configured_references = _config_references(ctx)
    initial_keys = set(initial)
    for item in configured_references:
        if item['key'] in initial_keys:
            raise ValueError(
                f'引用键“{item["key"]}”与配置 initial 中的普通字段同名，'
                '请把节点关系只放在 references 中'
            )

    if 'values' not in ctx.state:
        ctx.state['values'] = copy.deepcopy(initial)
    values = thaw(ctx.state['values'])
    if not isinstance(values, dict):
        raise ValueError('状态 values 已损坏，必须是 JSON 对象')

    if 'references' not in ctx.state:
        # 只有首次初始化引用表时才复制配置；之后配置变化不覆盖运行状态。
        ctx.state['references'] = copy.deepcopy(configured_references)
    references = _load_state_references(ctx)
    return values, references


def _load_receipts(ctx):
    receipts = thaw(ctx.state.get('receipts', []))
    if not isinstance(receipts, list):
        raise ValueError('状态 receipts 已损坏，必须是数组')
    return receipts


def _minimum(ctx):
    minimum = _config_value(ctx, 'minimum', {})
    if not isinstance(minimum, dict):
        raise ValueError('配置 minimum 必须是数字字典')
    for field, value in minimum.items():
        if not _is_number(value):
            raise ValueError(f'配置 minimum 的字段“{field}”必须是数字')
    return minimum


def _merged_view(values, references):
    """普通 values 与显式 references 按 key 合并后的业务视图。"""
    view = copy.deepcopy(values)
    for item in references:
        view[item['key']] = item['node_id']
    return view


def _reference_map(references):
    return {item['key']: item for item in references}


def _check_reference_value(key, value):
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f'引用字段“{key}”必须是节点 ID 字符串或 null')
    return value


def _request_parts(parameters):
    set_values = thaw(parameters.get('set', {}))
    deltas = thaw(parameters.get('deltas', {}))
    expected = thaw(parameters.get('expected', {}))
    reference_items = thaw(parameters.get('references', []))
    key = parameters.get('key')

    for label, value in (('set', set_values), ('deltas', deltas), ('expected', expected)):
        if not isinstance(value, dict):
            raise ValueError(f'参数 {label} 必须是 JSON 对象')
    for field, delta in deltas.items():
        if not _is_number(delta):
            raise ValueError(f'字段“{field}”的增减值必须是数字，布尔值不能当作数字')
    if key is not None and not isinstance(key, str):
        raise ValueError('参数 key 必须是字符串')
    references = _normalize_references(reference_items, '参数 references')
    for item in references:
        _check_reference_value(item['key'], item['node_id'])
    return set_values, deltas, expected, references, key


async def _read(ctx):
    async with ctx.network.lock_nodes([ctx.node_id], timeout=LOCK_TIMEOUT):
        values, references = _load_records(ctx)
        return ComponentResult(data={'values': _merged_view(values, references)})


async def _apply(ctx, parameters):
    set_values, deltas, expected, reference_items, key = _request_parts(parameters)
    request = {
        'set': set_values,
        'deltas': deltas,
        'expected': expected,
        'references': reference_items,
    }
    fingerprint = _fingerprint(request)

    async with ctx.network.lock_nodes([ctx.node_id], timeout=LOCK_TIMEOUT):
        values, references = _load_records(ctx)
        receipts = _load_receipts(ctx)

        if key is not None:
            for receipt in reversed(receipts):
                if receipt.get('key') != key:
                    continue
                if receipt.get('fingerprint') != fingerprint:
                    raise ValueError(
                        f'去重键“{key}”已用于不同请求，请更换 key 或保持参数一致'
                    )
                snapshot_values = thaw(receipt.get('values', {}))
                if not isinstance(snapshot_values, dict):
                    raise ValueError('回执 values 已损坏，必须是 JSON 对象')
                snapshot_references = _normalize_references(
                    thaw(receipt.get('references', [])), '回执 references'
                )
                return ComponentResult(
                    data={
                        'values': _merged_view(snapshot_values, snapshot_references),
                        'duplicate': True,
                    }
                )

        # 显式引用新增或更新：不能与普通 values 字段同名。
        for item in reference_items:
            if item['key'] in values:
                raise ValueError(
                    f'引用键“{item["key"]}”与普通记录字段同名，'
                    '请把节点关系只放在 references 中'
                )

        next_references = copy.deepcopy(references)
        next_map = _reference_map(next_references)
        # expected 针对变更前的普通 values 与显式引用合并视图核验。
        merged_before = _merged_view(values, references)
        for field, expected_value in expected.items():
            if field not in merged_before:
                raise ValueError(f'期望字段“{field}”不存在，无法核验')
            if not _json_equal(merged_before[field], expected_value):
                raise ValueError(
                    f'字段“{field}”的当前值与 expected 不一致，操作已取消'
                )

        for item in reference_items:
            if item['key'] in next_map:
                next_map[item['key']]['node_id'] = item['node_id']
            else:
                created = {'key': item['key'], 'node_id': item['node_id']}
                next_references.append(created)
                next_map[item['key']] = created

        next_values = copy.deepcopy(values)
        changed_values = set()
        for field, value in set_values.items():
            if field in next_map:
                next_map[field]['node_id'] = _check_reference_value(field, value)
                continue
            next_values[field] = copy.deepcopy(value)
            changed_values.add(field)

        for field, delta in deltas.items():
            if field in next_map:
                raise ValueError(f'引用字段“{field}”不能做数值增减')
            current = next_values[field] if field in next_values else 0
            if not _is_number(current):
                raise ValueError(f'字段“{field}”当前不是数字，不能增减')
            next_values[field] = current + delta
            changed_values.add(field)

        minimum = _minimum(ctx)
        for field, floor in minimum.items():
            if field not in changed_values or field not in next_values:
                continue
            value = next_values[field]
            if not _is_number(value):
                raise ValueError(f'字段“{field}”不是数字，不能校验最低值')
            if value < floor:
                raise ValueError(
                    f'字段“{field}”为 {value}，低于最低值 {floor}，操作已取消'
                )

        ctx.state['values'] = next_values
        ctx.state['references'] = next_references
        merged_after = _merged_view(next_values, next_references)
        if key is not None:
            receipts.append(
                {
                    'key': key,
                    'fingerprint': fingerprint,
                    'values': thaw(next_values),
                    'references': thaw(next_references),
                }
            )
            ctx.state['receipts'] = receipts[-MAX_RECEIPTS:]
        return ComponentResult(
            data={'values': merged_after, 'duplicate': False}
        )


async def execute(ctx, activation):
    if activation.kind != 'access':
        return ComponentResult(status='error', error='局部记录仓只接受访问请求')

    try:
        if activation.operation == 'read':
            return await _read(ctx)
        if activation.operation == 'apply':
            return await _apply(ctx, activation.parameters)
        return ComponentResult(
            status='error', error=f'不支持的请求：{activation.operation}'
        )
    except Exception as error:
        return ComponentResult(status='error', error=str(error))
