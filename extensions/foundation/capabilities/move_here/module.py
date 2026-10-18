"""目的地提供移动工具；顺序由 await 保证，中间状态由节点锁隔离。"""
import asyncio
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw

async def call(ctx,target,operation,arguments=None):
    result=await ctx.network.call(target,'place.info',operation,arguments or {})
    if result['status']!='ok':raise RuntimeError(result['error'])
    return result['data']

def connected(edges,target,relation):
    return any(edge['target_node_id']==target and edge['metadata']['attributes'].get('relation')==relation and 'movement' in edge['metadata']['channels'] for edge in edges)

def location_channels(ctx):
    channels=thaw(ctx.config.get('location_channels',('movement','tools')))
    if not isinstance(channels,list) or not channels:
        raise ValueError('新位置边频道必须是非空字符串数组')
    if any(not isinstance(channel,str) or not channel for channel in channels):
        raise ValueError('新位置边频道必须是非空字符串')
    if len(set(channels))!=len(channels):
        raise ValueError('新位置边频道不能重复')
    if 'movement' not in channels:
        raise ValueError('新位置边频道必须包含 movement')
    if 'self' in channels:
        raise ValueError('新位置边频道不能包含 self 频道')
    return channels

def link(source,target,action,channels):
    return dict(source=source,target=target,action=action,metadata=dict(channels=list(channels),threshold=1,multiplier=1,attributes={'relation':'location'}))

async def run_hooks(ctx,actor,old):
    targets={'requester':actor,'origin':old,'destination':ctx.node_id}
    results=[]
    for index,hook in enumerate(ctx.config.get('before_hooks',())):
        key=hook.get('target')
        if key not in targets:raise ValueError('第 %d 个移动前钩子的目标无效' % (index+1))
        module=hook.get('module')
        operation=hook.get('operation')
        if not isinstance(module,str) or not module or not isinstance(operation,str) or not operation:
            raise ValueError('第 %d 个移动前钩子必须填写模块和操作' % (index+1))
        arguments=thaw(hook.get('arguments',{}))
        if not isinstance(arguments,dict):raise ValueError('第 %d 个移动前钩子的参数必须是对象' % (index+1))
        # 目标节点均已在本事务锁内，钩子不能自行扩大锁集合。
        result=await ctx.network.call(targets[key],module,operation,arguments)
        if result['status']!='ok':
            raise RuntimeError('移动前钩子第 %d 项失败：%s' % (index+1,result['error']))
        # 按配置顺序保留成功钩子的公开结果，供发起 Agent 读取观察。
        data=result.get('data')
        results.append(dict(target=key,module=module,operation=operation,data=thaw(data) if data is not None else None))
    return results

async def move(ctx):
    channels=location_channels(ctx)
    actor=ctx.requester_id;metadata=await ctx.network.metadata(actor)
    if metadata['node_type']!='agent':raise ValueError('移动请求必须由 Agent 发起')
    before=await call(ctx,actor,'read');old=before['location']
    if not old:raise ValueError('NPC 尚未设置初始所在地点，请装配位置资料')
    if old==ctx.node_id:return dict(moved=False,location=ctx.node_id,before_results=[])
    async with ctx.network.lock_nodes([actor,old,ctx.node_id]):
        current=await call(ctx,actor,'read')
        if current['location']!=old:raise RuntimeError('等待期间位置已变化，请重新选择目的地')
        old_edges=await ctx.network.edges(old);new_edges=await ctx.network.edges(ctx.node_id);actor_edges=await ctx.network.edges(actor)
        if not connected(old_edges,ctx.node_id,'road') or not connected(new_edges,old,'road'):raise ValueError('目的地必须与旧地点有双向相邻道路')
        if not connected(actor_edges,old,'location') or not connected(old_edges,actor,'location'):raise ValueError('NPC 的位置资料与双向位置连接不一致')
        # 前置检查全部通过后、修改位置数据前执行可配置钩子；异常穿出锁作用域触发整单回滚。
        before_results=await run_hooks(ctx,actor,old)
        await ctx.network.patch_edges([link(actor,ctx.node_id,'add',channels),link(ctx.node_id,actor,'add',channels)])
        destination=await call(ctx,ctx.node_id,'read')
        await call(ctx,ctx.node_id,'arrive',{'visitor':actor})
        await call(ctx,old,'leave',{'visitor':actor})
        await call(ctx,actor,'set_location',{'location':ctx.node_id,'description':destination['name']+'：'+destination['description']})
        # 精确移除旧位置边，保留道路、其他频道与业务链接。
        removals=[dict(source=source,target=target,action='remove',metadata=thaw(edge['metadata'])) for source,target,edges in [(actor,old,actor_edges),(old,actor,old_edges)] for edge in edges if edge['target_node_id']==target and edge['metadata']['attributes'].get('relation')=='location']
        await ctx.network.patch_edges(removals)
    return dict(moved=True,from_location=old,location=ctx.node_id,description=destination['description'],before_results=before_results)

async def execute(ctx,activation):
    if activation.kind!='access' or activation.operation!='move':return ComponentResult(status='error',error='移动到此仅接受移动访问')
    try:
        async with asyncio.timeout(ctx.config.get('timeout_seconds',15)):
            return ComponentResult(data=await move(ctx))
    except Exception as error:
        # 必须在锁作用域外转换失败结果，确保异常触发回滚。
        return ComponentResult(status='error',error='移动未完成：'+(str(error) or '等待或执行超时，请重试'))
