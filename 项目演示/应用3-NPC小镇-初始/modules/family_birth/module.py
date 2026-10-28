"""出生两阶段提交：先记录收费待办，再调用宿主的原子幂等模板创建端口。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.edge_changes import apply_edges
from app.runtime.requester import as_caller, requester_id
from domain.annotated_link import AnnotatedLink
from domain.core import CallableTool, Module, access
from domain.json_values import thaw

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))


class Sources:
    def __init__(self, module, field, default):
        self._access_origin = module._access_origin
        self.channels = module.config.get(field, [default])
        self.channel_mode = module.config.get('channel_modes', {}).get(field, 'allow')
        self.strength = module.strength

    @access()
    async def collect(self, node):
        return node


async def call(participants,target,module,operation,args=None,**options):
    return deepcopy(thaw(await getattr(participants[target].modules.get(module),operation)(**(args or {}))))


async def time_source(module):
    sources = [node for node in (await Sources(module, 'time_channels', 'time').collect()).values() if node.modules.get('world.time') is not None]
    if len(sources) != 1:raise ValueError('时间频道须连接唯一的时间源')
    return sources[0]


async def texts(module, field, default):
    return {key:node for key,node in (await Sources(module, field, default).collect()).items() if node.node_type == 'markdown'}


def edge(participants, source, target, action, kind):
    return participants[source], action, AnnotatedLink(target, ['context.assembler.context'], threshold=1, attributes={'context':kind})


async def inspect(module,participants):
    values=(await call(participants,requester_id.get(),'records.store','read'))['values'];pregnancy=values.get('pregnancy')
    if not pregnancy:return dict(pregnancy=None,ready=False)
    clock_node=await time_source(module);participants[clock_node.info.node_id]=clock_node
    tick=(await call(participants,clock_node.info.node_id,'world.time','read'))['tick']
    elapsed=tick-pregnancy['start_tick']
    return dict(pregnancy=pregnancy,tick=tick,elapsed=elapsed,ready=elapsed>=module.config.get('duration',10))

async def deliver(module,node,participants,args):
    actor=requester_id.get();request=actor+'\x1f'+args['key']
    old=next((r for r in module.state.get('births',[]) if r['request']==request),None)
    if old:
        if old['name']!=args['name']:raise ValueError('同一出生请求不能更改姓名')
        return dict(old['result'],duplicate=True)
    clock_node=await time_source(module);clock=clock_node.info.node_id;participants[clock]=clock_node
    pregnant=(await call(participants,actor,'records.store','read'))['values'].get('pregnancy')
    if not pregnant:raise ValueError('没有怀孕词条')
    parents=pregnant['parents'];pregnancy_id=pregnant['id']
    if actor not in parents:raise ValueError('怀孕记录与待产者不一致')
    people={who:(await call(participants,who,'records.store','read'))['values'] for who in parents}
    contexts=[p['context_node'] for p in people.values() if p.get('context_node')]
    pregnancy_texts=await texts(module,'pregnancy_channels','family.pregnancy');parent_texts=await texts(module,'parent_channels','family.parent')
    participants.update(pregnancy_texts);participants.update(parent_texts)
    locks=[node.info.node_id,clock,*parents,*contexts,*pregnancy_texts,*parent_texts]
    selected={key:participants[key] for key in locks}
    async with module.transaction(list(selected)):
        values=(await call(participants,actor,'records.store','read'))['values'];current=values.get('pregnancy')
        if not current or current['id']!=pregnancy_id:raise ValueError('怀孕记录已变化，请重新查询')
        if (await call(participants,actor,'place.info','read'))['location']!=node.info.node_id:raise ValueError('待产者须本人到达医院')
        tick=(await call(participants,clock,'world.time','read'))['tick']
        if tick-current['start_tick']<module.config.get('duration',10):raise ValueError('尚未达到生产时间')
        pending=deepcopy(thaw(module.state.get('pending',{})))
        if pregnancy_id in pending:
            job=pending[pregnancy_id]
            if job['arguments']['name']!=args['name']:raise ValueError('请使用原姓名重试待办出生')
        else:
            template=next((t['template'] for t in module.config['templates'] if t['home']==current['home']),None)
            if not template:raise ValueError('该住所没有新生儿模板')
            cost=module.config.get('cost',1)
            if values.get('ap',0)<cost:raise ValueError('行动点不足')
            if cost:await call(participants,actor,'records.store','apply',{'deltas':{'ap':-cost}})
            job=dict(template=template,key='birth-'+pregnancy_id,arguments=dict(name=args['name'],parents=parents,home=current['home']))
            pending[pregnancy_id]=job;module.state['pending']=pending
    # Host template creation has its own atomic commit and durable idempotency.
    created=await module.instantiate(node.info.node_id,**job)
    child=created.get('node_ids',{}).get('child')
    if not child:raise ValueError('出生模板没有返回儿童节点，可按原请求重试')
    selected={key:participants[key] for key in locks}
    async with module.transaction(list(selected)):
        existing=next((r for r in module.state.get('births',[]) if r['pregnancy_id']==pregnancy_id),None)
        if existing:return dict(existing['result'],duplicate=True)
        values=(await call(participants,actor,'records.store','read'))['values']
        if (values.get('pregnancy') or {}).get('id')!=pregnancy_id:raise ValueError('待办出生的怀孕记录发生变化')
        changes=[]
        for who in parents:
            current_values=(await call(participants,who,'records.store','read'))['values']
            context=current_values.get('context_node')
            if not context:raise ValueError('家长缺少显式上下文节点引用')
            payload={'set':{'is_parent':True},'references':[{'key':'child_'+pregnancy_id,'node_id':child}]}
            if who==actor:
                payload['set']['pregnant']=False;payload['unset']=['pregnancy']
                changes.extend(edge(participants,context,target,'remove','pregnancy') for target in pregnancy_texts)
            changes.extend(edge(participants,context,target,'add','parent') for target in parent_texts)
            await call(participants,who,'records.store','apply',payload)
        if changes:apply_edges(changes)
        pending=deepcopy(thaw(module.state.get('pending',{})));pending.pop(pregnancy_id,None);module.state['pending']=pending
        result=dict(child=child,node_ids=created['node_ids'],duplicate=False)
        module.state['births']=(list(module.state.get('births',[]))+[dict(request=request,name=args['name'],pregnancy_id=pregnancy_id,result=result)])[-200:]
        return result


class FamilyBirthModule(Module):
    def __init__(self, transaction, instantiate, config=None, state=None, **access_settings):
        super().__init__('family.birth', **access_settings)
        self.transaction = transaction
        self.instantiate = instantiate
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec['id'], getattr(self,spec['operation']), spec['description'], deepcopy(spec['parameters'])))

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
        return await inspect(self,await self._participants())

    async def deliver(self, name, key):
        return next(iter((await self._deliver(dict(name=name,key=key))).values()))

    @access(channels=())
    async def _deliver(self, node, parameters):
        with as_caller(node.info.node_id):
            return await deliver(self,node,await self._participants(),parameters)
