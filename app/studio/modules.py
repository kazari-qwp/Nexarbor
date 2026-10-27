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

class ProjectModules:
    def __init__(self,backend,library,*,agent_run=None,instantiate=None,project_directory=None):
        self.backend=backend;self.project_directory=Path(project_directory).resolve() if project_directory is not None else backend.directory;self.library={key:Path(value).resolve() for key,value in library.items()};self.agent_run=agent_run;self.instantiate=instantiate
        self.builtins={key:backend.saver.tables.module_types[key] for key in ('tool_discovery','context.assembler')}
        self.manifests={key:json.loads((folder/'module.json').read_text(encoding='utf-8')) for key,folder in self.library.items()}
        self.defaults={key:json.loads((folder/'example.json').read_text(encoding='utf-8')) if (folder/'example.json').exists() else {} for key,folder in self.library.items()};self.classes={}
        backend.saver.tables.module_types.update({key:(lambda record,key=key:self.restore(key,record)) for key in self.library if key not in self.builtins})

    def module_type(self,key):
        if key in self.classes:return self.classes[key]
        folder=self.library[key];spec=self.manifests[key]
        if spec['format']!='nexarbor-module/v4':raise ValueError('模块必须使用 nexarbor-module/v4')
        relative,name=spec['entry'].split(':',1);file=(folder/relative).resolve()
        if not file.is_relative_to(folder) or file.suffix!='.py':raise ValueError('模块入口必须位于自己的目录中')
        package='_nexarbor_project_'+sha256(str(folder).encode()).hexdigest();parent=ModuleType(package);parent.__path__=[str(folder)];sys.modules[package]=parent
        entry=importlib.util.spec_from_file_location(package+'.entry',file);loaded=importlib.util.module_from_spec(entry);sys.modules[entry.name]=loaded;entry.loader.exec_module(loaded)
        cls=getattr(loaded,name)
        if not isinstance(cls,type) or not issubclass(cls,Module):raise TypeError('v4 入口必须是 Module 子类')
        self.classes[key]=cls;return cls

    def ports(self):
        return dict(directory=self.backend.directory,project_directory=self.project_directory,transaction=lambda nodes,**p:self.backend.node_locks.transaction(nodes,**p),
                    emit=lambda node,**p:emit_module_signal(self.backend.signals,node,**p),
                    checkpoint=self.checkpoint,agent_run=self.run_agent,instantiate=self.create_nodes,wait_signal=lambda signal_id:self.backend.signals.wait(signal_id))

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
        defaults=self.defaults[key]
        record=dict(config=defaults.get('config',{}) if config is None else config,state=defaults.get('state',{}) if state is None else state,**(defaults.get('access',{}) if access is None else access))
        module=pending[key]=self.restore(key,record)
        module._dependencies=tuple(self.create(node,dependency,pending=pending) for dependency in self.manifests[key].get('requires',[]))
        return module

    def mount(self,node,key,config=None,state=None,access=None):
        pending={};module=self.create(node,key,config,state,access,pending=pending);node.install(module)
        for item in pending.values():
            if hasattr(item,'_tool_specs'):bind_tools(item,node,item._tool_specs)
        return module
