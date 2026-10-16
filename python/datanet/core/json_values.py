"""Immutable JSON values shared by signals and interface metadata."""
import math

class FrozenDict(dict):
    def _deny(self,*args,**kwargs):raise TypeError('JSON value is immutable')
    __setitem__=__delitem__=clear=pop=popitem=setdefault=update=__ior__=_deny
    def __deepcopy__(self,memo):return self

def freeze(value):
    if value is None or type(value) in (str,bool,int):return value
    if type(value) is float and math.isfinite(value):return value
    if isinstance(value,(list,tuple)):return tuple(freeze(v) for v in value)
    if isinstance(value,dict) and all(type(k) is str for k in value):return FrozenDict((k,freeze(v)) for k,v in value.items())
    raise ValueError('Expected finite JSON values and string object keys')

def thaw(value):
    if isinstance(value,dict):return {k:thaw(v) for k,v in value.items()}
    if isinstance(value,tuple):return [thaw(v) for v in value]
    return value

def names(value,label,allow_empty=True):
    if not isinstance(value,(list,tuple)) or any(not isinstance(v,str) or not v.strip() for v in value):raise ValueError(label+' must contain nonempty names')
    result=tuple(dict.fromkeys(value))
    if not allow_empty and not result:raise ValueError(label+' must not be empty')
    return result
