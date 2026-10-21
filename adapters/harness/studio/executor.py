"""Generic native Agent port. All application behavior comes from node modules/config."""
import asyncio
import json
from dataclasses import asdict,is_dataclass
from hashlib import sha256
from datanet.core.agent_node import AgentNode
from datanet.core.access_budget import active_agent
from datanet.core.tool_access import list_tools,invoke_tool,validate_arguments
from types import SimpleNamespace

def discovery_key(backend, actor, binding, sources):
    """Cheap committed-structure key; never scan business histories for discovery.

    Dynamic providers default to uncached. A provider may explicitly declare
    state_schema.x-tool-discovery = network or state in its module manifest.
    This is an adapter hint, not an authorization grant.
    """
    from datanet.core.json_values import thaw
    with backend._transaction_lock:
        network=backend.network
        nodes,links,biases,modes=network.routing_snapshot(include_aggregation=True)
        locks=backend.node_locks
        _,images=locks.overrides()
        rows=[];cacheable=True
        for node_id,node in nodes.items():
            image=images.get(node_id);attrs=image['attrs'] if image else vars(node)
            modules=[]
            for name,spec in attrs.get('modules',{}).items():
                instance=backend.modules.instances.get((node_id,name))
                if instance is None:continue
                definition=instance.definition
                policy=definition.state_schema.get('x-tool-discovery')
                if definition.tool_provider and policy not in ('network','state'):cacheable=False
                modules.append((name,id(instance),id(definition),instance.active,definition.operations,definition.agent_tools,spec['access'],spec['config'],
                    spec['state'] if definition.tool_provider and policy=='state' else None))
            tools=image['tools'] if image else node.tools
            definitions=image['definitions'] if image else node.tool_definitions
            private=image['agent_definitions'] if image else node.agent_tool_definitions
            edges=[(e.target_node_id,e.metadata.threshold,e.metadata.multiplier,e.metadata.channels,e.metadata.attributes) for e in links[node_id]]
            rows.append((node_id,id(node),attrs.get('name'),attrs.get('description'),biases[node_id],modes[node_id],
                locks.ownership(node_id),(attrs.get('module_strength') if image else node.module_strength),edges,modules,definitions,private,
                [(name,id(callback)) for name,callback in tools.items()],attrs.get('expose',[]),attrs.get('offered_tools',[])))
        if not cacheable:return None
        external=backend.external_tools
        value=(binding,sorted(sources),rows,sorted(backend.components.enabled),external.catalog(),
            backend.agents.get(actor,{}).get('external_tools',{}))
        return sha256(json.dumps(thaw(value),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class NativeExecutor:
    def __init__(self,backend,transport):
        self.backend,self.transport=backend,transport
        self.seen={}
        self.tool_views={}
        from datanet.core.module_tools import ModuleTools
        self.module_tools=ModuleTools(backend)
        if transport is not None:
            class ContextPort:
                async def capture(self,bindings):
                    return await asyncio.to_thread(transport.host,'agent-context-capture',dict(bindings=bindings))
                async def restore(self,cursors):
                    return await asyncio.to_thread(transport.host,'agent-context-restore',dict(contexts=cursors,transactional=True))
            backend.context_port=ContextPort()
        backend.agent_executor=self.run
        for method,mutation in [('prepare',True),('invoke',True),('ack',True),('bind',True),('prune',True),('visit',True)]:
            backend.components.rpc('executor_'+method,lambda b,p,method=method:getattr(self,method)(p),mutation=mutation)
    def binding(self,actor):
        node=self.backend.network.nodes[actor]
        from datanet.core.execution_binding import validate_execution_binding
        validate_execution_binding(node,self.backend.network,getattr(self.backend.components,'module_types',{}))
        if not isinstance(node,AgentNode):raise TypeError('Native execution requires an Agent node')
        binding=dict(node.execution_binding or {})
        from datanet.core.channel_filters import resolve
        policy=binding.get('channel_mode',binding.get('channel_modes',{}).get('channels','allow'))
        binding['channels']=list(resolve(binding.get('channels',[]),policy,self.backend.network.channel_names() if policy=='deny' else ()))
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
        await self.refresh_tools(node_id,binding,include_self=True)
        timeout=options.get('timeout_seconds',binding.get('timeout_seconds',90))
        if type(timeout) not in (int,float) or not 1<=timeout<=86400:raise ValueError('Invalid executor timeout')
        request=dict(actor=node_id,name=node.name,message=message,timeout_seconds=timeout,max_steps=binding.get('max_steps',12),session_id=self.backend.agents.get(node_id,{}).get('session_id'),context_cursor=node.context_cursor,model=binding.get('model'),model_signature=self.backend.agents.get(node_id,{}).get('model_signature'))
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
    async def refresh_tools(self,actor,binding,*,include_self=False):
        memory=self.backend.agents.get(actor,{})
        sources=list(dict.fromkeys([*([actor] if include_self else []),*binding.get('tool_sources',[]),
            *(source['node_id'] for source in memory.get('module_tool_sources',{}).values())]))
        before=discovery_key(self.backend,actor,binding,sources)
        cached=self.tool_views.get(actor)
        if before is not None and cached and cached['key']==before:return cached['view']
        # A deleted provider cannot leave a retained executable tool behind.
        for source_id,source in list(memory.get('module_tool_sources',{}).items()):
            if source['node_id'] not in self.backend.network.nodes:
                memory['module_tool_sources'].pop(source_id)
                memory['module_tools']={alias:item for alias,item in memory.get('module_tools',{}).items() if item['source_id']!=source_id}
        await asyncio.gather(*(self.module_tools.visit(actor,target,
            strength=binding.get('strength',0),channels=binding.get('channels',[]))
            for target in sources if target in self.backend.network.nodes))
        # Provider tables use synchronous admission; let them wait off the
        # core event loop while a short peer transaction owns a provider.
        view=await asyncio.to_thread(self.definitions,actor)
        after=discovery_key(self.backend,actor,binding,sources)
        self.tool_views[actor]=dict(key=after if before==after else None,view=view)
        return view

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
        definitions,_=self.backend.runtime.run(self.refresh_tools(actor,binding))
        for reference in binding.get('prepare',[]):
            target=reference.get('node',actor)
            channels=reference.get('channels',binding.get('channels',[]))
            value=self.backend.runtime.run(self.backend.modules.local_access(actor,target,reference['module'],reference['operation'],reference.get('arguments',{})) if self.backend.network.same_family(actor,target) else self.backend.modules.access(actor,target,reference['module'],reference['operation'],reference.get('arguments',{}),strength=binding.get('strength',0),channels=channels))
            if value.get('status')!='ok':raise RuntimeError(value.get('error') or '上下文准备失败')
            packet=value.get('data') or {}
            if isinstance(packet,dict) and packet.get('format')=='nexarbor-context/v1':
                source='prepare:'+target+':'+reference['module']+':'+reference['operation']
                from datanet.studio.context_packets import apply_context_packet
                apply_context_packet(self.backend,actor,source,packet)
        # 接线撤销后移除快照，但保留已经投递/排队的事件历史。
        active={'prepare:'+r.get('node',actor)+':'+r['module']+':'+r['operation'] for r in binding.get('prepare',[])}
        for source in node.inputs.snapshot():
            if source.startswith('prepare:') and source not in active:node.inputs.update(source,dict(system_prompt='',context=[],tail=[]))
        sources=node.inputs.snapshot()
        return dict(actor=actor,system_prompt='\n\n'.join(v['system_prompt'] for _,v in sorted(sources.items())),
            skills=node.skills,context=[dict(id=s+'/'+d['id'],text=d['text']) for s,v in sorted(sources.items()) for d in v['context']],
            inputs=[dict(source=s,**e) for s,e in node.inputs.pending()],tail=node.inputs.tail(),tools=definitions,retained_tools=[v['definition'] for v in self.backend.agents[actor]['tool_history'].values()],
            unavailable={name:self.refusal(actor,name) for name in self.seen.get(actor,{}) if name not in {d['name'] for d in definitions}})
    def invoke(self,p):
        with self.backend.node_locks.access_sync([p['actor']]):
            return self._invoke_owned(p)

    def _invoke_owned(self,p):
        self._check_session(p)
        actor=p['actor'];node,binding=self.binding(actor)
        cached=self.tool_views.get(actor)
        definitions,routes=cached['view'] if cached else self.definitions(actor)
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
        self.tool_views.pop(p['actor'],None)
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
            self.backend.agents.setdefault(p['actor'],{}).update(session_id=p['session_id'],executor='harness',model_signature=p.get('model_signature'))
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
        self.tool_views.pop(actor,None)
        return list(history)
