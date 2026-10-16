"""Persist node response configuration; executable grants remain host-owned."""
from copy import deepcopy
from datanet.core.json_values import freeze,names


def validate(rules):
    if not isinstance(rules,list) or len(rules)>64:raise ValueError('Responders must be a list of at most 64 entries')
    result=[];seen=set()
    for rule in rules:
        if set(rule)!={'id','channels','steps'} or not isinstance(rule['id'],str) or not rule['id'] or rule['id'] in seen:raise ValueError('Invalid or duplicate responder ID')
        seen.add(rule['id']);channels=list(names(rule['channels'],'channels',allow_empty=False))
        steps=rule['steps']
        if not isinstance(steps,list) or not 1<=len(steps)<=64:raise ValueError('A responder needs 1..64 steps')
        for step in steps:
            if set(step)!={'tool','arguments'} or not isinstance(step['tool'],str) or not step['tool'] or not isinstance(step['arguments'],dict):raise ValueError('Invalid responder step')
            freeze(step['arguments'])
        result.append(dict(id=rule['id'],channels=channels,steps=deepcopy(steps)))
    return result


def configure(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the host may configure signal responders')
    target=p['target']
    if target not in b.network.nodes:raise KeyError(target)
    rules=validate(p['responders'])
    b.extension_state.setdefault('signal_response',{})[target]=rules
    return dict(target=target,responders=len(rules))


def register(s):s.rpc('signal_response_configure',configure,mutation=True)
