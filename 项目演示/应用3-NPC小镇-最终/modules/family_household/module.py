"""同住双方完成家庭计划同意后，记录怀孕起始 tick 与上下文边。"""
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


async def plan(module,node,participants,args):
    actor,partner=requester_id.get(),args['partner']
    clock_node=await time_source(module);clock=clock_node.info.node_id
    pregnancy_texts=await texts(module,'pregnancy_channels','family.pregnancy')
    participants.update(pregnancy_texts);participants[clock]=clock_node
    text_ids=list(pregnancy_texts)
    people={who:(await call(participants,who,'records.store','read'))['values'] for who in (actor,partner)}
    contexts=[p['context_node'] for p in people.values() if p.get('context_node')]
    selected={key:participants[key] for key in [node.info.node_id,actor,partner,clock,*contexts,*text_ids]}
    async with module.transaction(list(selected)):
        for who in (actor,partner):
            if (await call(participants,who,'records.store','read'))['values'].get('home')!=node.info.node_id:
                raise ValueError('家庭计划须在双方登记的共同住处办理')
        agreement=await node.modules.get('agreements.pair').agree(partner,'family_plan',args['key'])
        identifier=agreement['id']
        if agreement['status']!='completed':return agreement
        started=module.state.get('started',{})
        if identifier in started:return dict(agreement,pregnancy=thaw(started[identifier]),duplicate=True)
        people={who:(await call(participants,who,'records.store','read'))['values'] for who in (actor,partner)}
        carriers=[who for who,p in people.items() if p.get('can_gestate') is True]
        if len(carriers)!=1:raise ValueError('该家庭计划需要一位可怀孕的参与者')
        mother=carriers[0];values=people[mother]
        if values.get('pregnancy') is not None or values.get('pregnant'):raise ValueError('已有怀孕记录')
        context=values.get('context_node')
        if not context:raise ValueError('参与者缺少显式上下文节点引用')
        tick=(await call(participants,clock,'world.time','read'))['tick']
        pregnancy=dict(id=sha256((node.info.node_id+':'+identifier).encode()).hexdigest()[:32],start_tick=tick,parents=sorted([actor,partner]),home=values['home'])
        await call(participants,mother,'records.store','apply',{'set':{'pregnant':True,'pregnancy':pregnancy}})
        if text_ids:apply_edges([edge(participants,context,target,'add','pregnancy') for target in text_ids])
        module.state['started']={**thaw(started),identifier:pregnancy}
        return dict(agreement,pregnancy=pregnancy)


class FamilyHouseholdModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('family.household', **access_settings)
        self.transaction = transaction
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
        return await node.modules.get('agreements.pair').inspect()

    async def plan(self, partner, key):
        return next(iter((await self._plan(dict(partner=partner,key=key))).values()))

    @access(channels=())
    async def _plan(self, node, parameters):
        with as_caller(node.info.node_id):
            return await plan(self,node,await self._participants(),parameters)
