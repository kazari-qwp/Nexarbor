"""频道名称仍是字符串列表；匹配模式独立保存，旧列表默认白名单。"""
from .json_values import names
def mode(value):
    if value not in ('allow','deny'):raise ValueError('频道模式必须是 allow 或 deny')
    return value
def matches(items, candidates, policy='allow'):
    selected=set(items);mode(policy)
    return any((c in selected) == (policy=='allow') for c in candidates)
def resolve(items, policy='allow', universe=()):
    items=names(items,'channels');mode(policy)
    return tuple(c for c in universe if c not in items) if policy=='deny' else items
