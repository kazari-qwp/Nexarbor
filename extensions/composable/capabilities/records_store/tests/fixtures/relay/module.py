from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult


async def execute(ctx, activation):
    if activation.kind != 'access' or activation.operation != 'forward':
        return ComponentResult(status='error', error='测试转调组件只接受 forward 访问请求')

    parameters = activation.parameters
    request = {'deltas': thaw(parameters['deltas'])}
    key = parameters.get('key')
    if key is not None:
        request['key'] = key

    result = await ctx.network.call(
        parameters['target'], 'records.store', 'apply', request
    )
    if result['status'] != 'ok':
        return ComponentResult(status='error', error=result['error'])
    return ComponentResult(
        data={
            'values': result['data']['values'],
            'duplicate': result['data']['duplicate'],
        }
    )
