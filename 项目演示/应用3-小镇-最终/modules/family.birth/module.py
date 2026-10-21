"""医院只检查待产者的怀孕记录和时间差，创建独立的新生儿网络。"""
from copy import deepcopy
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

async def call(ctx,target,module,operation,args=None,**options):
    result=await (await ctx.nodes)[target].call(module, operation, args or {})
    if result['status']!='ok':raise ValueError(result.get('error') or '医院操作失败')
    return deepcopy(thaw(result['data']))

async def time_source(ctx):
    channels=ctx.filter_channels('time_channels',['time'])
    sources=[node for node in await ctx.network.nodes(channels=channels) if 'world.time' in node.modules]
    if len(sources)!=1:raise ValueError('时间频道须连接唯一的时间源')
    return sources[0].node_id,channels

async def texts(ctx,field,default):
    return [n.node_id for n in await ctx.network.nodes(channels=ctx.filter_channels(field,[default])) if n.node_type=='text_file']

def edge(source,target,action,kind):
    return dict(source=source,target=target,action=action,metadata=dict(channels=['context.assembler.context'],threshold=1,multiplier=1,attributes={'context':kind}))

async def inspect(ctx):
    values=(await call(ctx,ctx.requester_id,'records.store','read'))['values'];pregnancy=values.get('pregnancy')
    if not pregnancy:return dict(pregnancy=None,ready=False)
    clock,channels=await time_source(ctx);tick=(await call(ctx,clock,'world.time','read',channels=channels))['tick']
    elapsed=tick-pregnancy['start_tick']
    return dict(pregnancy=pregnancy,tick=tick,elapsed=elapsed,ready=elapsed>=ctx.config.get('duration',10))

async def deliver(ctx,args):
    actor=ctx.requester_id;request=actor+'\x1f'+args['key']
    old=next((r for r in ctx.state.get('births',[]) if r['request']==request),None)
    if old:
        if old['name']!=args['name']:raise ValueError('同一出生请求不能更改姓名')
        return dict(old['result'],duplicate=True)
    clock,channels=await time_source(ctx)
    pregnant=(await call(ctx,actor,'records.store','read'))['values'].get('pregnancy')
    if not pregnant:raise ValueError('没有怀孕词条')
    parents=pregnant['parents'];pregnancy_id=pregnant['id']
    if actor not in parents:raise ValueError('怀孕记录与待产者不一致')
    people={who:(await call(ctx,who,'records.store','read'))['values'] for who in parents}
    contexts=[p['context_node'] for p in people.values() if p.get('context_node')]
    pregnancy_texts=await texts(ctx,'pregnancy_channels','family.pregnancy');parent_texts=await texts(ctx,'parent_channels','family.parent')
    locks=[ctx.node_id,clock,*parents,*contexts,*pregnancy_texts,*parent_texts]
    async with ctx.network.lock_nodes(locks):
        values=(await call(ctx,actor,'records.store','read'))['values'];current=values.get('pregnancy')
        if not current or current['id']!=pregnancy_id:raise ValueError('怀孕记录已变化，请重新查询')
        if (await call(ctx,actor,'place.info','read'))['location']!=ctx.node_id:raise ValueError('待产者须本人到达医院')
        tick=(await call(ctx,clock,'world.time','read',channels=channels))['tick']
        if tick-current['start_tick']<ctx.config.get('duration',10):raise ValueError('尚未达到生产时间')
        pending=deepcopy(thaw(ctx.state.get('pending',{})))
        if pregnancy_id in pending:
            job=pending[pregnancy_id]
            if job['arguments']['name']!=args['name']:raise ValueError('请使用原姓名重试待办出生')
        else:
            template=next((t['template'] for t in ctx.config['templates'] if t['home']==current['home']),None)
            if not template:raise ValueError('该住所没有新生儿模板')
            cost=ctx.config.get('cost',1)
            if values.get('ap',0)<cost:raise ValueError('行动点不足')
            if cost:await call(ctx,actor,'records.store','apply',{'deltas':{'ap':-cost}})
            job=dict(template=template,key='birth-'+pregnancy_id,arguments=dict(name=args['name'],parents=parents,home=current['home']))
            pending[pregnancy_id]=job;ctx.state['pending']=pending
    # Host template creation has its own atomic commit and durable idempotency.
    created=await ctx.network.invoke(ctx.node_id,'templates:instantiate',job,channels=['runtime.template'])
    child=created.get('node_ids',{}).get('child')
    if not child:raise ValueError('出生模板没有返回儿童节点，可按原请求重试')
    async with ctx.network.lock_nodes(locks):
        existing=next((r for r in ctx.state.get('births',[]) if r['pregnancy_id']==pregnancy_id),None)
        if existing:return dict(existing['result'],duplicate=True)
        values=(await call(ctx,actor,'records.store','read'))['values']
        if (values.get('pregnancy') or {}).get('id')!=pregnancy_id:raise ValueError('待办出生的怀孕记录发生变化')
        changes=[]
        for who in parents:
            current_values=(await call(ctx,who,'records.store','read'))['values']
            context=current_values.get('context_node')
            if not context:raise ValueError('家长缺少显式上下文节点引用')
            payload={'set':{'is_parent':True},'references':[{'key':'child_'+pregnancy_id,'node_id':child}]}
            if who==actor:
                payload['set']['pregnant']=False;payload['unset']=['pregnancy']
                changes.extend(edge(context,target,'remove','pregnancy') for target in pregnancy_texts)
            changes.extend(edge(context,target,'add','parent') for target in parent_texts)
            await call(ctx,who,'records.store','apply',payload)
        if changes:await ctx.network.patch_edges(changes)
        pending=deepcopy(thaw(ctx.state.get('pending',{})));pending.pop(pregnancy_id,None);ctx.state['pending']=pending
        result=dict(child=child,node_ids=created['node_ids'],duplicate=False)
        ctx.state['births']=(list(ctx.state.get('births',[]))+[dict(request=request,name=args['name'],pregnancy_id=pregnancy_id,result=result)])[-200:]
        return result

async def execute(ctx,activation):
    try:return ComponentResult(data=await (inspect(ctx) if activation.operation=='inspect' else deliver(ctx,activation.parameters)))
    except Exception as error:return ComponentResult(status='error',error=str(error))
