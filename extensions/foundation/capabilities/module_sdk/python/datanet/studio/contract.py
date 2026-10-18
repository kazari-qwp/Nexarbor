"""Local-only v2 contract; old modules fail before their source is imported."""
import importlib.util
import json
import re
import sys
from hashlib import sha256
from copy import deepcopy
from pathlib import Path
from jsonschema import Draft202012Validator
from datanet.core.node_modules import NodeModule
from datanet.core.json_values import names

SCHEMA={'type':'object','required':['format','id','version','entry','node_types','requires','config_schema','state_schema','tools','signals'],
 'additionalProperties':False,'properties':{
 'format':{'const':'nexarbor-module/v2'},'id':{'type':'string','pattern':r'^[a-z][a-z0-9_.-]+$'},
 'version':{'type':'string','pattern':r'^\d+\.\d+\.\d+$'},'entry':{'const':'module.py:Module'},
 'node_types':{'type':'array','minItems':1,'uniqueItems':True,'items':{'enum':['node','text_file','agent','pulse']}},
 'requires':{'type':'array','uniqueItems':True,'items':{'type':'string'}},
 'config_schema':{'type':'object'},'state_schema':{'type':'object'},
 'tools':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['name','description','parameters','channels'],
   'properties':{'name':{'type':'string','pattern':r'^[a-z][a-z0-9_]*$'},'description':{'type':'string'},'parameters':{'type':'object'},
      'channels':{'oneOf':[{'type':'array','items':{'type':'string','minLength':1}},{'type':'object','required':['config'],'additionalProperties':False,'properties':{'config':{'type':'string'}}}]}}}},
 'signals':{'type':'array','items':{'type':'string','minLength':1}},
 'operations':{'type':'array','items':{'type':'object','required':['name','parameters','channels'],'additionalProperties':False,'properties':{'name':{'type':'string','pattern':r'^[a-z][a-z0-9_]*$'},'parameters':{'type':'object'},'channels':{'type':'array','uniqueItems':True,'items':{'type':'string','minLength':1}}}}}
}}

def manifest(folder):
    result=json.loads((Path(folder)/'module.json').read_text(encoding='utf-8'))
    if result.get('format')!='nexarbor-module/v2':raise ValueError('Only local nexarbor-module/v2 is supported; migrate the old module explicitly')
    Draft202012Validator(SCHEMA).validate(result)
    for key in ['config_schema','state_schema']:Draft202012Validator.check_schema(result[key])
    if len({t['name'] for t in result['tools']})!=len(result['tools']):raise ValueError('Duplicate tool names')
    for tool in result['tools']:
        Draft202012Validator.check_schema(tool['parameters'])
        if tool['parameters'].get('type')!='object':raise ValueError('Tool parameters must be an object')
    operations=result.get('operations',[])
    if len({o['name'] for o in operations})!=len(operations):raise ValueError('Duplicate operations')
    for operation in operations:Draft202012Validator.check_schema(operation['parameters'])
    return result

class StudioModule(NodeModule):
    """Subclass setup(), declared tool methods, and optionally on_signal(context)."""
    def setup(self):pass
    def on_signal(self,context):return None
    def tool_description(self,name,default):return default
    def tool_enabled(self,name):return True
    def on_tool_denied(self,name,actor,reason):return reason
    def _checked(self,function,schema):
        import inspect
        if inspect.iscoroutinefunction(function):
            async def checked(**arguments):
                Draft202012Validator(schema).validate(arguments)
                value=await function(**arguments)
                Draft202012Validator(self.manifest['state_schema']).validate(self.state)
                return value
        else:
            def checked(**arguments):
                Draft202012Validator(schema).validate(arguments)
                value=function(**arguments)
                Draft202012Validator(self.manifest['state_schema']).validate(self.state)
                return value
        return checked
    def install(self):
        if self.context.metadata()['node_type'] not in self.manifest['node_types']:raise ValueError('Module does not support this node type')
        from datanet.core.json_values import thaw
        Draft202012Validator(self.manifest['config_schema']).validate(thaw(self.config))
        self.setup()
        Draft202012Validator(self.manifest['state_schema']).validate(self.state)
        for operation in self.manifest.get('operations',[]):
            self.operation(operation['name'],self._checked(getattr(self,operation['name']),operation['parameters']),channels=operation['channels'])
        if self.manifest['signals']:
            async def receive(context):
                value=self.on_signal(context)
                if hasattr(value,'__await__'):value=await value
                Draft202012Validator(self.manifest['state_schema']).validate(self.state)
                return value
            self.receive(self.manifest['signals'],receive)
        for tool in self.manifest['tools']:
            if not self.tool_enabled(tool['name']):continue
            channels=tool['channels']
            if isinstance(channels,dict):channels=self.config[channels['config']]
            channels=names(channels,'tool channels')
            checked=self._checked(getattr(self,tool['name']),tool['parameters'])
            def refusal(actor,reason,_name=tool['name']):return self.on_tool_denied(_name,actor,reason)
            self.tool(tool['name'],checked,description=self.tool_description(tool['name'],tool['description']),parameters=tool['parameters'],access_channels=channels,refusal=refusal)

def factory(folder):
    folder=Path(folder).resolve();specification=manifest(folder)
    source=(folder/'module.py').resolve()
    if not source.is_relative_to(folder):raise ValueError('Module entry escapes its directory')
    key='nexarbor_user_'+re.sub(r'\W','_',specification['id'])+'_'+sha256(str(folder).encode()).hexdigest()[:16]
    spec=importlib.util.spec_from_file_location(key,source,submodule_search_locations=[str(folder)])
    module=importlib.util.module_from_spec(spec);sys.modules[key]=module
    try:spec.loader.exec_module(module)
    except BaseException:sys.modules.pop(key,None);raise
    cls=getattr(module,'Module',None)
    if not isinstance(cls,type) or not issubclass(cls,StudioModule):raise TypeError('Module must extend StudioModule')
    def create(context):
        result=cls(context);result.manifest=deepcopy(specification);return result
    return specification,create
