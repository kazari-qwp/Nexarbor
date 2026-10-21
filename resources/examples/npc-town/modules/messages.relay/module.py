"""沿 chat 频道把便笺转交给收件人自己的 messages.box，不保存副本。"""
from datanet.core.module_protocol import ComponentResult


async def _send_to(ctx, parameters):
    recipient = parameters['recipient']
    if recipient == ctx.node_id:
        raise ValueError('收件人必须是自己以外的另一位真实 Agent')

    target = (await ctx.network.nodes(channels=['chat'])).get(recipient)
    metadata = target.metadata if target else None
    if metadata is None:
        raise ValueError(f'收件人 {recipient} 当前不可达')
    if metadata.get('node_type') != 'agent':
        raise ValueError(f'收件人 {recipient} 不是真实 Agent')

    if 'messages.box' not in target.modules:
        raise ValueError('收件人未装配消息箱')
    forwarded = await target.call('messages.box', 'send', {
        'text': parameters['text'], 'topic': parameters.get('topic', ''),
        **({'key': parameters['key']} if 'key' in parameters else {})})
    if forwarded.get('status') != 'ok':
        raise ValueError(f'收件人 {recipient} 的消息箱拒绝投递：{forwarded.get("error") or "未知错误"}')
    # 成功结果原样返回；from 由 messages.box 依据原始 requester_id 填写。
    return forwarded['data']


async def execute(ctx, activation):
    if activation.kind != 'access' or activation.operation != 'send_to':
        return ComponentResult(status='error', error='私信便笺中继只处理 send_to 访问请求')
    try:
        return ComponentResult(data=await _send_to(ctx, activation.parameters))
    except Exception as error:
        return ComponentResult(status='error', error=str(error))
