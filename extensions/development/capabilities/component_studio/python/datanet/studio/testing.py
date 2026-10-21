"""组件作者使用的真实运行时测试夹具；不是业务实现或模拟 ctx。"""
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import json,os
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.text_node import TextFileNode
from datanet.core.node_modules import NodeModules
from datanet.core.module_tools import ModuleTools
from datanet.core.external_tools import ExternalTools
from .contract import factory

class ModuleHarness:
    def __init__(self,folder,dependencies=None):
        self.folder=Path(folder).resolve();self.spec,self.definition=factory(self.folder)
        definitions={self.spec['id']:self.definition}
        paths=dependencies if dependencies is not None else json.loads(os.environ.get('DATANET_TEST_MODULES','{}'))
        for name,path in paths.items():
            if name!=self.spec['id']:definitions[name]=factory(path)[1]
        self.backend=SimpleNamespace(directory=self.folder,network=Network(),agents={},_transaction_lock=RLock(),
            components=SimpleNamespace(module_owners={},module_extensions={},module_types=definitions,enabled=set()))
        self.backend.modules=NodeModules(self.backend,definitions);self.backend.signals=self.backend.network.signals;self.backend.dispatch=lambda *a:None;self.backend.external_tools=ExternalTools(self.backend)
        self.network=self.backend.network;self.modules=self.backend.modules;self.tools=ModuleTools(self.backend)
        from .port_testing import environment_contracts
        self.backend.port_contracts=environment_contracts()
    def add_node(self,id,name=None,*,agent=False,description=''):
        node=AgentNode(id,name or id,file_path=self.folder/(id.replace('/','_')+'.md')) if agent else Node(id,name or id,None,description=description)
        self.network.add_node(node);return node
    def connect(self,source,target,channels=('test',),**kw):return self.network.nodes[source].connect(target,channels=list(channels),**kw)
    def add_text(self,id,text='',name=None):
        file=self.folder/'test-data'/(id.replace('/','_')+'.txt');file.parent.mkdir(exist_ok=True);file.write_text(text,encoding='utf-8')
        node=TextFileNode(id,name or id,'text',file);self.network.add_node(node);return node
    def bind_agent(self,actor,binding):
        """Explicit unit-test setup only; does not grant ports or repair a candidate network."""
        from copy import deepcopy
        from datanet.core.execution_binding import validate_execution_binding
        node=self.network.nodes[actor]
        if not isinstance(node,AgentNode):raise ValueError('只有实际 Agent 节点可配置测试执行绑定')
        if not isinstance(binding,dict) or binding.get('executor')!='harness':raise ValueError('显式提供 executor=harness 的测试执行绑定')
        previous=node.execution_binding;node.execution_binding=deepcopy(binding)
        try:validate_execution_binding(node,self.network,self.backend.components.module_types)
        except BaseException:node.execution_binding=previous;raise
        return deepcopy(node.execution_binding)
    def disconnect(self,source,target):
        node=self.network.nodes[source];node.interfaces[:]=[edge for edge in node.interfaces if edge.target_node_id!=target]
    def mount(self,node,module=None,config=None,state=None,access=None):
        return self.modules.mount(node,module or self.spec['id'],config=config,state=state,access=access or {'strength':2,'channels':['test']})
    async def call(self,node,operation,parameters=None,*,actor=None,module=None,strength=2,channels=('test',)):
        return await self.modules.access(actor or node,node,module or self.spec['id'],operation,parameters or {},strength=strength,channels=list(channels))
    async def close(self):await self.backend.signals.close();self.modules.clear()
    def register_tools(self,provider,definitions,execute):
        """测试宿主端口；execute 是测试回调，组件仍通过真实授权路由调用。"""
        if provider=='runtime' and any(item['name']=='agent_run' for item in definitions):raise ValueError('不要替换整个官方 Agent 运行端口；用 h.register_agent(callback) 仅替换模型正文')
        from .port_testing import checked_executor
        self.backend.external_tools.register(provider,definitions,checked_executor(provider,definitions,execute,self.backend.port_contracts))
    def register_agent(self,callback):
        """Local execution-boundary checks; full input preparation uses NetworkHarness."""
        from .agent_testing import register_agent
        register_agent(self.backend,callback)
    def register_readonly_ports(self):
        """Register the production read-only text service; offers/grants remain explicit."""
        import datanet
        from .service import PROJECT
        port_path=str(PROJECT/'extensions/foundation/capabilities/runtime_ports/python/datanet')
        if port_path not in datanet.__path__:datanet.__path__.append(port_path)
        from datanet.runtime_ports.services import TEXT_READ,read_text
        async def execute(actor,name,args):return read_text(self.folder,args)
        self.register_tools('runtime',[TEXT_READ],execute)
    def apply_context(self,actor,packet,source='prepare:test'):
        """Apply a preparation packet through the production executor's contract."""
        from .context_packets import apply_context_packet
        if not apply_context_packet(self.backend,actor,source,packet):raise ValueError('需要 nexarbor-context/v1 准备结果')
        return self.network.nodes[actor].inputs.snapshot()
    async def emit(self,actor,channels,*,strength=3,content=None,signal_id=None):
        from datanet.core.signals import Signal
        options=dict(content=content,node_timeout_seconds=5,timeout_seconds=10)
        if signal_id is not None:options['signal_id']=signal_id
        return await self.backend.signals.propagate(Signal(actor,channels,strength,**options))
