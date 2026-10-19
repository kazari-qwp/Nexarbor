"""v3 component manifest and fixed async entry validation."""
import importlib.util
import json
import re
import sys
from hashlib import sha256
from pathlib import Path, PurePosixPath
from jsonschema import Draft202012Validator
from datanet.core.module_protocol import ModuleDefinition, Activation, ComponentResult

SCHEMA = {'type':'object', 'additionalProperties':False,
 'required':['format','id','version','entry','node_types','requires','config_schema','state_schema','operations','signals'],
 'properties':{
 'format':{'const':'nexarbor-module/v3'},
 'id':{'type':'string','pattern':r'^[a-z][a-z0-9_.-]+$'},
 'version':{'type':'string','pattern':r'^\d+\.\d+\.\d+$'},
 'name':{'type':'string','minLength':1,'maxLength':160},
 'agent_tools':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['id','name','description','operation'],'properties':{key:{'type':'string','minLength':1} for key in ('id','name','description','operation')}}},
 'description':{'type':'string','maxLength':4000},
 'preview':{'type':'string','maxLength':350000,'pattern':r'^data:image/(png|jpeg|webp|svg\+xml)(;base64)?,[^\r\n]+$'},
 'entry':{'const':'module.py:execute'},
 'node_types':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string','pattern':r'^[a-z][a-z0-9_]*$'}},
 'requires':{'type':'array','uniqueItems':True,'items':{'type':'string'}},
 'config_schema':{'type':'object'}, 'state_schema':{'type':'object'},
 'frontend':{'type':'object','additionalProperties':False,'required':['entry'],
    'properties':{'entry':{'type':'string','minLength':1},'title':{'type':'string','minLength':1},
                  'height':{'type':'integer','minimum':160,'maximum':900},'preview_operation':{'type':'string','minLength':1}}},
 'tool_provider':{'type':'object','additionalProperties':False,'required':['list','invoke'],
    'properties':{'list':{'type':'string','minLength':1},'invoke':{'type':'string','minLength':1}}},
 'operations':{'type':'array','items':{'type':'object','additionalProperties':False,
   'required':['name','channels','parameters','result'], 'properties':{
    'name':{'type':'string','minLength':1}, 'channels':{'type':'array','uniqueItems':True,'items':{'type':'string','minLength':1}},
    'parameters':{'type':'object'}, 'result':{'type':'object'}}}},
 'signals':{'oneOf':[{'type':'array','uniqueItems':True,'items':{'type':'string','minLength':1}},
    {'type':'object','additionalProperties':False,'required':['config'],'properties':{'config':{'type':'string','minLength':1}}}]}}}

def manifest(folder):
    result=json.loads((Path(folder)/'module.json').read_text(encoding='utf-8'))
    if result.get('format')!='nexarbor-module/v3':
        raise ValueError('Only nexarbor-module/v3 is supported; old modules are not migrated automatically')
    Draft202012Validator(SCHEMA).validate(result)
    for key in ('config_schema','state_schema'): Draft202012Validator.check_schema(result[key])
    seen=set()
    for operation in result['operations']:
        if operation['name'] in seen: raise ValueError('Duplicate operation')
        seen.add(operation['name'])
        for key in ('parameters','result'): Draft202012Validator.check_schema(operation[key])
        if operation['parameters'].get('type')!='object': raise ValueError('Parameters must be an object')
    tools=set()
    for tool in result.get('agent_tools',[]):
        if tool['id'] in tools or tool['operation'] not in seen:raise ValueError('模块工具重复或引用未声明操作')
        tools.add(tool['id'])
    if tools and result.get('tool_provider'):raise ValueError('静态工具与动态工具提供器不能同时声明')
    if result.get('frontend',{}).get('preview_operation') and result['frontend']['preview_operation'] not in seen:raise ValueError('预览必须引用已声明操作')
    frontend_file(folder,result)
    return result


def frontend_file(folder,specification):
    """可选页面必须是组件目录内的自包含 HTML 文件。"""
    page=specification.get('frontend')
    if page is None:return None
    entry=page['entry'];relative=PurePosixPath(entry)
    if '\\' in entry or ':' in entry or relative.is_absolute() or '..' in relative.parts or relative.suffix!='.html':
        raise ValueError('模块前端入口必须是组件内的相对 HTML 路径')
    root=Path(folder).resolve();target=(root/entry).resolve()
    if not target.is_relative_to(root) or not target.is_file():raise ValueError('模块前端入口不存在或越出组件目录')
    if target.stat().st_size>1024*1024:raise ValueError('模块前端文件不能超过 1 MiB')
    target.read_text(encoding='utf-8')
    return target

def factory(folder):
    folder=Path(folder).resolve(); specification=manifest(folder)
    source=(folder/'module.py').resolve()
    if not source.is_relative_to(folder): raise ValueError('Module entry escapes its directory')
    key='nexarbor_user_'+re.sub(r'\W','_',specification['id'])+'_'+sha256(str(folder).encode()).hexdigest()[:16]
    # 每个源码版本独立导入相对辅助文件；旧实例仍持有旧模块对象，直到显式重新装配。
    for loaded in list(sys.modules):
        if loaded == key or loaded.startswith(key+'.'):sys.modules.pop(loaded,None)
    spec=importlib.util.spec_from_file_location(key,source,submodule_search_locations=[str(folder)])
    module=importlib.util.module_from_spec(spec);sys.modules[key]=module
    try:
        spec.loader.exec_module(module)
        definition=ModuleDefinition(module.execute, tool_provider=specification.get('tool_provider'),agent_tools=specification.get('agent_tools',[]),
            **{key:specification[key] for key in ('operations','signals','node_types','config_schema','state_schema')})
    except BaseException:
        sys.modules.pop(key,None);raise
    return specification,definition
