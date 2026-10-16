"""Deterministic JSON state deltas; replay values, never commands or model calls."""
import json
from hashlib import sha256
from copy import deepcopy

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def checksum(value):return sha256(canonical(value).encode('utf-8')).hexdigest()
def diff(old,new,path=None):
    path=[] if path is None else path
    if type(old) is not type(new):return [dict(op='set',path=path,value=deepcopy(new))]
    if isinstance(old,dict):
        ops=[dict(op='remove',path=path+[key]) for key in sorted(old.keys()-new.keys())]
        for key in sorted(new):
            ops.extend(diff(old[key],new[key],path+[key]) if key in old else [dict(op='set',path=path+[key],value=deepcopy(new[key]))])
        return ops
    if isinstance(old,list):
        ops=[]
        for index in range(min(len(old),len(new))):ops.extend(diff(old[index],new[index],path+[index]))
        if len(new)>len(old):ops.append(dict(op='append',path=path,value=deepcopy(new[len(old):])))
        if len(new)<len(old):ops.append(dict(op='truncate',path=path,length=len(new)))
        return ops
    return [] if old==new and (not isinstance(old,float) or canonical(old)==canonical(new)) else [dict(op='set',path=path,value=deepcopy(new))]
def apply(document,operations):
    document=deepcopy(document)
    for operation in operations:
        path=operation['path'];target=document
        if not isinstance(path,list) or any(type(key) not in (str,int) for key in path):raise ValueError('Invalid delta path')
        if not path and operation['op']=='set':document=deepcopy(operation['value']);continue
        for key in path[:-1]:target=target[key]
        if operation['op']=='set':target[path[-1]]=deepcopy(operation['value'])
        elif operation['op']=='remove':del target[path[-1]]
        elif operation['op'] in ('append','truncate'):
            array=target[path[-1]] if path else document
            if not isinstance(array,list):raise ValueError('Delta requires an array')
            if operation['op']=='append':array.extend(deepcopy(operation['value']))
            else:del array[operation['length']:]
        else:raise ValueError('Unknown delta operation')
    return document
