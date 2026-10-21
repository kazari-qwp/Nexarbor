"""角色活动状态机：同步占用活动键，异步执行模型；不以节点事务包住活动。"""
from copy import deepcopy
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult


def _copy(value):
    """状态可能含可变 list；thaw 只负责解冻，必须再深拷贝。"""
    return deepcopy(thaw(value))

MAX_KEYS=200

def _entries(ctx):return _copy(ctx.state.get('activities',[]))
def _find(ctx,key):return next((entry for entry in _entries(ctx) if entry['key']==key),None)
def _save(ctx,entry):
    entries=[item for item in _entries(ctx) if item['key']!=entry['key']]
    ctx.state['activities']=(entries+[entry])[-MAX_KEYS:]

def _result(ctx,key,status,*,duplicate=False,reason=None):
    entry=_find(ctx,key) or {}
    result=dict(key=key,status=status,duplicate=duplicate,budget_field=ctx.config.get('budget_field','ap'),budget=ctx.config.get('budget',10),completed_count=entry.get('completed_count',0),completed_total=ctx.state.get('completed_total',0))
    if reason:result['reason']=reason
    return result

async def _call(ctx,module,operation,arguments,channel):
    result=await (await ctx.nodes)[ctx.node_id].call(module, operation, arguments)
    if result['status']!='ok':raise RuntimeError(result.get('error') or '本地组件执行失败：'+module)
    return result['data']

def _reserve(ctx,key,resume):
    # 检查与 running 标记之间没有 await，另一激活不会穿插进来。
    previous=_find(ctx,key)
    if previous and not resume:
        if previous['status']=='completed':return None
        raise ValueError('活动键正在执行或上次失败，拒绝重放')
    running=next((e for e in _entries(ctx) if e['status']=='running'),None)
    if running:raise ValueError('本节点已有正在执行的活动，拒绝重叠启动')
    if resume and (not previous or previous['status']!='completed'):raise ValueError('只能继续本时刻已完成的活动')
    entry=dict(previous or {},key=key,status='running',pending=False,runs=(previous or {}).get('runs',0),completed_count=(previous or {}).get('completed_count',0))
    _save(ctx,entry)
    return entry

def _finish(ctx,key,error=None):
    entry=_find(ctx,key)
    if error is not None:
        entry.update(status='failed',pending=False,error=str(error)[:2000])
    else:
        first=entry['completed_count']==0
        entry.update(status='completed',pending=False,completed_count=1)
        if first:ctx.state['completed_total']=ctx.state.get('completed_total',0)+1
        ctx.publish_metadata({'活动状态':'已完成','最近完成活动键':key,'活动完成次数':ctx.state.get('completed_total',0)})
    _save(ctx,entry)

async def _drive(ctx,key,*,resume=False):
    entry=_reserve(ctx,key,resume)
    if entry is None:return _result(ctx,key,'completed',duplicate=True)
    try:
        field=ctx.config.get('budget_field','ap')
        if not resume:await _call(ctx,'records.store','apply',{'set':{field:ctx.config.get('budget',10)}},'records')
        limit=1+ctx.config.get('max_reactions',8)
        while entry['runs']<limit:
            if resume:
                account=await _call(ctx,'records.store','read',{},'records')
                if account['values'].get(field,0)<=0:break
            # 清除已接收的通知，再准备最新现场。执行中的新通知只置 pending。
            entry=_find(ctx,key);entry.update(pending=False,runs=entry['runs']+1);_save(ctx,entry)
            prompt=ctx.config.get('prompt','') if not resume else '你收到新便条。只处理这条新消息，按当前剩余行动点回应，不要重复已完成的行动；完成或需要等待答复、到货、下个时段时直接结束，下一 tick 再继续。不要轮询消息或处境。'
            try:await ctx.network.invoke(ctx.node_id,'runtime:agent_run',{'message':prompt},channels=['runtime.agent'])
            except Exception as error:raise RuntimeError('运行官方端口 runtime:agent_run 失败：'+str(error)) from error
            entry=_find(ctx,key)
            if not entry.get('pending'):break
            resume=True
        _finish(ctx,key)
        return _result(ctx,key,'completed')
    except BaseException as error:
        _finish(ctx,key,error);raise

async def _notify(ctx,key):
    if key!=ctx.signal_id:raise ValueError('活动通知必须属于当前信号')
    entry=_find(ctx,key)
    if entry is None:
        # 初次激活准备上下文时会读取已有便条；通知本身不能凭空新建活动。
        return {'skipped':True}
    if entry['status']=='running':
        entry['pending']=True;_save(ctx,entry);return {'queued':True}
    if entry['status']=='failed':return {'skipped':True}
    return await _drive(ctx,key,resume=True)

async def execute(ctx,activation):
    is_signal=activation.kind=='signal'
    try:
        if is_signal:key=activation.signal.signal_id
        elif activation.kind=='access' and activation.operation in ('activate','notify'):key=activation.parameters['key']
        else:raise ValueError('不支持的角色活动请求')
        if not ctx.config.get('enabled',False):return ComponentResult(data=_result(ctx,key,'skipped',reason='角色活动已禁用'))
        result=await _notify(ctx,key) if not is_signal and activation.operation=='notify' else await _drive(ctx,key)
        return ComponentResult(data=result)
    except Exception as error:
        if is_signal:raise
        return ComponentResult(status='error',error=str(error))
