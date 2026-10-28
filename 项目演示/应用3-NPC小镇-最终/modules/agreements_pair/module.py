"""实际在场双方同意；到访版本变化会使未完成审批失效。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.requester import as_caller, requester_id
from domain.core import CallableTool, Module, access
from domain.json_values import thaw

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))

class AgreementError(ValueError): pass
def _plain(value): return deepcopy(thaw(value))
def _as_list(value): return [] if value is None else list(value) if isinstance(value,(list,tuple)) else [value]

async def call(participants,target,module,operation,args=None):
    return _plain(await getattr(participants[target].modules.get(module),operation)(**(args or {})))

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

async def agree(module,node,participants,args):
    actor,partner=requester_id.get(),args['partner'];rule_id=args['rule'];key=args['key']
    if not actor or actor==partner:raise AgreementError('需要两位不同的真实 Agent')
    for who in (actor,partner):
        if participants[who].node_type!='agent':raise AgreementError('协议参与者必须是 Agent')
    rule=next((r for r in module.config.get('rules',()) if r['id']==rule_id),None)
    if rule is None:raise AgreementError('协议规则不存在')
    async with module.transaction([node.info.node_id,actor,partner]):
        state=module.state;agreements=_plain(state.get('agreements',[]));receipts=_plain(state.get('agree_receipts',[]))
        receipt=next((r for r in receipts if r['requester']==actor and r['user_key']==key),None)
        if receipt:
            if receipt['partner']!=partner or receipt['rule']!=rule_id:raise AgreementError('同一请求键不能改变对象或规则')
            return summary(next(a for a in agreements if a['id']==receipt['agreement_id']),True)
        locations={who:await call(participants,who,'place.info','read') for who in (actor,partner)}
        address=module.config.get('address') or locations[actor].get('location')
        if not address or any(p.get('location')!=address for p in locations.values()):raise AgreementError('双方必须实际在同一协议地点')
        visits={who:p.get('visit',0) for who,p in locations.items()}
        values={who:(await call(participants,who,'records.store','read'))['values'] for who in (actor,partner)}
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
            if cost:await call(participants,actor,'records.store','apply',{'deltas':{'ap':-cost},'key':node.info.node_id+':'+actor+':'+key})
            entry['approvals'].append(dict(participant=actor,key=key,visits=visits))
        if {a['participant'] for a in entry['approvals']}==set(pair):
            for who in pair:
                other=partner if who==actor else actor
                payload={'set':_plain(rule.get('set_values',{}))}
                if rule.get('forbid_existing_pair') and rule.get('pair_field'):payload['references']=[{'key':rule['pair_field'],'node_id':other}]
                if payload['set'] or payload.get('references'):await call(participants,who,'records.store','apply',payload)
            entry['status']='completed'
        receipts.append(dict(key=actor+'\x1f'+key,requester=actor,user_key=key,partner=partner,rule=rule_id,agreement_id=entry['id']))
        # Preserve agreements referenced by retry receipts.
        state['agreements']=agreements;state['agree_receipts']=receipts[-200:]
        return summary(entry)


class AgreementsPairModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('agreements.pair', **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec['id'], getattr(self, spec['operation']), spec['description'], deepcopy(spec['parameters'])))

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
        return {'rules':_plain(self.config.get('rules',[])), 'agreements':[_plain(entry) for entry in self.state.get('agreements',[]) if requester_id.get() in entry['participants']]}

    async def agree(self, partner, rule, key):
        return next(iter((await self._agree(dict(partner=partner,rule=rule,key=key))).values()))

    @access(channels=())
    async def _agree(self, node, parameters):
        return await agree(self,node,await self._participants(),parameters)
