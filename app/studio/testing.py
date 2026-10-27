"""制作模块的真实核心测试夹具；隔离文件，默认不执行模型或外部工具。"""
import asyncio
from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from jsonschema import Draft202012Validator
from adapt.harness.executor import NativeExecutor
from app.runtime.backend import Backend
from app.network_saver import NetworkSaver
from app.runtime.context_packets import apply_context_packet
from app.runtime.module_signals import ModuleSignals
from app.runtime.requester import as_requester,requester_id
from app.runtime.signal_authority import signal_authority
from app.projects.host_tools import host_tool_name
from app.runtime import ports
from domain.core import CallableTool,Link,MarkdownNode,Network,Node,NodeInfo,access
from domain.agent import MarkdownAgentNode
from domain.signals import Signal
from .modules import ProjectModules
from .port_testing import checked_executor,environment_contracts

ROOT=Path(__file__).resolve().parents[2]

class Visit:
    def __init__(self,h,actor,strength,channels):self.h=h;self._access_origin=h.network.get(actor);self.strength=strength;self.channels=channels
    @access()
    async def call(self,node,target,module,operation,p):
        if node.info.node_id!=target:return
        return await self.h.local_call(node,module,operation,p)
    @access()
    async def invoke(self,node,target,name,p):
        if node.info.node_id!=target:return
        tool=next(tool for tool in node.tools if tool.name==name)
        Draft202012Validator(tool.parameters).validate(p)
        value=tool.invoke(**p)
        return (await value if inspect.isawaitable(value) else value,)

