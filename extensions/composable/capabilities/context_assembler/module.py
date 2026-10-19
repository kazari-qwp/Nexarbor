"""纯读取、确定排序、来源可追踪；preview 与 assemble 使用同一个函数。"""
from copy import deepcopy
from collections.abc import Mapping
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

KINDS = ('system_prompt', 'context', 'inputs', 'tail')

def plain(value):
    return deepcopy(thaw(value))

def pointer(value, path):
    if not path: return value
    if not path.startswith('/'): raise ValueError('JSON Pointer 必须以 / 开头')
    for part in path[1:].split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value

def matches(facts, conditions):
    for key, value in conditions.items():
        try: current = pointer(facts, key) if key.startswith('/') else facts[key]
        except (KeyError, IndexError, TypeError, ValueError): return False
        if type(current) is not type(value) or current != value: return False
    return True

async def call(ctx, node, module, operation, args, channels):
    result = await ctx.network.call(node, module, operation, args, channels=channels)
    if result.get('status') != 'ok': raise ValueError(result.get('error') or '文本来源读取失败')
    return plain(result.get('data'))

async def assemble(ctx, config):
    config = plain(config)
    rows, errors, entries = [], [], []
    facts = plain(ctx.metadata());bound_facts={}
    for binding in config.get('bindings', []):
        try:
            value = await call(ctx, binding['node'], binding['module'], binding['operation'], binding.get('arguments', {}), ctx.resolve_channels(binding['channels'],binding.get('channel_modes',{}).get('channels','allow')))
            value = pointer(value, binding.get('pointer', ''))
            if not isinstance(value, dict): raise ValueError('条件事实结果必须是对象')
            for key,item in value.items():
                if key in bound_facts and bound_facts[key]!=item:raise ValueError('条件事实字段冲突：'+key)
            facts.update(value);bound_facts.update(value)
        except Exception as error:
            errors.append({'source': 'facts:' + binding['node'], 'error': str(error)})
    # 每种类型单独 BFS。禁止把四种频道合并查询，否则路径会从一种类型串到另一种。
    for kind in KINDS:
        seen = set()
        channels=ctx.filter_channels(kind+'_channels',['context.assembler.'+kind])
        try: nodes = await ctx.network.nodes(channels=channels)
        except Exception as error:
            errors.append({'source': kind, 'error': str(error)}); continue
        for item in nodes:
            meta = item['metadata']; node = meta['node_id']
            if node == ctx.node_id or node in seen or meta.get('node_type') != 'text_file': continue
            seen.add(node)
            origin = {'id': 'node:' + node, 'kind': kind, 'source': node, 'path': list(item.get('path', [])), 'channel': list(channels)}
            try:
                data = await call(ctx, node, 'context.text', 'read', {}, channels)
                entries.append({**data, **origin})
            except Exception as error: errors.append({**origin, 'error': str(error)})
    for source in config.get('sources', []):
        item = {**source, 'id': 'node:' + ctx.node_id + ':source:' + source['id'], 'source': source.get('path') if source['type'] == 'file' else '直接文本', 'channel': None}
        try:
            if source['type'] == 'file' and source.get('enabled', True) and matches(facts, source.get('when', {})):
                # 唯一文件端口：官方宿主解析项目路径与明确授权的目录，普通模块无 open() 权限。
                data = await ctx.extended('read_text', {'path': source.get('path', ''), 'roots': list(config.get('document_roots', []))})
                item.update(text=data['text'], resolved_path=data['path'])
            entries.append(item)
        except Exception as error: errors.append({'id': item['id'], 'source': item['source'], 'kind': item['kind'], 'error': str(error)})
    # 每个下游先在自己的事实与授权下装配，再合并带稳定来源 ID 的结果。
    rows=[]
    for item in entries:rows.append({**item,'matched':bool(item.get('enabled',True) and matches(facts,item.get('when',{})))})
    ancestors={item['node_id'] for item in ctx.call_path if item['module']==ctx.module_id}
    chain_channels=ctx.filter_channels('channels',['context.assembler'])
    for reached in await ctx.network.modules(ctx.module_id,channels=chain_channels):
        target=reached['node_id']
        if target in ancestors:continue
        try:
            result=await ctx.network.call(target,ctx.module_id,'assemble',{},channels=chain_channels,forward=True)
            if result.get('status')!='ok':raise ValueError(result.get('error') or '下游组装失败')
            packet=plain(result['data']);rows.extend(packet['sources']);errors.extend(packet['errors'])
        except PermissionError:
            # 可达中继节点没有此组件，不是错误来源。
            continue
        except Exception as error:errors.append({'source':target,'error':str(error)})
    patch={'system_prompt':'','context':[],'inputs':[],'tail':[]};seen={};unique=[]
    for item in sorted(rows,key=lambda e:(e.get('order',0),e['id'],e['kind'])):
        kind,key=item['kind'],(item['kind'],item['id'])
        if key in seen:
            if seen[key].get('text')!=item.get('text'):errors.append({'source':item['id'],'error':'同一来源在本次读取中内容发生变化'})
            continue
        seen[key]=item;unique.append(item)
        if not item.get('matched',False):continue
        text=item.get('text','')
        if not isinstance(text,str):errors.append({'source':item['id'],'error':'来源不是文本'});continue
        if not text.strip():continue
        if kind=='system_prompt':patch[kind]+=('\n\n' if patch[kind] else '')+text
        elif kind=='context':patch[kind].append({'id':item['id'],'text':text})
        elif kind=='tail':patch[kind].append(text)
        else:
            event=item.get('event_id')
            if not event:errors.append({'source':item['id'],'error':'inputs 需要唯一且稳定的事件编号'});continue
            patch[kind].append({'id':item['id']+'/'+event,'text':text,'delivery':item.get('delivery','followup')})
    return {'format':'nexarbor-context/v1','patch':patch,'sources':unique,'errors':errors}

async def execute(ctx,activation):
    config=activation.parameters.get('config',ctx.config) if activation.operation=='preview' else ctx.config
    return ComponentResult(data=await assemble(ctx,config))
