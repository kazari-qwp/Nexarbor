"""Generic native Agent port. All application behavior comes from node modules/config."""
import asyncio
from dataclasses import asdict,is_dataclass
from hashlib import sha256
from datanet.core.agent_node import AgentNode
from datanet.core.access_budget import active_agent
from datanet.core.tool_access import list_tools,invoke_tool,validate_arguments
from types import SimpleNamespace

class NativeExecutor:
    def __init__(self,backend,transport):
        self.backend,self.transport=backend,transport
        backend.execute_agent=self.run
        for method,mutation in [('prepare',True),('invoke',True),('ack',True),('bind',True)]:
            backend.components.rpc('executor_'+method,lambda b,p,method=method:getattr(self,method)(p),mutation=mutation)
    def binding(self,actor):
        node=self.backend.network.nodes[actor]
        if not isinstance(node,AgentNode):raise TypeError('Native execution requires an Agent node')
        binding=node.execution_binding or {}
        if binding.get('executor')!='harness':raise ValueError('Configure this node with executor=harness')
        strength=binding.get('strength',0)
        if type(strength) not in (int,float) or not 0<=strength<=32:raise ValueError('Invalid executor strength')
        return node,binding
    async def run(self,node_id,message='',**options):
        node,binding=self.binding(node_id)
        timeout=options.get('timeout_seconds',binding.get('timeout_seconds',90))
        if type(timeout) not in (int,float) or not 1<=timeout<=600:raise ValueError('Invalid executor timeout')
        request=dict(actor=node_id,name=node.name,message=message,timeout_seconds=timeout,max_steps=binding.get('max_steps',12),session_id=self.backend.agents.get(node_id,{}).get('session_id'))
        try:
            result=await asyncio.to_thread(self.transport.host,'agent-run',request)
            if result.get('status')!='completed':raise RuntimeError(result.get('error') or 'Agent did not complete')
            self.backend.agents.setdefault(node_id,{}).update(session_id=result['session_id'],executor='harness')
            return result
        except asyncio.CancelledError:
            await asyncio.to_thread(self.transport.host,'agent-cancel',dict(actor=node_id));raise
    def definitions(self,actor):
        node,binding=self.binding(actor);definitions=[];routes={}
        for name,spec in node.agent_tool_definitions.items():
            definitions.append(spec['function']);routes[name]=dict(private=True,tool=name)
        for target in self.backend.network.nodes.values():
            for spec in list_tools(self.backend.network,actor,target.node_id,strength=binding.get('strength',0)).items:
                alias='node_'+sha256((target.node_id+'\0'+spec['name']).encode()).hexdigest()[:20]
                definitions.append(dict(name=alias,description=target.name+' · '+spec['description'],parameters=spec['parameters']))
                routes[alias]=dict(private=False,target=target.node_id,tool=spec['name'])
        return definitions,routes
    def prepare(self,p):
        actor=p['actor'];node,binding=self.binding(actor)
        for reference in binding.get('prepare',[]):
            value=self.backend.modules.call(reference.get('node',actor),reference['module'],reference['operation'],reference.get('arguments',{}))
            if hasattr(value,'__await__'):raise ValueError('Preparation operations must be synchronous')
        sources=node.inputs.snapshot();definitions,_=self.definitions(actor)
        return dict(actor=actor,system_prompt='你有一份私有的记忆，根据你的需要主动维护和阅读，适时清除过时和无用记忆。\n\n'+'\n\n'.join(v['system_prompt'] for _,v in sorted(sources.items())),
            context=[dict(id=s+'/'+d['id'],text=d['text']) for s,v in sorted(sources.items()) for d in v['context']],
            inputs=[dict(source=s,**e) for s,e in node.inputs.pending()],tail=node.inputs.tail(),tools=definitions)
    def invoke(self,p):
        actor=p['actor'];node,binding=self.binding(actor);_,routes=self.definitions(actor)
        if p['name'] not in routes:raise PermissionError('Tool is no longer reachable from this Agent')
        route=routes[p['name']];arguments=p.get('arguments',{})
        identity=active_agent.set((SimpleNamespace(max_signal_strength=binding.get('strength',0)),actor))
        try:
            if route['private']:
                validate_arguments(arguments,node.agent_tool_definitions[route['tool']]['function']['parameters'])
                value=node.invoke_tool(route['tool'],**arguments)
            else:value=invoke_tool(self.backend.network,actor,route['target'],route['tool'],arguments,strength=binding.get('strength',0))
            return asdict(value) if is_dataclass(value) else value
        finally:active_agent.reset(identity)
    def ack(self,p):
        node,_=self.binding(p['actor'])
        for event in p.get('events',[]):node.inputs.acknowledge(event['source'],event['id'])
        return {'ok':True}
    def bind(self,p):
        self.binding(p['actor'])
        self.backend.agents.setdefault(p['actor'],{}).update(session_id=p['session_id'],executor='harness')
        return {'ok':True}
