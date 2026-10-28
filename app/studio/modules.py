"""加载项目自己的 v4 Module 类；只注入声明在构造器中的运行端口。"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
from inspect import signature
import json
from pathlib import Path
import sys
from types import ModuleType
from app.projects.module_tools import install_tools,bind_tools
from app.runtime.module_emitter import emit_module_signal
from domain.core import Module
from jsonschema import Draft202012Validator
from .unavailable import UnavailableModule

class ProjectModules:
    def __init__(self,backend,library,*,agent_run=None,instantiate=None,project_directory=None,tolerate=False):
        self.backend=backend;self.project_directory=Path(project_directory).resolve() if project_directory is not None else backend.directory;self.library={key:Path(value).resolve() for key,value in library.items()};self.agent_run=agent_run;self.instantiate=instantiate
        self.tolerate=tolerate
        self.builtins={key:backend.saver.tables.module_types[key] for key in ('tool_discovery','context.assembler')}
        self.manifests={key:json.loads((folder/'module.json').read_text(encoding='utf-8')) for key,folder in self.library.items()}
        self.defaults={key:json.loads((folder/'example.json').read_text(encoding='utf-8')) if (folder/'example.json').exists() else {} for key,folder in self.library.items()};self.classes={}
        backend.saver.tables.restore_modules=self.restore_tables
        backend.saver.tables.module_types.update({key:(lambda record,key=key:self.restore(key,record)) for key in self.library if key not in self.builtins})

    def restore_tables(self,node,records):
        modules={};specs={record['module_id']:record for record in records}
        def load(key,active=()):
            if key in modules:return modules[key]
            record=specs[key]
            try:
                if key in active:raise ValueError('模块依赖循环：'+key)
                module=self.restore(key,record)
                definition=self.manifests.get(key,{})
                if definition and node.node_type not in definition['node_types']:raise ValueError('模块不支持节点类型：'+node.node_type)
                for field in ('config','state'):Draft202012Validator(definition.get(field+'_schema',{})).validate(record.get(field,{}))
                for dependency in definition.get('requires',record.get('modules',[])):
                    if dependency not in specs:raise ValueError('缺少依赖：'+dependency)
                    other=load(dependency,(*active,key))
                    if isinstance(other,UnavailableModule):raise ValueError('依赖不可用：'+dependency+'；'+other.unavailable_reason)
            except Exception as error:
                if not self.tolerate:raise
                module=UnavailableModule(key,record,str(error))
            modules[key]=module
            return module
        for key in specs:load(key)
        return modules

    def module_type(self,key):
        if key in self.classes:return self.classes[key]
        folder=self.library[key];spec=self.manifests[key]
        if spec['format']!='nexarbor-module/v4':raise ValueError('模块必须使用 nexarbor-module/v4')
        relative,name=spec['entry'].split(':',1);file=(folder/relative).resolve()
        if not file.is_relative_to(folder) or file.suffix!='.py':raise ValueError('模块入口必须位于自己的目录中')
        group='_nexarbor_project_'+sha256(str(folder.parent).encode()).hexdigest()
        if group not in sys.modules:
            parent=ModuleType(group);parent.__path__=[str(folder.parent)];sys.modules[group]=parent
        package=group+'.module_'+sha256(str(folder).encode()).hexdigest();parent=ModuleType(package);parent.__path__=[str(folder)];sys.modules[package]=parent
        entry=importlib.util.spec_from_file_location(package+'.entry',file);loaded=importlib.util.module_from_spec(entry);sys.modules[entry.name]=loaded;entry.loader.exec_module(loaded)
        cls=getattr(loaded,name)
        if not isinstance(cls,type) or not issubclass(cls,Module):raise TypeError('v4 入口必须是 Module 子类')
        self.classes[key]=cls;return cls

    def ports(self):
        return dict(directory=self.backend.directory,project_directory=self.project_directory,node_access=lambda nodes:self.backend.node_locks.access(nodes),transaction=lambda nodes,**p:self.backend.node_locks.transaction(nodes,**p),
                    emit=lambda node,**p:emit_module_signal(self.backend.signals,node,**p),
                    checkpoint=self.checkpoint,agent_run=self.run_agent,instantiate=self.create_nodes,wait_signal=lambda signal_id:self.backend.signals.wait(signal_id),manage=self.manage)

    async def manage(self,module,operation,parameters):
        if not hasattr(self.backend,'network_administrator'):
            from projects.discussion_collaboration.modules.network_administrator.service import Administrator
            self.backend.network_administrator=Administrator(self.backend)
        return await self.backend.network_administrator.operation(module,operation,parameters)

    async def checkpoint(self,**p):
        await self.backend.node_locks.wait_prepared()
        return self.backend.save(**p)
    async def run_agent(self,actor,message='',**p):
        if self.agent_run is None:raise RuntimeError('此宿主未启用真实模型执行')
        return await self.agent_run(actor,message,**p)
    async def create_nodes(self,actor,**p):
        if self.instantiate is None:raise RuntimeError('此宿主未登记运行模板')
        return await self.instantiate(actor,**p)

    def restore(self,key,record):
        if key in self.builtins:
            value=dict(record)
            if key=='tool_discovery':
                value={**dict(channels=(),strength=1,channel_mode='allow'),**value}
            return self.builtins[key](value)
        cls=self.module_type(key);parameters=signature(cls).parameters
        options={name:port for name,port in self.ports().items() if name in parameters}
        options['config']=deepcopy(record.get('config',{}))
        if 'state' in parameters:options['state']=deepcopy(record.get('state',{}))
        options.update({name:record[name] for name in ('channels','strength','channel_mode') if name in record})
        module=cls(**options)
        if module.module_id!=key:raise ValueError('Module 标识必须与 module.json 的 id 一致：'+key)
        signals=self.manifests[key].get('signals',[])
        module.signal_channels=tuple(module.config.get(signals['config'],())) if isinstance(signals,dict) else tuple(signals)
        # Modules may build tools themselves; otherwise agent_tools declares them.
        if not module.tools.members:module._tool_specs=install_tools(module,self.library[key]/'module.py')
        return module

    def create(self,node,key,config=None,state=None,access=None,*,pending=None):
        current=node.modules.get(key)
        if current is not None:return current
        pending={} if pending is None else pending
        if key in pending:return pending[key]
        defaults=self.defaults.get(key,{})
        record=dict(config=defaults.get('config',{}) if config is None else config,state=defaults.get('state',{}) if state is None else state,**(defaults.get('access',{}) if access is None else access))
        try:
            module=pending[key]=self.restore(key,record)
            definition=self.manifests.get(key,{})
            if definition and node.node_type not in definition['node_types']:raise ValueError('模块不支持节点类型：'+node.node_type)
            for field in ('config','state'):Draft202012Validator(definition.get(field+'_schema',{})).validate(record.get(field,{}))
            module._dependencies=tuple(self.create(node,dependency,pending=pending) for dependency in definition.get('requires',[]))
            for dependency in module.modules:
                if isinstance(dependency,UnavailableModule):raise ValueError('依赖不可用：'+dependency.module_id+'；'+dependency.unavailable_reason)
        except Exception as error:
            if not self.tolerate:raise
            module=pending[key]=UnavailableModule(key,record,str(error))
            module._dependencies=tuple(pending[dependency] for dependency in self.manifests.get(key,{}).get('requires',[]) if dependency in pending)
            module.saved_dependencies=[dependency.module_id for dependency in module.modules]
        return module

    def mount(self,node,key,config=None,state=None,access=None):
        pending={};module=self.create(node,key,config,state,access,pending=pending);node.install(module)
        for item in pending.values():
            if hasattr(item,'_tool_specs'):bind_tools(item,node,item._tool_specs)
        return module
