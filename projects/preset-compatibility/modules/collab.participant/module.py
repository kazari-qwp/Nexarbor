from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

async def execute(ctx, activation):
    if activation.kind != 'access':
        return ComponentResult(status='error', error='成员入口只接受调用')
    operation = activation.operation
    module = ctx.config['integrator_module']
    arguments = dict(thaw(activation.parameters))
    if operation == 'read':
        arguments = {'include_history': False}
    elif operation in ('submit', 'approve', 'veto'):
        arguments['member'] = ctx.requester_id
        if operation in ('approve', 'veto') and not arguments.get('candidate_id'):
            current = await ctx.local.call(module, 'read', {'include_history': False})
            if current.get('status') != 'ok':
                return ComponentResult(status='error', error=current.get('error') or '无法读取候选')
            candidate = (current.get('data') or {}).get('candidate') or {}
            if not candidate.get('id'):
                return ComponentResult(status='error', error='当前没有待验收的候选')
            arguments['candidate_id'] = candidate['id']
    else:
        return ComponentResult(status='error', error='未知操作')
    result = await ctx.local.call(module, operation, arguments)
    data = thaw(result.get('data'))
    if operation == 'read' and result['status'] == 'ok' and isinstance(data, dict):
        own = next((entry for entry in data.get('members', []) if entry['id'] == ctx.requester_id), None)
        data['self'] = {'id': ctx.requester_id, 'branch': own.get('branch') if own else None, 'is_member': own is not None}
    return ComponentResult(status=result['status'], data=data, error=result.get('error'))