class ModuleHarness:
    def __init__(self,module_directory,*,library=None,_runtime_directory=None,_initial_document=None,_configure_saver=None,_store=None):
        source=Path(module_directory).resolve() if module_directory is not None else None
        self.spec=json.loads((source/'module.json').read_text(encoding='utf-8')) if source else {}
        self.module_id=self.spec.get('id')
        self.library=dict(library if library is not None else json.loads(os.environ.get('NEXARBOR_TEST_MODULES','{}')))
        if source:self.library[self.module_id]=source
        dependencies=source/'dependencies' if source else None
        if dependencies is not None and dependencies.exists():
            for manifest in dependencies.rglob('module.json'):
                item=json.loads(manifest.read_text(encoding='utf-8'));self.library.setdefault(item['id'],manifest.parent)
        self.temporary=TemporaryDirectory(prefix='studio-behavior-',dir=ROOT/'build') if _runtime_directory is None else None
        self.folder=Path(self.temporary.name) if self.temporary is not None else Path(_runtime_directory).resolve()
        self.folder.mkdir(parents=True,exist_ok=True)
        self._active_agents=set();self.agent_callback=None;self.port_contracts=environment_contracts();self.providers={};self.definitions={};self.last_agent_views={};self._closed=False
        saver=NetworkSaver(read_text=self._read_text)
        claimed=False
        try:
            self.modules=ProjectModules(SimpleNamespace(directory=self.folder,saver=saver),self.library,agent_run=self.run_agent)
            if _configure_saver is not None:_configure_saver(saver)
            claimed=True
            self.backend=Backend(self.folder,network=Network(),saver=saver,initial_document=_initial_document,store=_store)
            self.modules.backend=self.backend
            self._configure_runtime()
        except BaseException:
            if hasattr(self,'backend'):self.backend.close()
            elif not claimed and _store is not None:_store.close()
            if self.temporary is not None:self.temporary.cleanup()
            raise

    @property
    def network(self):return self.backend.network

    def _configure_runtime(self):
        self.backend.agent_executor=self.run_agent
        self.executor=NativeExecutor(self.network,None,bindings=self.backend.bindings,states=self.backend.agents,locks=self.backend.node_locks)
        self.signals=ModuleSignals(self.backend.signals);self.signals.refresh()

    def add_node(self,id,name=None,*,agent=False,description=''):
        if agent:
            file=self.folder/'data'/(id.replace('/','_')+'.md');file.parent.mkdir(parents=True,exist_ok=True);file.write_text('',encoding='utf-8');node=MarkdownAgentNode(NodeInfo(id,name or id,description),file)
        else:node=Node(NodeInfo(id,name or id,description))
        self.network.add(node);return node

    def add_text(self,id,text='',name=None):
        file=self.folder/'data'/(id.replace('/','_')+'.md');file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text,encoding='utf-8')
        node=MarkdownNode(NodeInfo(id,name or id),file);self.network.add(node);return node

    def connect(self,source,target,*,channels,threshold=1,multiplier=1):
        from domain.core import Multiplier
        edge=Link(target,channels,threshold,Multiplier(multiplier));self.network.get(source).links.add(edge);return edge

    def disconnect(self,source,target):
        links=self.network.get(source).links
        for link in tuple(links):
            if link.target_id==target:links.remove(link)

    def read(self,node):return self.network.get(node).dataer.read()
    def write(self,node,value):return self.network.get(node).dataer.write(value)

    def mount(self,node,*,module=None,config=None,state=None,access=None):
        instance=self.modules.mount(self.network.get(node),module or self.module_id,config,state,access);self.signals.refresh();return instance

    async def local_call(self,node,module,operation,p):
        spec=self.modules.manifests[module];definition=next(item for item in spec['operations'] if item['name']==operation)
        Draft202012Validator(definition['parameters']).validate(p)
        result=getattr(node.modules.get(module),operation)(**p)
        value=await result if inspect.isawaitable(result) else result
        return dict(status='ok',data=value)

    async def call(self,node,operation,parameters=None,*,actor=None,module=None,strength=2,channels=()):
        actor=actor or node
        with as_requester(actor):result=await Visit(self,actor,strength,channels).call(node,module or self.module_id,operation,parameters or {})
        if result.get(node) is None:raise PermissionError('目标不在本次 access 的可达范围')
        return result[node]

    def register_tools(self,provider,definitions,execute):
        if provider=='runtime' and any(item['name']=='agent_run' for item in definitions):raise ValueError('用 register_agent 只替换模型计算')
        self.providers[provider]=checked_executor(provider,definitions,execute,self.port_contracts)
        for definition in definitions:self.definitions[provider+':'+definition['name']]=definition

    def _read_text(self,path,roots=()):return ports.read_text(self.folder,dict(path=path,roots=roots))

    def register_readonly_ports(self):
        async def execute(actor,name,p):
            if name=='read_text':return self._read_text(p['path'],p.get('roots',()))
            if name!='checkpoint' and self.agent_callback is None:raise PermissionError('测试环境禁用模型和外部副作用')
            return await ports.execute(self.backend,actor,name,p)
        self.register_tools('runtime',[ports.TEXT_READ,ports.DEFINITIONS[1]],execute)

    def make_port(self,node,ref):
        definition=self.definitions[ref];provider,name=ref.split(':',1)
        async def execute(**p):
            if provider not in self.providers:raise PermissionError('测试副本未启用外部端口：'+ref)
            return await self.providers[provider](requester_id.get() or node,name,p)
        return CallableTool(host_tool_name(node,ref),execute,definition.get('description',''),definition['parameters'])

    def offer(self,node,ref,channels):
        tool=self.make_port(node,ref);self.network.get(node).install(tool)
        self.backend.saver.tables.tool_types[tool.name]=lambda current,record:self.make_port(current.info.node_id,ref)
        metadata=self.backend.extension_state.setdefault('node_properties',{}).setdefault(node,{})
        metadata.setdefault('offered_ports',[]).append(dict(ref=ref,channels=list(channels)));return tool

    async def invoke(self,actor,target,ref,parameters=None,*,strength=2,channels=()):
        with as_requester(actor):result=await Visit(self,actor,strength,channels).invoke(target,host_tool_name(target,ref),parameters or {})
        if target not in result or result[target] is None:raise PermissionError('目标不在本次 access 的可达范围')
        return result[target][0]

    def bind_agent(self,actor,binding):
        if self.network.get(actor).node_type!='agent':raise ValueError('执行绑定要求 Agent 节点')
        self.backend.bindings[actor]=deepcopy(binding)
    def register_agent(self,callback):self.agent_callback=callback
    async def prepare_agent(self,actor):return await self.executor.prepare(dict(actor=actor))
    async def acknowledge_agent(self,actor,events):return self.executor.ack(dict(actor=actor,events=[{'source':e['source'],'id':e['id']} for e in events]))
    def apply_context(self,actor,packet,source='prepare:test'):
        node=self.network.get(actor)
        if not apply_context_packet(node,self.backend.agents.setdefault(actor,{}),source,packet):raise ValueError('需要 nexarbor-context/v1 准备结果')
        return node.inputs.snapshot()
    async def agent_tool(self,actor,name,arguments):
        result=await self.executor.invoke(dict(actor=actor,name=name,arguments=arguments))
        if isinstance(result,dict) and result.get('status')=='forbidden':raise PermissionError('; '.join(result['errors']))
        return result
    async def run_agent(self,actor,message='',**options):
        if self.agent_callback is None:raise RuntimeError('测试副本未启用模型；用 register_agent 只替换模型计算')
        if actor in self._active_agents:raise RuntimeError('Agent already running')
        if self.backend.node_locks.current:raise RuntimeError('不能持节点事务等待模型')
        self._active_agents.add(actor)
        try:
            self.last_agent_views[actor]=await self.prepare_agent(actor);await self.acknowledge_agent(actor,self.last_agent_views[actor]['inputs'])
            async with self.backend.node_locks.suspend_access():result=await self.agent_callback(actor,message)
            return dict(status='completed',output=result)
        finally:self._active_agents.remove(actor)

    async def emit(self,actor,channels,*,strength=3,content=None,signal_id=None):
        parameters=dict(origin=actor,channels=channels,strength=strength,content=content)
        if signal_id is not None:parameters['signal_id']=signal_id
        with as_requester(actor),signal_authority(actor,strength):receipt=self.backend.signals.emit(Signal(**parameters))
        return await self.backend.signals.wait(receipt['signal_id'])

    async def run_pulse(self,pulse,cycles=1,timeout_seconds=86400,*,expect_complete=True):
        self.last_pulse_report=await self.network.get(pulse).run(self.backend.signals,cycles=cycles,timeout_seconds=timeout_seconds)
        if expect_complete and self.last_pulse_report['status']!='completed':raise AssertionError(self.last_pulse_report['status'])
        return self.last_pulse_report

    async def restart(self):
        self.backend.save(full=True);saver=self.backend.saver;self.backend.close();self.backend=Backend(self.folder,saver=saver);self.modules.backend=self.backend;self._configure_runtime()

    async def close(self):
        if self._closed:return
        self._closed=True
        if self.backend.signals._active:await asyncio.gather(*(self.backend.signals.cancel(key) for key in tuple(self.backend.signals._active)))
        self.backend.close()
        if self.temporary is not None:self.temporary.cleanup()
