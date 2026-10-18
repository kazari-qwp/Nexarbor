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

def link(source,target,action):
    return dict(source=source,target=target,action=action,metadata=dict(channels=['movement','tools'],threshold=1,multiplier=1,attributes={'relation':'location'}))

async def move(ctx):
    actor=ctx.requester_id;metadata=await ctx.network.metadata(actor)
    if metadata['node_type']!='agent':raise ValueError('移动请求必须由 Agent 发起')
    before=await call(ctx,actor,'read');old=before['location']
    if not old:raise ValueError('NPC 尚未设置初始所在地点，请装配位置资料')
    if old==ctx.node_id:return dict(moved=False,location=ctx.node_id)
    async with ctx.network.lock_nodes([actor,old,ctx.node_id]):
        current=await call(ctx,actor,'read')
        if current['location']!=old:raise RuntimeError('等待期间位置已变化，请重新选择目的地')
        old_edges=await ctx.network.edges(old);new_edges=await ctx.network.edges(ctx.node_id);actor_edges=await ctx.network.edges(actor)
        if not connected(old_edges,ctx.node_id,'road') or not connected(new_edges,old,'road'):raise ValueError('目的地必须与旧地点有双向相邻道路')
        if not connected(actor_edges,old,'location') or not connected(old_edges,actor,'location'):raise ValueError('NPC 的位置资料与双向位置连接不一致')
        await ctx.network.patch_edges([link(actor,ctx.node_id,'add'),link(ctx.node_id,actor,'add')])
        destination=await call(ctx,ctx.node_id,'read')
        await call(ctx,ctx.node_id,'arrive',{'visitor':actor})
        await call(ctx,old,'leave',{'visitor':actor})
        await call(ctx,actor,'set_location',{'location':ctx.node_id,'description':destination['name']+'：'+destination['description']})
        # 精确移除旧位置边，保留道路、其他频道与业务链接。
        removals=[dict(source=source,target=target,action='remove',metadata=thaw(edge['metadata'])) for source,target,edges in [(actor,old,actor_edges),(old,actor,old_edges)] for edge in edges if edge['target_node_id']==target and edge['metadata']['attributes'].get('relation')=='location']
        await ctx.network.patch_edges(removals)
    return dict(moved=True,from_location=old,location=ctx.node_id,description=destination['description'])

async def execute(ctx,activation):
    if activation.kind!='access' or activation.operation!='move':return ComponentResult(status='error',error='移动到此仅接受移动访问')
    try:
        async with asyncio.timeout(ctx.config.get('timeout_seconds',15)):
            return ComponentResult(data=await move(ctx))
    except Exception as error:
        # 必须在锁作用域外转换失败结果，确保异常触发回滚。
        return ComponentResult(status='error',error='移动未完成：'+(str(error) or '等待或执行超时，请重试'))
