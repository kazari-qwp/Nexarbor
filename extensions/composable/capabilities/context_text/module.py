"""只读本节点文本；类型在连线上，既不遍历网络也不写 Agent。"""
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw

async def execute(ctx, activation):
    result = ctx.read({'method': 'key', 'key': 'content'})
    if result.get('status') != 'ok':
        return ComponentResult(status='error', error='无法读取文本节点内容')
    items = result.get('items') or []
    text = items[0].get('content', '') if items else ''
    if not isinstance(text, str):
        return ComponentResult(status='error', error='上下文文本源必须提供文本')
    return ComponentResult(data={**thaw(ctx.config), 'text': text})
