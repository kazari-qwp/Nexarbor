"""有限批次出边修改；权限与锁由调用端口检查。"""
from .interface import Interface

def edge_changes(value):
    if not isinstance(value,list) or not value or len(value)>1000:raise ValueError('连接修改必须是 1 至 1000 项的列表')
    result=[]
    for item in value:
        if not isinstance(item,dict) or set(item)!={'source','target','action','metadata'}:raise ValueError('连接修改需要 source、target、action、metadata')
        if not isinstance(item['source'],str) or not item['source'] or item['action'] not in ('add','remove'):raise ValueError('连接修改起点或动作无效')
        result.append(dict(source=item['source'],action=item['action'],edge=Interface(item['target'],item['metadata'])))
    return result
