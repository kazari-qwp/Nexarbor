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
        self.seen={}
        from datanet.core.module_tools import ModuleTools
        self.module_tools=ModuleTools(backend)
        if transport is not None:
            class ContextPort:
                async def capture(self,bindings):
                    return await asyncio.to_thread(transport.host,'agent-context-capture',dict(bindings=bindings))
                async def restore(self,cursors):
                    return await asyncio.to_thread(transport.host,'agent-context-restore',dict(contexts=cursors))
            backend.context_port=ContextPort()
        backend.agent_executor=self.run
        for method,mutation in [('prepare',True),('invoke',True),('ack',True),('bind',True),('prune',True),('visit',True)]:
            backend.components.rpc('executor_'+method,lambda b,p,method=method:getattr(self,method)(p),mutation=mutation)
    def binding(self,actor):
        node=self.backend.network.nodes[actor]
        from datanet.studio.network_work import validate_execution
        validate_execution(node,self.backend)
        if not isinstance(node,AgentNode):raise TypeError('Native execution requires an Agent node')
        binding=node.execution_binding or {}
        if binding.get('executor')!='harness':raise ValueError('Configure this node with executor=harness')
        strength=binding.get('strength',0)
        if type(strength) not in (int,float) or not 0<=strength<=32:raise ValueError('Invalid executor strength')
        from datanet.core.json_values import names
        names(binding.get('channels',[]),'executor channels')
        return node,binding
    def _check_session(self,p):
        expected=p.get('executor_session_id')
        if expected is not None and self.backend.agents.get(p['actor'],{}).get('session_id')!=expected:
            raise PermissionError('Executor session was replaced; discard this stale callback')
    async def run(self,node_id,message='',**options):
        async with self.backend.node_locks.access([node_id]):
            return await self._run_owned(node_id,message,**options)

    async def _run_owned(self,node_id,message='',**options):
        node,binding=self.binding(node_id)
        # 首轮也装配本节点公开的工具来源；之后每次模型请求按当前网络刷新。
        await self.module_tools.visit(node_id,node_id,strength=binding.get('strength',0),channels=binding.get('channels',[]))
        timeout=options.get('timeout_seconds',binding.get('timeout_seconds',90))
        if type(timeout) not in (int,float) or not 1<=timeout<=600:raise ValueError('Invalid executor timeout')
        request=dict(actor=node_id,name=node.name,message=message,timeout_seconds=timeout,max_steps=binding.get('max_steps',12),session_id=self.backend.agents.get(node_id,{}).get('session_id'),context_cursor=node.context_cursor)
        try:
            async with self.backend.node_locks.suspend_access():
                with self.backend.node_locks.export_owner(node_id) as ticket:
                    result=await asyncio.to_thread(self.transport.host,'agent-run',dict(request,node_access_ticket=ticket))
            if self.backend.network.nodes.get(node_id) is not node:raise RuntimeError('Agent node was replaced during execution')
            if result.get('status')!='completed':raise RuntimeError(result.get('error') or 'Agent did not complete')
            self.backend.agents.setdefault(node_id,{}).update(session_id=result['session_id'],executor='harness')
            return result
        except asyncio.CancelledError:
            await asyncio.to_thread(self.transport.host,'agent-cancel',dict(actor=node_id));raise
    def definitions(self,actor):
        node,binding=self.binding(actor);definitions=[];routes={}
        history=self.backend.agents.setdefault(actor,{}).setdefault('tool_history',{})
        self.seen.setdefault(actor,{}).update({name:value['route'] for name,value in history.items()})
        for name,spec in node.agent_tool_definitions.items():
            definitions.append(spec['function']);routes[name]=dict(private=True,tool=name)
        definitions.append(dict(name='network_visit',description='沿自身授权频道访问网络。省略 target 查看可达节点；填写节点编号取得其信息和提供的外部工具。',
            parameters={'type':'object','properties':{'target':{'type':'string'}},'additionalProperties':False}))
        routes['network_visit']=dict(private=True,visit=True)
        for item in self.backend.external_tools.acquired(actor,strength=binding.get('strength',0),channels=binding.get('channels',[])):
            definitions.append(item['definition']);routes[item['alias']]=dict(private=False,external=True,**{k:item[k] for k in ('target','ref','channels','strength')})
        for item in self.module_tools.acquired(actor,strength=binding.get('strength',0),channels=binding.get('channels',[])):
            definitions.append(item['definition']);routes[item['alias']]=dict(private=False,module_tool=True,entry=item)
        self.seen.setdefault(actor,{}).update(routes)
        for definition in definitions:history[definition['name']]=dict(definition=definition,route=routes[definition['name']])
        return definitions,routes
    def refusal(self,actor,name):
        route=self.seen.get(actor,{}).get(name)
        reason='这个工具已离开你当前可达的范围，不能执行。'
        if route and not route['private'] and not route.get('external') and not route.get('module_tool'):
            target=self.backend.network.nodes.get(route['target'])
            callback=target.tool_refusals.get(route['tool']) if target else None
            if callback:return str(callback(actor,reason))
        return reason
    def prepare(self,p):
        with self.backend.node_locks.access_sync([p['actor']]):
            return self._prepare_owned(p)

    def _prepare_owned(self,p):
        self._check_session(p)
        actor=p['actor'];node,binding=self.binding(actor)
        if self.backend.agents.get(actor,{}).get('module_tool_sources'):
            self.backend.runtime.run(self.module_tools.refresh(actor,strength=binding.get('strength',0),channels=binding.get('channels',[])))
        for reference in binding.get('prepare',[]):
            value=self.backend.modules.call(reference.get('node',actor),reference['module'],reference['operation'],reference.get('arguments',{}))
            if hasattr(value,'__await__'):self.backend.runtime.run(value)
        sources=node.inputs.snapshot();definitions,_=self.definitions(actor)
        return dict(actor=actor,system_prompt='你有一份私有的记忆，根据你的需要主动维护和阅读，适时清除过时和无用记忆。\n\n'+'\n\n'.join(v['system_prompt'] for _,v in sorted(sources.items())),
            context=[dict(id=s+'/'+d['id'],text=d['text']) for s,v in sorted(sources.items()) for d in v['context']],
            inputs=[dict(source=s,**e) for s,e in node.inputs.pending()],tail=node.inputs.tail(),tools=definitions,retained_tools=[v['definition'] for v in self.backend.agents[actor]['tool_history'].values()],
            unavailable={name:self.refusal(actor,name) for name in self.seen.get(actor,{}) if name not in {d['name'] for d in definitions}})
    def invoke(self,p):
        with self.backend.node_locks.access_sync([p['actor']]):
            return self._invoke_owned(p)

    def _invoke_owned(self,p):
        self._check_session(p)
        actor=p['actor'];node,binding=self.binding(actor);definitions,routes=self.definitions(actor)
        if p['name'] not in routes:return dict(status='forbidden',errors=[self.refusal(actor,p['name'])])
        route=routes[p['name']];arguments=p.get('arguments',{})
        validate_arguments(arguments,next(d['parameters'] for d in definitions if d['name']==p['name']))
        identity=active_agent.set((SimpleNamespace(max_signal_strength=binding.get('strength',0)),actor))
        try:
            if route.get('visit'):return self.visit(dict(actor=actor,**arguments))
            if route.get('module_tool'):
                return self.backend.runtime.run(self.module_tools.invoke(actor,route['entry'],arguments,
                    strength=binding.get('strength',0),channels=binding.get('channels',[])))
            if route.get('external'):
                return self.backend.runtime.run(self.backend.external_tools.invoke(actor,route['target'],route['ref'],arguments,
                    strength=min(binding.get('strength',0),route['strength']),
                    channels=[c for c in route['channels'] if c in binding.get('channels',[])]))
            if route['private']:
                validate_arguments(arguments,node.agent_tool_definitions[route['tool']]['function']['parameters'])
                value=node.invoke_tool(route['tool'],**arguments)
            else:value=invoke_tool(self.backend.network,actor,route['target'],route['tool'],arguments,strength=binding.get('strength',0))
            return asdict(value) if is_dataclass(value) else value
        finally:active_agent.reset(identity)
    def visit(self,p):
        with self.backend.node_locks.access_sync([p['actor']]):
            return self._visit_owned(p)

    def _visit_owned(self,p):
        self._check_session(p)
        actor=p['actor'];node,binding=self.binding(actor)
        strength=binding.get('strength',0);channels=binding.get('channels',[])
        target=p.get('target')
        if target is None:
            while True:
                targets=[n.node_id for n,_,_ in self.backend.network.walk_states(actor,strength=strength,channels=channels)]
                with self.backend.node_locks.access_sync(targets,mutable=False):
                    with self.backend._transaction_lock:
                        reached=list(self.backend.network.walk_states(actor,strength=strength,channels=channels))
                        if {n.node_id for n,_,_ in reached}!=set(targets):continue
                        return dict(nodes=[n.get_metadata() for n,_,_ in reached])
        with self.backend.node_locks.access_sync([target],mutable=False):
            tools=self.backend.external_tools.visit(actor,target,strength=strength,channels=channels)
            tools.extend(self.backend.runtime.run(self.module_tools.visit(actor,target,strength=strength,channels=channels)))
            return dict(metadata=self.backend.network.nodes[target].get_metadata(),tools=tools)
    def ack(self,p):
        with self.backend.node_locks.access_sync([p['actor']]):
            return self._ack_owned(p)

    def _ack_owned(self,p):
        self._check_session(p)
        node,_=self.binding(p['actor'])
        for event in p.get('events',[]):node.inputs.acknowledge(event['source'],event['id'])
        return {'ok':True}
    def bind(self,p):
        with self.backend.node_locks.access_sync([p['actor']]):
            self.binding(p['actor'])
            self.backend.agents.setdefault(p['actor'],{}).update(session_id=p['session_id'],executor='harness')
            if p.get('context_cursor') is not None: self.backend.network.nodes[p['actor']].context_cursor=p['context_cursor']
            return {'ok':True}
    def prune(self,p):
        with self.backend.node_locks.access_sync([p['actor']]):
            return self._prune_owned(p)

    def _prune_owned(self,p):
        self._check_session(p)
        actor=p['actor'];definitions,_=self.definitions(actor)
        retained=set(p.get('referenced',[]))|{d['name'] for d in definitions}
        history=self.backend.agents[actor]['tool_history']
        for name in list(history):
            if name not in retained:history.pop(name);self.seen.get(actor,{}).pop(name,None)
        return list(history)
