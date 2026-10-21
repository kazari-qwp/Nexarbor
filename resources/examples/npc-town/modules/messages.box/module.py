"""本地消息投递；普通入箱同步完成，只有收费与投递的组合使用短事务。"""
import json
from uuid import uuid4
from copy import deepcopy
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult


def _copy(value):
    """状态可能含可变 list；thaw 只负责解冻，必须再深拷贝。"""
    return deepcopy(thaw(value))

def _request(ctx,parameters):
    sender=ctx.requester_id
    if not sender:raise ValueError('无法确认消息发送者')
    text=parameters['text'];topic=parameters.get('topic','');key=parameters.get('key')
    identity=json.dumps([sender,key],ensure_ascii=False,separators=(',',':')) if key is not None else None
    fingerprint=json.dumps({'text':text,'topic':topic},ensure_ascii=False,sort_keys=True,separators=(',',':'))
    message=dict(id=uuid4().hex,**{'from':sender},to=ctx.node_id,text=text,topic=topic)
    return message,identity,fingerprint

def _plan(ctx,message,identity,fingerprint):
    messages=_copy(ctx.state.get('messages',[]));seen=_copy(ctx.state.get('seen',[]))
    if identity is not None:
        for receipt in reversed(seen):
            if receipt['key']!=identity:continue
            if receipt['fingerprint']!=fingerprint:raise ValueError('相同去重键不能发送不同内容')
            return None,dict(message,id=receipt['id'],duplicate=True,ap=None)
    messages.append(message)
    if identity is not None:seen.append(dict(key=identity,fingerprint=fingerprint,id=message['id']))
    limit=int(ctx.config.get('max_messages',200))
    return dict(messages=messages[-limit:],seen=seen[-max(limit,200):]),dict(message,duplicate=False,ap=None)

def _commit(ctx,candidate):
    for field,value in candidate.items():ctx.state[field]=value

async def _sender_metadata(ctx,sender):
    metadata=ctx.metadata() if sender==ctx.node_id else (await ctx.nodes)[sender].metadata
    if ctx.config.get('require_agent',True) and metadata.get('node_type')!='agent':raise ValueError('只有真实 Agent 节点可以发送消息')

async def _charge(ctx,sender,message,key,cost):
    account=await (await ctx.nodes)[sender].call('records.store', 'read', {})
    if account['status']!='ok':raise RuntimeError(account.get('error') or '读取行动点失败')
    ap=account['data']['values'].get('ap')
    if type(ap) not in (int,float) or ap<cost:raise ValueError('行动点不足，无法发送消息')
    receipt=json.dumps([ctx.module_id,ctx.node_id,sender,'send',key if key is not None else message['id']],ensure_ascii=False,separators=(',',':'))
    charged=await (await ctx.nodes)[sender].call('records.store', 'apply', {'deltas':{'ap':-cost},'key':receipt})
    if charged['status']!='ok':raise RuntimeError(charged.get('error') or '扣除行动点失败')
    return charged['data']['values']['ap']

async def _send(ctx,parameters):
    message,identity,fingerprint=_request(ctx,parameters);sender=message['from']
    await _sender_metadata(ctx,sender)
    cost=ctx.config.get('send_cost',0)
    candidate,result=_plan(ctx,message,identity,fingerprint)
    if candidate is None:return result
    if cost:
        # 保护的约束只有“扣费与入箱一起成功”；不涵盖阅读、模型执行或回应。
        async with ctx.network.lock_nodes(list(dict.fromkeys([ctx.node_id,sender])),timeout=20):
            candidate,result=_plan(ctx,message,identity,fingerprint)
            if candidate is not None:
                result['ap']=await _charge(ctx,sender,message,parameters.get('key'),cost)
                _commit(ctx,candidate)
    else:
        # 元数据查询结束后重新读取本地最新状态，再同步计算、提交。
        _commit(ctx,candidate)
    if not result['duplicate'] and ctx.config.get('notify_activity',False) and ctx.signal_id:
        try:result['notification']=ctx.network.post(ctx.node_id,'agents.activity','notify',{'key':ctx.signal_id},channels=['activity'])
        except Exception as error:
            # 投递已完成；通知失败不能谎报为投递失败或让调用者重复扣费。
            result['notification']=dict(queued=False,error=str(error))
    return result

async def execute(ctx,activation):
    if activation.kind!='access':return ComponentResult(status='error',error='消息与讨论箱只处理访问请求')
    try:
        operation=activation.operation
        if operation=='send':return ComponentResult(data=await _send(ctx,activation.parameters))
        if operation=='read':
            if ctx.config.get('read_policy','self')!='reachable' and ctx.requester_id!=ctx.node_id:raise PermissionError('该消息箱仅允许所在节点自己读取')
            return ComponentResult(data={'messages':_copy(ctx.state.get('messages',[]))[-activation.parameters.get('limit',20):]})
        if operation=='clear':
            if ctx.requester_id!=ctx.node_id:raise PermissionError('只有消息箱所在节点可以清理本地消息')
            count=len(ctx.state.get('messages',[]));_commit(ctx,dict(messages=[],seen=[]));return ComponentResult(data={'cleared':count})
        raise ValueError('不支持的消息箱操作')
    except Exception as error:return ComponentResult(status='error',error=str(error))
