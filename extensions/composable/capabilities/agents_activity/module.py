from datanet.core.module_protocol import ComponentResult

MAX_ACTIVITY_KEYS = 200
LOCK_TIMEOUT_SECONDS = 15


class ActivityRejected(Exception):
    """活动键状态不允许继续执行。"""


def _activity_entries(ctx):
    entries = ctx.state.get('activities', [])
    return [dict(item) for item in entries if isinstance(item, dict)]


def _find_activity(ctx, key):
    for entry in _activity_entries(ctx):
        if entry.get('key') == key:
            return entry
    return None


def _upsert_activity(ctx, entry):
    entries = [item for item in _activity_entries(ctx) if item.get('key') != entry.get('key')]
    entries.append(dict(entry))
    ctx.state['activities'] = entries[-MAX_ACTIVITY_KEYS:]


def _result(ctx, key, status, duplicate, budget_field, budget, entry=None, reason=None):
    entry = entry or {}
    data = {
        'key': key,
        'status': status,
        'duplicate': bool(duplicate),
        'budget_field': budget_field,
        'budget': budget,
        'completed_count': int(entry.get('completed_count', 0) or 0),
        'completed_total': int(ctx.state.get('completed_total', 0) or 0),
    }
    if reason:
        data['reason'] = reason
    return data


def _lock_self(ctx, timeout=LOCK_TIMEOUT_SECONDS):
    # 角色只锁自己，锁定范围不随信号源或调用者扩大。
    return ctx.network.lock_nodes([ctx.node_id], timeout=timeout)


def _signal_key(activation):
    signal = getattr(activation, 'signal', None)
    key = getattr(signal, 'signal_id', None) if signal is not None else None
    if not isinstance(key, str) or not key.strip():
        raise ActivityRejected('信号缺少有效的 signal_id，无法作为活动键')
    return key


def _access_key(activation):
    key = activation.parameters.get('key')
    if not isinstance(key, str) or not key.strip():
        raise ActivityRejected('活动键必须是非空字符串')
    return key


async def _records_apply(ctx, budget_field, budget):
    result = await ctx.network.call(
        ctx.node_id,
        'records.store',
        'apply',
        {'set': {budget_field: budget}},
        channels=['records'],
    )
    if not isinstance(result, dict) or result.get('status') != 'ok':
        error = result.get('error') if isinstance(result, dict) else '记录仓没有返回结果'
        raise RuntimeError(f'重置行动预算失败：{error}')
    values = (result.get('data') or {}).get('values') or {}
    if values.get(budget_field) != budget:
        raise RuntimeError('记录仓未按预期写入行动预算')


async def _prepare_context(ctx):
    result = await ctx.network.call(
        ctx.node_id,
        'agents.context',
        'prepare',
        {},
        channels=['self'],
    )
    if not isinstance(result, dict) or result.get('status') != 'ok':
        error = result.get('error') if isinstance(result, dict) else '上下文准备没有返回结果'
        raise RuntimeError(f'准备角色上下文失败：{error}')


async def _run_agent(ctx, prompt):
    # 官方端口只运行本节点，工具由宿主从本节点自己的工具收集器取得。
    try:
        return await ctx.network.invoke(
            ctx.node_id,
            'runtime:agent_run',
            {'message': prompt},
            channels=['runtime.agent'],
        )
    except Exception as error:
        raise RuntimeError(f'运行官方端口 runtime:agent_run 失败：{error}') from error


async def _mark_completed(ctx, key, budget_field, budget):
    async with _lock_self(ctx):
        existing = _find_activity(ctx, key) or {}
        if existing.get('status') == 'completed':
            return _result(ctx, key, 'completed', True, budget_field, budget, existing)
        count = int(existing.get('completed_count', 0) or 0) + 1
        entry = {
            'key': key,
            'status': 'completed',
            'completed_count': count,
        }
        _upsert_activity(ctx, entry)
        total = int(ctx.state.get('completed_total', 0) or 0) + 1
        ctx.state['completed_total'] = total
        ctx.publish_metadata({
            '活动状态': '已完成',
            '最近完成活动键': key,
            '活动完成次数': total,
        })
        return _result(ctx, key, 'completed', False, budget_field, budget, entry)


async def _mark_failed(ctx, key, message):
    text = str(message)[:2000]
    try:
        async with _lock_self(ctx):
            existing = _find_activity(ctx, key) or {}
            if existing.get('status') == 'completed':
                return
            entry = dict(existing)
            entry['key'] = key
            entry['status'] = 'failed'
            entry['error'] = text
            entry.setdefault('completed_count', 0)
            _upsert_activity(ctx, entry)
    except Exception:
        # 记录失败状态是尽力而为，不能覆盖最初的业务失败。
        return


async def _run_activity(ctx, key):
    budget_field = str(ctx.config.get('budget_field', 'ap') or 'ap')
    budget = int(ctx.config.get('budget', 10))
    prompt = str(ctx.config.get('prompt', '') or '')

    started = False
    try:
        async with _lock_self(ctx):
            existing = _find_activity(ctx, key)
            if existing is not None:
                status = existing.get('status')
                if status == 'completed':
                    return _result(
                        ctx, key, 'completed', True,
                        budget_field, budget, existing,
                    )
                if status == 'running':
                    raise ActivityRejected('该活动键正在执行，拒绝重放半轮活动')
                raise ActivityRejected('该活动键上次执行失败，拒绝自动重放；请使用新的活动键')

            await _records_apply(ctx, budget_field, budget)
            _upsert_activity(ctx, {
                'key': key,
                'status': 'running',
                'completed_count': int((existing or {}).get('completed_count', 0) or 0),
            })
            started = True
    except Exception as error:
        if started:
            await _mark_failed(ctx, key, error)
        raise

    try:
        await _prepare_context(ctx)
        # 模型运行必须在释放独占锁之后进行。
        await _run_agent(ctx, prompt)
    except Exception as error:
        await _mark_failed(ctx, key, error)
        raise

    try:
        return await _mark_completed(ctx, key, budget_field, budget)
    except Exception as error:
        await _mark_failed(ctx, key, f'记录活动完成状态失败：{error}')
        raise


async def execute(ctx, activation):
    is_signal = activation.kind == 'signal'
    try:
        if activation.kind == 'signal':
            key = _signal_key(activation)
        elif activation.kind == 'access' and activation.operation == 'activate':
            key = _access_key(activation)
        else:
            raise ActivityRejected('不支持的请求')

        if not bool(ctx.config.get('enabled', False)):
            budget_field = str(ctx.config.get('budget_field', 'ap') or 'ap')
            budget = int(ctx.config.get('budget', 10))
            existing = _find_activity(ctx, key)
            return ComponentResult(data=_result(
                ctx, key, 'skipped', False, budget_field, budget, existing,
                reason='角色活动已禁用',
            ))

        return ComponentResult(data=await _run_activity(ctx, key))
    except ActivityRejected as error:
        if is_signal:
            raise
        return ComponentResult(status='error', error=str(error))
    except Exception as error:
        if is_signal:
            raise
        return ComponentResult(status='error', error=f'角色活动失败：{error}')
