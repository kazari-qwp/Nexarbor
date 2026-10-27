"""项目模块声明的工具装配；沿用旧稳定名称，不改变工具箱接口。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from domain.core import CallableTool

def install_tools(module,file):
    definition=json.loads(Path(file).with_name('module.json').read_text(encoding='utf-8'))
    operations={item['name']:item for item in definition['operations']}
    specs=definition.get('agent_tools',[])
    for spec in specs:
        operation=operations[spec['operation']]
        module.tools._add(CallableTool(spec['id'],getattr(module,spec['operation']),spec.get('description',operation.get('description',definition.get('description',''))),deepcopy(operation['parameters'])))
    return specs

def bind_tools(module,node,specs):
    source=sha256((node.info.node_id+'\0'+module.module_id).encode()).hexdigest()[:24]
    for tool,spec in zip(module.tools,specs):
        tool.name='mod_'+sha256((source+'\0'+spec['id']).encode()).hexdigest()[:24]
        tool.description=node.info.node_id+' · '+spec['name']+' · '+tool.description
