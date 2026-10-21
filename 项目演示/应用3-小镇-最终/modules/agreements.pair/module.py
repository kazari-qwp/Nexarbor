"""双方实际在场时登记同意；离场通过到访版本使未完成同意失效。"""
from copy import deepcopy
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

class AgreementError(ValueError): pass
def _plain(value): return deepcopy(thaw(value))
def _as_list(value): return [] if value is None else list(value) if isinstance(value,(list,tuple)) else [value]

async def call(ctx,target,module,operation,args=None):
    result=await (await ctx.nodes)[target].call(module, operation, args or {})
    if result['status']!='ok':raise AgreementError(result.get('error') or '协议数据读取失败')
    return _plain(result['data'])

def _check_prerequisites(rule, left_values, right_values, left_id, right_id):
    eligible_field = rule.get("eligible_field")
    if eligible_field and not (
        left_values.get(eligible_field) is True
        or right_values.get(eligible_field) is True
    ):
        raise AgreementError("双方均不具备协议所需资格：" + str(eligible_field))
    for field, expected in _plain(rule.get("require_values") or {}).items():
        if left_values.get(field) != expected or right_values.get(field) != expected:
            raise AgreementError("双方尚未满足协议前提：" + str(field))
    for field in _as_list(rule.get("equal_fields")):
        left = left_values.get(field)
        right = right_values.get(field)
        if left in (None, "") or right in (None, "") or left != right:
            raise AgreementError("双方字段必须相同且非空：" + str(field))
    pair_field = rule.get("pair_field")
    if rule.get("require_pair"):
        if not pair_field:
            raise AgreementError("协议规则缺少关系字段")
        if left_values.get(pair_field) != right_id or right_values.get(pair_field) != left_id:
            raise AgreementError("双方尚未与对方建立所需关系")
    if rule.get("forbid_existing_pair"):
        if not pair_field:
            raise AgreementError("协议规则缺少关系字段")
        if left_values.get(pair_field) not in (None, "") or right_values.get(pair_field) not in (None, ""):
            raise AgreementError("双方已有关系，不能重复建立")


def summary(entry,duplicate=False):
    return {**_plain(entry),'duplicate':duplicate}

async def agree(ctx,args):
    actor,partner=ctx.requester_id,args['partner'];rule_id=args['rule'];key=args['key']
    if not actor or actor==partner:raise AgreementError('需要两位不同的真实 Agent')
    for who in (actor,partner):
        if ((await ctx.nodes)[who].metadata)['node_type']!='agent':raise AgreementError('协议参与者必须是 Agent')
    rule=next((r for r in ctx.config.get('rules',()) if r['id']==rule_id),None)
    if rule is None:raise AgreementError('协议规则不存在')
    async with ctx.network.lock_nodes([ctx.node_id,actor,partner]):
        state=ctx.state;agreements=_plain(state.get('agreements',[]));receipts=_plain(state.get('agree_receipts',[]))
        receipt=next((r for r in receipts if r['requester']==actor and r['user_key']==key),None)
        if receipt:
            if receipt['partner']!=partner or receipt['rule']!=rule_id:raise AgreementError('同一请求键不能改变对象或规则')
            return summary(next(a for a in agreements if a['id']==receipt['agreement_id']),True)
        locations={who:await call(ctx,who,'place.info','read') for who in (actor,partner)}
        address=ctx.config.get('address') or locations[actor].get('location')
        if not address or any(p.get('location')!=address for p in locations.values()):raise AgreementError('双方必须实际在同一协议地点')
        visits={who:p.get('visit',0) for who,p in locations.items()}
        values={who:(await call(ctx,who,'records.store','read'))['values'] for who in (actor,partner)}
        _check_prerequisites(rule,values[actor],values[partner],actor,partner)
        pair=sorted([actor,partner])
        entry=next((a for a in reversed(agreements) if sorted(a['participants'])==pair and a['rule']==rule_id and a['status']=='open'),None)
        if entry is None:
            sequence=state.get('sequence',0)+1;state['sequence']=sequence
            entry=dict(id='agr-'+str(sequence),rule=rule_id,participants=pair,approvals=[],status='open')
            agreements.append(entry)
        # Both participants' visit versions identify one continuous meeting.
        entry['approvals']=[a for a in entry['approvals'] if a.get('visits')==visits]
        if not any(a['participant']==actor for a in entry['approvals']):
            cost=rule.get('cost',1)
            if values[actor].get('ap',0)<cost:raise AgreementError('行动点不足')
            if cost:await call(ctx,actor,'records.store','apply',{'deltas':{'ap':-cost},'key':ctx.node_id+':'+actor+':'+key})
            entry['approvals'].append(dict(participant=actor,key=key,visits=visits))
        if {a['participant'] for a in entry['approvals']}==set(pair):
            for who in pair:
                other=partner if who==actor else actor
                payload={'set':_plain(rule.get('set_values',{}))}
                if rule.get('forbid_existing_pair') and rule.get('pair_field'):payload['references']=[{'key':rule['pair_field'],'node_id':other}]
                if payload['set'] or payload.get('references'):await call(ctx,who,'records.store','apply',payload)
            entry['status']='completed'
        receipts.append(dict(key=actor+'\x1f'+key,requester=actor,user_key=key,partner=partner,rule=rule_id,agreement_id=entry['id']))
        # Preserve agreements referenced by retry receipts.
        state['agreements']=agreements;state['agree_receipts']=receipts[-200:]
        return summary(entry)

async def execute(ctx,activation):
    try:
        if activation.operation=='inspect':
            return ComponentResult(data={'rules':_plain(ctx.config.get('rules',[])),'agreements':[_plain(a) for a in ctx.state.get('agreements',[]) if ctx.requester_id in a['participants']]})
        if activation.operation!='agree':raise AgreementError('不支持的协议操作')
        return ComponentResult(data=await agree(ctx,activation.parameters))
    except Exception as error:return ComponentResult(status='error',error=str(error))
