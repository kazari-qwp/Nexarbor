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
            components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
        self.backend.modules=NodeModules(self.backend,definitions);self.backend.signals=self.backend.network.signals;self.backend.dispatch=lambda *a:None;self.backend.external_tools=ExternalTools(self.backend)
        self.network=self.backend.network;self.modules=self.backend.modules;self.tools=ModuleTools(self.backend)
    def add_node(self,id,name=None,*,agent=False,description=''):
        node=AgentNode(id,name or id,file_path=self.folder/(id.replace('/','_')+'.md')) if agent else Node(id,name or id,None,description=description)
        self.network.add_node(node);return node
    def connect(self,source,target,channels=('test',),**kw):return self.network.nodes[source].connect(target,channels=list(channels),**kw)
    def add_text(self,id,text='',name=None):
        file=self.folder/'test-data'/(id.replace('/','_')+'.txt');file.parent.mkdir(exist_ok=True);file.write_text(text,encoding='utf-8')
        node=TextFileNode(id,name or id,'text',file);self.network.add_node(node);return node
    def disconnect(self,source,target):
        node=self.network.nodes[source];node.interfaces[:]=[edge for edge in node.interfaces if edge.target_node_id!=target]
    def mount(self,node,module=None,config=None,state=None,access=None):
        return self.modules.mount(node,module or self.spec['id'],config=config,state=state,access=access or {'strength':2,'channels':['test']})
    async def call(self,node,operation,parameters=None,*,actor=None,module=None,strength=2,channels=('test',)):
        return await self.modules.access(actor or node,node,module or self.spec['id'],operation,parameters or {},strength=strength,channels=list(channels))
    async def close(self):await self.backend.signals.close();self.modules.clear()
    def register_tools(self,provider,definitions,execute):
        """测试宿主端口；execute 是测试回调，组件仍通过真实授权路由调用。"""
        self.backend.external_tools.register(provider,definitions,execute)
    async def emit(self,actor,channels,*,strength=3,content=None):
        from datanet.core.signals import Signal
        return await self.backend.signals.propagate(Signal(actor,channels,strength,content=content,node_timeout_seconds=5,timeout_seconds=10))
