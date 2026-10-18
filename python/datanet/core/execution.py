"""Host-independent execution contract and optional configuration codec."""
from dataclasses import dataclass,field
from typing import Protocol,Callable,Any
from copy import deepcopy
from functools import partial

@dataclass
class ExecutionRequest:
    session_id:str
    node_id:str
    message:str
    prompt:str=''
    tools:list=field(default_factory=list)
    max_steps:int=8
    timeout_seconds:float=60
    input_state:dict=field(default_factory=dict)

@dataclass
class ExecutionResult:
    status:str
    output:str=''
    steps:int=0
    error:str|None=None

class Executor(Protocol):
    def run(self,request:ExecutionRequest,tools:dict[str,Callable])->ExecutionResult:...
    def cancel(self,session_id:str)->bool:...
    def status(self,session_id:str)->str:...
    def send(self,session_id:str,message:str)->None:...

_encoder=_decoder=_package_loader=None
def register_execution_codec(encoder,decoder,package_loader):
    global _encoder,_decoder,_package_loader
    _encoder,_decoder,_package_loader=encoder,decoder,package_loader
def encode_execution(node,base):
    return _encoder(node,base) if _encoder else deepcopy(node.agent_config)
def decode_execution(value,base):
    return _decoder(value,base) if _decoder else deepcopy(value)
def load_execution_package(path):
    if _package_loader is None:
        from .component_registry import ensure_nodes
        ensure_nodes()
    if _package_loader is None:raise RuntimeError('No execution package provider installed')
    return _package_loader(path)


class ExecutorRegistry:
    def __init__(self,network):self.network=network;self.executors={};self.bindings={}
    def register(self,name,executor):
        if name in self.executors:raise ValueError('Executor already registered')
        self.executors[name]=executor
    def bind(self,node_id,executor,session_id,tool_names=(),max_signal_strength=0):
        from .agent_node import AgentNode
        from .interface import validate_strength
        node=self.network.nodes[node_id]
        if not isinstance(node,AgentNode):raise TypeError('An executor requires an Agent node')
        if executor not in self.executors:raise KeyError(executor)
        definitions={**node.tool_definitions,**node.agent_tool_definitions}
        if any(name not in definitions for name in tool_names):raise ValueError('Tool is not registered on this node')
        if not isinstance(session_id,str) or not session_id:raise ValueError('Session ID must be nonempty text')
        if any(other!=node_id and value['session_id']==session_id and value['executor']==executor for other,value in self.bindings.items()):raise ValueError('Session is already bound to another node')
        self.bindings[node_id]={'executor':executor,'session_id':session_id,'tools':list(tool_names),'strength':validate_strength(max_signal_strength)}
        node.execution_binding=deepcopy(self.bindings[node_id])
    def run(self,node_id,message,**options):
        from contextlib import nullcontext
        locks=getattr(self.network,'node_locks',None)
        with locks.access_sync([node_id]) if locks else nullcontext():
            return self._run_owned(node_id,message,**options)

    def _run_owned(self,node_id,message,**options):
        from types import SimpleNamespace
        from .access_budget import active_agent
        node=self.network.nodes[node_id];binding=self.bindings[node_id]
        definitions={**node.tool_definitions,**node.agent_tool_definitions}
        tools=[]
        for name in binding['tools']:
            spec=definitions[name];spec=spec.get('function',spec)
            tools.append({'type':'function','function':{k:deepcopy(spec[k]) for k in ['name','description','parameters']}})
        request=ExecutionRequest(binding['session_id'],node_id,message,tools=tools,input_state=node.inputs.snapshot(),**options)
        def invoke(tool_name,/,**arguments):
            token=active_agent.set((SimpleNamespace(max_signal_strength=binding['strength']),node_id))
            try:return node.invoke_tool(tool_name,**arguments)
            finally:active_agent.reset(token)
        result=self.executors[binding['executor']].run(request,{name:partial(invoke,name) for name in binding['tools']})
        if result.status=='completed':
            for source,event in node.inputs.pending():
                if any(e['id']==event['id'] for e in request.input_state.get(source,{}).get('inputs',[])):node.inputs.acknowledge(source,event['id'])
        return result
    def bind_signals(self,runtime,node_id,*,max_steps=8):
        """Register normal executor completion as signal completion; no model ready tool."""
        import asyncio
        import json
        from dataclasses import asdict
        from .json_values import thaw
        if runtime.network is not self.network or node_id not in self.bindings:raise ValueError('Signal executor binding is absent')
        if not hasattr(self,'_signal_workers'):self._signal_workers={}
        async def handle(context):
            previous=self._signal_workers.get(node_id)
            if previous and not previous.done():raise RuntimeError('Previous executor work has not stopped')
            content=thaw(context.signal.content)
            message=content if isinstance(content,str) else json.dumps(content,ensure_ascii=False)
            binding=self.bindings[node_id]
            worker=asyncio.create_task(asyncio.to_thread(self.run,node_id,message,max_steps=max_steps,timeout_seconds=context.signal.node_timeout_seconds))
            self._signal_workers[node_id]=worker
            def finished(task):
                if self._signal_workers.get(node_id) is task:self._signal_workers.pop(node_id,None)
                if not task.cancelled():task.exception()
            worker.add_done_callback(finished)
            try:
                result=await asyncio.shield(worker)
            except asyncio.CancelledError:
                self.executors[binding['executor']].cancel(binding['session_id'])
                raise
            if result.status!='completed':raise RuntimeError(result.error or 'Agent signal processing failed: '+result.status)
            return asdict(result)
        runtime.bind(node_id,handle,access_strength=lambda:self.bindings[node_id]['strength'])

    def restore_bindings(self):
        for node in self.network.nodes.values():
            binding=getattr(node,'execution_binding',None)
            if binding:self.bind(node.node_id,binding['executor'],binding['session_id'],binding['tools'],binding['strength'])
