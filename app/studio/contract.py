"""v4 component manifest and Module class entry validation."""
import importlib.util
import json
import re
import sys
from hashlib import sha256
from pathlib import Path, PurePosixPath
from jsonschema import Draft202012Validator
from domain.core import Module

SCHEMA = {'type':'object', 'additionalProperties':False,
 'required':['format','id','version','entry','node_types','requires','config_schema','state_schema','operations','signals'],
 'properties':{
 'format':{'const':'nexarbor-module/v4'},
 'id':{'type':'string','pattern':r'^[a-z][a-z0-9_.-]+$'},
 'version':{'type':'string','pattern':r'^\d+\.\d+\.\d+$'},
 'name':{'type':'string','minLength':1,'maxLength':160},
 'agent_tools':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['id','name','description','operation'],'properties':{key:{'type':'string','minLength':1} for key in ('id','name','description','operation')}}},
 'description':{'type':'string','maxLength':4000},
 'preview':{'type':'string','maxLength':350000,'pattern':r'^data:image/(png|jpeg|webp|svg\+xml)(;base64)?,[^\r\n]+$'},
 'entry':{'type':'string','pattern':r'^[A-Za-z0-9_./-]+\.py:[A-Za-z_]\w*$'},
 'node_types':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string','pattern':r'^[a-z][a-z0-9_]*$'}},
 'requires':{'type':'array','uniqueItems':True,'items':{'type':'string'}},
 'config_schema':{'type':'object'}, 'state_schema':{'type':'object'},
 'frontend':{'type':'object','additionalProperties':False,'anyOf':[{'required':['entry']},{'required':['display_as']}],
    'properties':{'entry':{'type':'string','minLength':1},'title':{'type':'string','minLength':1},
                  'display_as':{'enum':['subnode']},'channel_groups':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['label','field'],'properties':{'label':{'type':'string','minLength':1},'field':{'type':'string','minLength':1}}}},
                  'height':{'type':'integer','minimum':160,'maximum':900},'preview_operation':{'type':'string','minLength':1}}},
 'operations':{'type':'array','items':{'type':'object','additionalProperties':False,
   'required':['name','parameters','result'], 'properties':{
    'description':{'type':'string'}, 'name':{'type':'string','minLength':1}, 'channels':{'oneOf':[{'type':'array','uniqueItems':True,'items':{'type':'string','minLength':1}},{'type':'object','additionalProperties':False,'required':['config'],'properties':{'config':{'type':'string','minLength':1}}}]},
    'parameters':{'type':'object'}, 'result':{'type':'object'}}}},
 'signals':{'oneOf':[{'type':'array','uniqueItems':True,'items':{'type':'string','minLength':1}},
    {'type':'object','additionalProperties':False,'required':['config'],'properties':{'config':{'type':'string','minLength':1}}}]}}}

def channel_schema(schema):
    if not isinstance(schema,dict):return
    props=schema.get('properties',{})
    fields=[k for k,v in props.items() if k.endswith('channels') and v.get('type')=='array']
    if fields:props.setdefault('channel_modes',{'type':'object','title':'频道匹配模式','additionalProperties':{'enum':['allow','deny']}})
    for value in list(props.values()):channel_schema(value)
    if isinstance(schema.get('items'),dict):channel_schema(schema['items'])

def manifest(folder):
    result=json.loads((Path(folder)/'module.json').read_text(encoding='utf-8'))
    if result.get('format')!='nexarbor-module/v4':
        raise ValueError('Only nexarbor-module/v4 is supported; old modules are not migrated automatically')
    Draft202012Validator(SCHEMA).validate(result)
    channel_schema(result['config_schema'])
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
    if result.get('frontend',{}).get('preview_operation') and result['frontend']['preview_operation'] not in seen:raise ValueError('预览必须引用已声明操作')
    frontend_file(folder,result)
    return result


def frontend_file(folder,specification):
    """可选页面必须是组件目录内的自包含 HTML 文件。"""
    page=specification.get('frontend')
    if page is None or not page.get('entry'):return None
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
    relative,class_name=specification['entry'].split(':',1)
    source=(folder/relative).resolve()
    if not source.is_relative_to(folder): raise ValueError('Module entry escapes its directory')
    key='nexarbor_user_'+re.sub(r'\W','_',specification['id'])+'_'+sha256(str(folder).encode()).hexdigest()[:16]
    # 每个源码版本独立导入相对辅助文件；旧实例仍持有旧模块对象，直到显式重新装配。
    for loaded in list(sys.modules):
        if loaded == key or loaded.startswith(key+'.'):sys.modules.pop(loaded,None)
    spec=importlib.util.spec_from_file_location(key,source,submodule_search_locations=[str(folder)])
    module=importlib.util.module_from_spec(spec);sys.modules[key]=module
    try:
        spec.loader.exec_module(module)
        definition=getattr(module,class_name)
        if not isinstance(definition,type) or not issubclass(definition,Module):raise TypeError('组件入口必须是 Module 子类')
        for operation in specification['operations']:
            if not callable(getattr(definition,operation['name'],None)):raise ValueError('公开操作没有对应方法：'+operation['name'])
        if specification['signals'] and not callable(getattr(definition,'on_signal',None)):raise ValueError('信号声明需要 on_signal 方法')
    except BaseException:
        sys.modules.pop(key,None);raise
    return specification,definition
