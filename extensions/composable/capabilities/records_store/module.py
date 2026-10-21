"""本地记录仓：纯计算候选状态，校验完后同步提交；不自行申请节点事务。"""
import json
import math
from copy import deepcopy
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult


def _copy(value):
    """状态可能含可变 list；thaw 只负责解冻，必须再深拷贝。"""
    return deepcopy(thaw(value))

MAX_RECEIPTS=200

def _number(value):
    return type(value) in (int,float) and math.isfinite(value)

def _equal(a,b):
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if _number(a) or _number(b):return _number(a) and _number(b) and a==b
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(_equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):return len(a)==len(b) and all(_equal(x,y) for x,y in zip(a,b))
    return type(a) is type(b) and a==b

def _references(items,label):
    result={}
    for item in items:
        key,target=item['key'],item['node_id']
        if key in result:raise ValueError(f'{label} 中引用键“{key}”重复')
        if target is not None and (not isinstance(target,str) or not target):raise ValueError(f'引用字段“{key}”必须是节点 ID 字符串或 null')
        result[key]=target
    return result

def _items(references):return [dict(key=k,node_id=v) for k,v in references.items()]
def _view(values,references):return {**_copy(values),**references}

def _snapshot(ctx):
    initial=_copy(ctx.config.get('initial',{}));configured=_references(ctx.config.get('references',[]),'配置')
    overlap=set(initial)&set(configured)
    if overlap:raise ValueError('配置 initial 与 references 字段同名：'+', '.join(sorted(overlap)))
    values=_copy(ctx.state.get('values',initial))
    references=_references(ctx.state.get('references',_items(configured)),'状态')
    if set(values)&set(references):raise ValueError('普通记录与引用字段不能同名')
    return values,references,_copy(ctx.state.get('receipts',[]))

def _plan(ctx,parameters):
    # 所有运算都在私有 JSON 副本上；任一步失败不会初始化或改写运行状态。
    values,references,receipts=_snapshot(ctx)
    request={field:_copy(parameters.get(field,[] if field=='references' else {})) for field in ('set','deltas','expected','references')}
    if parameters.get('unset'):request['unset']=_copy(parameters['unset'])
    fingerprint=json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    key=parameters.get('key')
    if key is not None:
        for receipt in reversed(receipts):
            if receipt['key']!=key:continue
            if receipt['fingerprint']!=fingerprint:raise ValueError(f'去重键“{key}”已用于不同请求')
            return None,dict(values=_view(receipt['values'],_references(receipt.get('references',[]),'回执')),duplicate=True)
    before=_view(values,references)
    for field,expected in request['expected'].items():
        if field not in before:raise ValueError(f'期望字段“{field}”不存在')
        if not _equal(before[field],expected):raise ValueError(f'字段“{field}”与 expected 不一致')
    updates=_references(request['references'],'参数 references')
    if set(updates)&set(values):raise ValueError('引用键与普通记录字段同名')
    references.update(updates)
    removed=request.get('unset',[])
    if set(removed)&(set(request['set'])|set(request['deltas'])|set(updates)):raise ValueError('删除字段不能同时写入')
    for field in removed:values.pop(field,None);references.pop(field,None)
    changed=set()
    for field,value in request['set'].items():
        if field in references:
            if value is not None and (not isinstance(value,str) or not value):raise ValueError(f'引用字段“{field}”必须是节点 ID 字符串或 null')
            references[field]=value
        else:values[field]=value;changed.add(field)
    for field,delta in request['deltas'].items():
        if field in references:raise ValueError(f'引用字段“{field}”不能做数值增减')
        current=values.get(field,0)
        if not _number(delta) or not _number(current):raise ValueError(f'字段“{field}”及其增减值必须是数字')
        value=current+delta
        if not _number(value):raise ValueError(f'字段“{field}”运算结果不是有限数字')
        values[field]=value;changed.add(field)
    for field,floor in ctx.config.get('minimum',{}).items():
        if field in changed and (not _number(values[field]) or values[field]<floor):raise ValueError(f'字段“{field}”低于最低值或不是数字，操作已取消')
    items=_items(references)
    if key is not None:receipts.append(dict(key=key,fingerprint=fingerprint,values=_copy(values),references=_copy(items)))
    candidate=dict(values=values,references=items,receipts=receipts[-MAX_RECEIPTS:])
    # 提交前验证全部 JSON，包括回执；后续没有网络等待或可能失败的业务运算。
    json.dumps(candidate,allow_nan=False)
    return candidate,dict(values=_view(values,references),duplicate=False)

async def execute(ctx,activation):
    if activation.kind!='access':return ComponentResult(status='error',error='局部记录仓只接受访问请求')
    try:
        if activation.operation=='read':
            values,references,_=_snapshot(ctx)
            return ComponentResult(data={'values':_view(values,references)})
        if activation.operation!='apply':raise ValueError('不支持的记录仓操作')
        candidate,result=_plan(ctx,activation.parameters)
        if candidate is not None:
            # 同一核心事件循环内，无 await 的提交不会向其他回调暴露半成品。
            for field,value in candidate.items():ctx.state[field]=value
        return ComponentResult(data=result)
    except Exception as error:return ComponentResult(status='error',error=str(error))
