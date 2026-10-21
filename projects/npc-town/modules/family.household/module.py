"""居民楼家庭计划：本地双人同意完成后，写入怀孕起始 tick。"""
from hashlib import sha256
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

async def call(ctx,target,module,operation,args=None,**options):
    result=await (await ctx.nodes)[target].call(module, operation, args or {})
    if result['status']!='ok':raise ValueError(result.get('error') or '家庭计划操作失败')
    return thaw(result['data'])

async def time_source(ctx):
    channels=ctx.filter_channels('time_channels',['time'])
    sources=[node for node in await ctx.network.nodes(channels=channels) if 'world.time' in node.modules]
    if len(sources)!=1:raise ValueError('时间频道须连接唯一的时间源')
    return sources[0].node_id,channels

async def pregnancy_texts(ctx):
    return [n.node_id for n in await ctx.network.nodes(channels=ctx.filter_channels('pregnancy_channels',['family.pregnancy'])) if n.node_type=='text_file']

def edge(source,target,action):
    return dict(source=source,target=target,action=action,metadata=dict(channels=['context.assembler.context'],threshold=1,multiplier=1,attributes={'context':'pregnancy'}))

async def plan(ctx,args):
    actor,partner=ctx.requester_id,args['partner']
    clock,channels=await time_source(ctx);texts=await pregnancy_texts(ctx)
    people={who:(await call(ctx,who,'records.store','read'))['values'] for who in (actor,partner)}
    contexts=[p['context_node'] for p in people.values() if p.get('context_node')]
    async with ctx.network.lock_nodes([ctx.node_id,actor,partner,clock,*contexts,*texts]):
        for who in (actor,partner):
            if (await call(ctx,who,'records.store','read'))['values'].get('home')!=ctx.node_id:
                raise ValueError('家庭计划须在双方登记的共同住处办理')
        result=await ctx.local.call('agreements.pair','agree',{'partner':partner,'rule':'family_plan','key':args['key']},target=ctx.node_id)
        if result['status']!='ok':raise ValueError(result.get('error') or '双方同意尚未登记')
        agreement=thaw(result['data']);identifier=agreement['id']
        if agreement['status']!='completed':return agreement
        started=ctx.state.get('started',{})
        if identifier in started:return dict(agreement,pregnancy=thaw(started[identifier]),duplicate=True)
        people={who:(await call(ctx,who,'records.store','read'))['values'] for who in (actor,partner)}
        carriers=[who for who,p in people.items() if p.get('can_gestate') is True]
        if len(carriers)!=1:raise ValueError('该家庭计划需要一位可怀孕的参与者')
        mother=carriers[0];values=people[mother]
        if values.get('pregnancy') is not None or values.get('pregnant'):raise ValueError('已有怀孕记录')
        context=values.get('context_node')
        if not context:raise ValueError('参与者缺少显式上下文节点引用')
        tick=(await call(ctx,clock,'world.time','read',channels=channels))['tick']
        pregnancy=dict(id=sha256((ctx.node_id+':'+identifier).encode()).hexdigest()[:32],start_tick=tick,parents=sorted([actor,partner]),home=values['home'])
        await call(ctx,mother,'records.store','apply',{'set':{'pregnant':True,'pregnancy':pregnancy}})
        if texts:await ctx.network.patch_edges([edge(context,target,'add') for target in texts])
        ctx.state['started']={**thaw(started),identifier:pregnancy}
        return dict(agreement,pregnancy=pregnancy)

async def execute(ctx,activation):
    try:
        if activation.operation=='inspect':
            result=await ctx.local.call('agreements.pair','inspect',{},target=ctx.node_id)
            return ComponentResult(status=result['status'],data=result.get('data'),error=result.get('error'))
        return ComponentResult(data=await plan(ctx,activation.parameters))
    except Exception as error:return ComponentResult(status='error',error=str(error))
