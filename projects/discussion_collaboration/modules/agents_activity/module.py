"""角色活动状态机；预算重置、幂等活动键和同层消息回应。"""

from copy import deepcopy

from app.runtime.signal_work import current_work
from app.transactions.locks import require_transaction_node
from domain.core import Module, access
from domain.json_values import thaw


def _copy(value):
    return deepcopy(thaw(value))


MAX_KEYS=200

def _entries(module):return _copy(module.state.get('activities',[]))
def _find(module,key):return next((entry for entry in _entries(module) if entry['key']==key),None)
def _save(module,entry):
    entries=[item for item in _entries(module) if item['key']!=entry['key']]
    module.state['activities']=(entries+[entry])[-MAX_KEYS:]

def _result(module,key,status,*,duplicate=False,reason=None):
    entry=_find(module,key) or {}
    result=dict(key=key,status=status,duplicate=duplicate,budget_field=module.config.get('budget_field','ap'),budget=module.config.get('budget',10),completed_count=entry.get('completed_count',0),completed_total=module.state.get('completed_total',0))
    if reason:result['reason']=reason
    return result

async def _call(node,module_id,operation,arguments):
    return await getattr(node.modules.get(module_id),operation)(**arguments)

def _reserve(module,key,resume):
    # 检查与 running 标记之间没有 await，另一激活不会穿插进来。
    previous=_find(module,key)
    if previous and not resume:
        if previous['status']=='completed':return None
        raise ValueError('活动键正在执行或上次失败，拒绝重放')
    running=next((e for e in _entries(module) if e['status']=='running'),None)
    if running:raise ValueError('本节点已有正在执行的活动，拒绝重叠启动')
    if resume and (not previous or previous['status']!='completed'):raise ValueError('只能继续本时刻已完成的活动')
    entry=dict(previous or {},key=key,status='running',pending=False,runs=(previous or {}).get('runs',0),completed_count=(previous or {}).get('completed_count',0))
    _save(module,entry)
    return entry

def _finish(module,key,error=None):
    entry=_find(module,key)
    if error is not None:
        entry.update(status='failed',pending=False,error=str(error)[:2000])
    else:
        first=entry['completed_count']==0
        entry.update(status='completed',pending=False,completed_count=1)
        if first:module.state['completed_total']=module.state.get('completed_total',0)+1
        module.published={'活动状态':'已完成','最近完成活动键':key,'活动完成次数':module.state.get('completed_total',0)}
    _save(module,entry)

async def _drive(module,node,key,*,resume=False):
    entry=_reserve(module,key,resume)
    if entry is None:return _result(module,key,'completed',duplicate=True)
    try:
        field=module.config.get('budget_field','ap')
        if not resume:await _call(node,'records.store','apply',{'set':{field:module.config.get('budget',10)}})
        limit=1+module.config.get('max_reactions',8)
        while entry['runs']<limit:
            if resume:
                account=await _call(node,'records.store','read',{})
                if account['values'].get(field,0)<=0:break
            # 清除已接收的通知，再准备最新现场。执行中的新通知只置 pending。
            entry=_find(module,key);entry.update(pending=False,runs=entry['runs']+1);_save(module,entry)
            prompt=module.config.get('prompt','') if not resume else '你收到新便条。按当前剩余行动点处理需要回应的内容；不要重复已完成的行动，自然结束。'
            try:await module.agent_run(node.info.node_id,prompt)
            except Exception as error:raise RuntimeError('运行官方端口 runtime:agent_run 失败：'+str(error)) from error
            entry=_find(module,key)
            if not entry.get('pending'):break
            resume=True
        _finish(module,key)
        return _result(module,key,'completed')
    except BaseException as error:
        _finish(module,key,error);raise

async def _notify(module,node,key):
    work=current_work.get()
    if work is None or key!=work.signal_id:raise ValueError('活动通知必须属于当前信号')
    entry=_find(module,key)
    if entry is None:
        # 初次激活准备上下文时会读取已有便条；通知本身不能凭空新建活动。
        return {'skipped':True}
    if entry['status']=='running':
        entry['pending']=True;_save(module,entry);return {'queued':True}
    if entry['status']=='failed':return {'skipped':True}
    return await _drive(module,node,key,resume=True)


class AgentsActivityModule(Module):
    signal_channels = ('tick',)

    def __init__(self, agent_run, config=None, state=None, **access_settings):
        super().__init__('agents.activity', **access_settings)
        self.agent_run = agent_run
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        self.published = {}

    async def on_signal(self, context):
        return await self.activate(context.signal.signal_id)

    async def activate(self, key):
        return next(iter((await self._activate(key)).values()))

    @access(channels=())
    async def _activate(self, node, key):
        require_transaction_node(node.info.node_id)
        if not self.config.get('enabled', False):
            return _result(self,key,'skipped',reason='角色活动已禁用')
        return await _drive(self,node,key)

    async def notify(self, key):
        return next(iter((await self._notify_local(key)).values()))

    @access(channels=())
    async def _notify_local(self, node, key):
        require_transaction_node(node.info.node_id)
        if not self.config.get('enabled', False):
            return _result(self,key,'skipped',reason='角色活动已禁用')
        return await _notify(self,node,key)
