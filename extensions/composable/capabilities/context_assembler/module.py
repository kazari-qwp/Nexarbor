"""按频道直接读取文本；拓扑层次决定顺序，preview 与 assemble 同源。"""
from copy import deepcopy
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

KINDS = ('system_prompt', 'context', 'inputs', 'tail')
def plain(value): return deepcopy(thaw(value))

async def collect(ctx, config):
    config = plain(config)
    rows, errors = [], []
    # 配置来源属于当前组装器，按列表顺序放在本层。
    for source in config.get('sources', []):
        item = {**source, 'id': 'node:' + ctx.node_id + ':source:' + source['id'], 'source': source.get('path') if source['type'] == 'file' else '直接文本', 'channel': None}
        try:
            if source['type'] == 'file':
                data = await ctx.extended('read_text', {'path': source.get('path', ''), 'roots': list(config.get('document_roots', []))})
                item.update(text=data['text'], resolved_path=data['path'])
            rows.append(item)
        except Exception as error: errors.append({'source': item['source'], 'kind': item['kind'], 'error': str(error)})
    # 四种频道分别 BFS，直接读取节点数据，不要求 context.text 配套模块。
    for kind in KINDS:
        channels = ctx.filter_channels(kind + '_channels', ['context.assembler.' + kind])
        try:
            for reached in await ctx.network.nodes(channels=channels):
                meta, path = reached.metadata, list(reached.path)
                node = reached.node_id
                if node == ctx.node_id or meta.get('node_type') != 'text_file': continue
                origin = {'id': 'node:' + node, 'kind': kind, 'source': node, 'path': path, 'channel': list(channels)}
                try:
                    result = await reached.read({'method': 'key', 'key': 'content'})
                    if result.get('status') != 'ok': raise ValueError('; '.join(result.get('errors', [])) or '文本读取失败')
                    text = result['items'][0]['content']
                    if not isinstance(text, str): raise ValueError('来源不是文本')
                    rows.append({**origin, 'text': text, 'event_id': 'once', 'delivery': 'followup'})
                except Exception as error: errors.append({**origin, 'error': str(error)})
        except Exception as error: errors.append({'source': kind, 'error': str(error)})
    return {'sources': rows, 'errors': errors}

async def assemble(ctx, config):
    packet = await collect(ctx, config)
    rows, errors = packet['sources'], packet['errors']
    # 核心 modules() 已按可达节点的 BFS 顺序返回，逐个收集一次即可。
    # 下游只读取自己的来源，避免递归把深层组装器提前塞入结果。
    channels = ctx.filter_channels('channels', ['context.assembler'])
    for reached in await ctx.network.nodes(channels=channels):
        target = reached.node_id
        if target == ctx.node_id or ctx.module_id not in reached.modules: continue
        try:
            result = await reached.call(ctx.module_id, 'collect')
            if result.get('status') != 'ok': raise ValueError(result.get('error') or '下游组装失败')
            downstream = plain(result['data'])
            rows.extend(downstream['sources']); errors.extend(downstream['errors'])
        except Exception as error: errors.append({'source': target, 'error': str(error)})
    patch = {'system_prompt': '', 'context': [], 'inputs': [], 'tail': []}
    seen, unique = {}, []
    # 保留核心 BFS 与配置列表的原始顺序，只去重，不重排。
    for item in rows:
        kind, key = item['kind'], (item['kind'], item['id'])
        if key in seen:
            if seen[key].get('text') != item.get('text'): errors.append({'source': item['id'], 'error': '同一来源在本次读取中内容发生变化'})
            continue
        seen[key] = item; unique.append({**item, 'matched': True})
        text = item.get('text', '')
        if not isinstance(text, str): errors.append({'source': item['id'], 'error': '来源不是文本'}); continue
        if not text.strip(): continue
        if kind == 'system_prompt': patch[kind] += ('\n\n' if patch[kind] else '') + text
        elif kind == 'context': patch[kind].append({'id': item['id'], 'text': text})
        elif kind == 'tail': patch[kind].append(text)
        else:
            event = item.get('event_id') or 'once'
            patch[kind].append({'id': item['id'] + '/' + event, 'text': text, 'delivery': item.get('delivery', 'followup')})
    return {'format': 'nexarbor-context/v1', 'patch': patch, 'sources': unique, 'errors': errors}

async def execute(ctx, activation):
    if activation.operation == 'collect': return ComponentResult(data=await collect(ctx, ctx.config))
    config = activation.parameters.get('config', ctx.config) if activation.operation == 'preview' else ctx.config
    return ComponentResult(data=await assemble(ctx, config))
