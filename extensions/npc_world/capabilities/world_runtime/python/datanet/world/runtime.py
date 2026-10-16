"""World policy over core pulses, resident text, and the existing Agent executor."""
import asyncio
import json
from threading import Lock,Thread
from datanet.core.application import Component
from datanet.world.state import state,clock,home_of
from datanet.world import profiles
from datanet.core.json_values import freeze

class Plugin(Component):
    def install(self):
        self.turns={};self.phase_lock=Lock();self.loop=None;self.thread=None;self.inflight={}
        self.on('session/root',self.root)
        self.on('tool/before',self.guide)
        self.on('agent/pre-step',self.pre_step)
        self.on('agent/request',self.request)
        self.on('node/metadata-changed',self.metadata_changed)

    def root(self,e):
        if self.r.config.get('rootNetwork')!='small_town':return
        owner='network_presets/small_town'
        self.r.rpc('world_init',actor='root',config=self.r.resource(owner,'town.json',True),common=self.r.resource(owner,'COMMON.md'))
        catalog=self.r.resource('nodes/resident_knowledge','profiles.json',True)
        self.r.rpc('world_configure_knowledge',actor='root',profiles=[dict(p,content=self.r.resource('nodes/resident_knowledge',p['file'])) for p in catalog])
        self.r.rpc('bind_agent',target='root',session_id=e['session_id'],kind='root',manager_id=None,creator_node_id=None)
        e['view']=self.r.bind('root',e['session_id'],'world_operator',self.r.resolve(['world_operator']),self.r.resource(owner,'prompt.md'))
        self.mount()

    def mount(self):
        assembler=self.r.plugins['capabilities/context_assembly']
        for actor,a in list(state(self.r.backend)['actors'].items()):
            node_id=profiles.context_id(actor)
            sources=[dict(id='clock',kind='tail',source=dict(type='node',target='world/time'))]
            owner='nodes/npc_child' if a['role']=='child' else 'nodes/npc_resident'
            file='personality.md' if a['role']=='child' else 'personalities/'+actor.rsplit('/',1)[-1]+'.md'
            sources.append(dict(id='personality',kind='system_prompt',source=dict(type='resource',component=owner,file=file)))
            if a['role']=='child':
                home=home_of(state(self.r.backend),actor)
                residence='你住在'+next(x['name'] for x in state(self.r.backend)['config']['places'] if x['id']==home)+'。' if home else '你目前没有登记住处。'
                sources.append(dict(id='residence',kind='system_prompt',source=dict(type='text',text=residence)))
            for spec in state(self.r.backend).get('knowledge_catalog',[]):
                sources.append(dict(id=spec['node_id'],name=spec['name'],kind='context',when=spec['when'],reference_only=spec['delivery']=='query',source=dict(type='node',target=spec['node_id'])))
            assembler.configure(node_id,sources)
            assembler.bind(actor,node_id)
            if actor in self.r.states:continue
            owner='nodes/npc_child' if a['role']=='child' else 'nodes/npc_resident'
            prompt=self.r.resource(owner,'prompt.md')
            old=self.r.backend.agents.get(actor)
            self.r.plugins['capabilities/agent_runtime'].create(actor,prompt,'root',2,['world_resident'],'npc_child' if a['role']=='child' else 'npc_resident',binding=old,resume=old is not None)
            self.r.rpc('agent_progress',target=actor,kind='world_npc')

    def metadata_changed(self,e):
        if e['namespace']=='npc' and e['node_id'] in (state(self.r.backend) or {}).get('actors',{}):self.r.rpc('world_refresh_knowledge',actor='root')

    def guide(self,e):
        if e['actor']=='root' and e['name'].startswith('world_'):
            self.r.load('root','world:operator',self.r.resource('network_presets/small_town','AGENTS.md'))
        elif e['actor'] in (state(self.r.backend) or {}).get('actors',{}):self.resident_guide(e['actor'])

    def resident_guide(self,actor):
        self.r.load(actor,'world:resident',self.r.resource('nodes/npc_resident','AGENTS.md'))

    def pre_step(self,e):
        if e['actor'] not in (state(self.r.backend) or {}).get('actors',{}):return
        self.resident_guide(e['actor']);self.update_status(e['actor']);turn=self.turns.get(e['actor'])
        if turn and turn['active'] and turn['count']>=turn['limit']:raise RuntimeError('World NPC request budget exhausted')

    def request(self,e):
        actor=e['actor'];turn=self.turns.get(actor)
        if turn and turn['active']:
            if turn['count']>=turn['limit']:raise RuntimeError('World NPC request budget exhausted')
            turn['count']+=1
            self.r.rpc('agent_progress',target=actor,world_signal_id=turn['signal_id'],world_requests=turn['count'])

    def update_status(self,actor):
        w=state(self.r.backend)
        if not w or actor not in w['actors']:return
        a=w['actors'][actor];text='[小镇] 地点：'+a['place']+'。'
        if any(not m.get('read') for m in a['inbox']):text+='有未读交谈。'
        if any(v['carrier']==actor and not v.get('child') and v['due_tick']-w['tick']<=5 for v in w['pregnancies'].values()):text+='临近或已到预产时刻，请查看 world_look。'
        turn=self.turns.get(actor)
        if turn and turn['active']:text+=f"本次请求已用{turn['count']}/{turn['limit']}，处理完后自然结束。"
        self.r.update_inputs(actor,'npc:status',tail=[text])

    def tool_world_look(self,actor,p):return self.r.rpc('world_look',actor=actor)
    def tool_world_messages(self,actor,p):return self.r.rpc('world_messages',actor=actor)
    def tool_world_observe(self,actor,p):
        w=self.r.rpc('world_observe',actor=actor)
        if p.get('target'):
            if p['target'] not in w['actors']:raise ValueError('Unknown resident')
            return dict(clock=clock(w['tick']),resident=w['actors'][p['target']],binding=self.r.backend.agents.get(p['target']),result=w['results'].get(p['target']))
        pulse=self.r.backend.network.nodes['world/pulse']
        return dict(clock=clock(w['tick']),time_text=self.r.backend.network.nodes['world/time']._read_key('content').items[0]['content'],pulse=pulse.state,
                    places=w['config']['places'],roads=w['config']['roads'],
                    residents=[dict(id=k,name=a['name'],place=a['place'],role=a['role'],session_id=self.r.backend.agents.get(k,{}).get('session_id')) for k,a in w['actors'].items()],
                    active=w['round'].get('active',False),events=w['events'][-20:],results=w['results'])

    def start_loop(self):
        if self.loop:return
        self.loop=asyncio.new_event_loop();self.thread=Thread(target=self.loop.run_forever,name='npc-signals',daemon=True);self.thread.start()

    def execute_npc(self,target,signal,execution_id,timeout_ms,task):
        previous=getattr(self.r.local,'execution_id',None);self.r.local.execution_id=execution_id
        limit=min(10,max(1,int(self.r.config.get('worldMaxRequests',8))))
        self.turns[target]=dict(active=True,signal_id=signal.signal_id,count=0,limit=limit)
        try:
            self.resident_guide(target)
            observation=self.r.rpc('world_look',actor=target)
            text=task+'\n'+json.dumps(observation,ensure_ascii=False)
            result=self.r.plugins['capabilities/agent_runtime'].execute('root',target,text,kind='world_npc',timeout_ms=timeout_ms)
            if result['status']!='ok':raise RuntimeError('Resident execution did not complete normally')
            return dict(session_id=result['session_id'],requests=self.turns[target]['count'])
        finally:
            self.turns[target]['active']=False;self.r.local.execution_id=previous

    async def pulse_cycle(self,targets,timeout_seconds,execution_id):
        self.r.local.execution_id=execution_id
        self.r.rpc('world_prepare_pulse',actor='root',targets=targets)
        runtime=self.r.backend.signals;pulse=self.r.backend.network.nodes['world/pulse']
        response=self.r.plugins['capabilities/signal_response']
        config=self.r.resource('network_presets/small_town','responses.json',True)
        def with_execution(function,*args,**kwargs):
            previous=getattr(self.r.local,'execution_id',None);self.r.local.execution_id=execution_id
            try:return function(*args,**kwargs)
            finally:self.r.local.execution_id=previous
        def update_time(context,signal_id):
            return with_execution(self.r.rpc,'world_open_pulse',actor='root',signal_id=signal_id)
        def assemble_context(context):
            return with_execution(self.r.plugins['capabilities/context_assembly'].assemble,context.delivery.node_id)
        async def run_actor(context,task,timeout_ms):
            target=context.delivery.node_id;signal=context.signal
            previous=self.inflight.get(target)
            if previous and not previous.done():raise RuntimeError('Previous NPC execution is still stopping')
            worker=asyncio.create_task(asyncio.to_thread(self.execute_npc,target,signal,execution_id,timeout_ms,task))
            self.inflight[target]=worker
            def finished(job):
                if self.inflight.get(target) is job:self.inflight.pop(target,None)
                if not job.cancelled():job.exception()
            worker.add_done_callback(finished)
            result=await asyncio.shield(worker)
            outcome=self.r.rpc('world_complete_pulse_actor',actor='root',target=target,signal_id=signal.signal_id,status='completed')
            return dict(**result,outcome=outcome)
        async def failed(context,error):
            target=context.delivery.node_id
            try:await asyncio.to_thread(with_execution,self.r.host,'cancel-agent',actor=target)
            except Exception:pass
            self.r.rpc('world_complete_pulse_actor',actor='root',target=target,signal_id=context.signal.signal_id,status='unavailable',reason=str(error) or type(error).__name__)
        response.bind('world/time',config['clock'],{'world_update_time':update_time})
        for target in targets:
            response.bind(target,config['npc'],{'assemble_context':assemble_context,'world_run_actor':run_actor},access_strength=2,on_error=failed)
        pulse.content=freeze(dict(task=self.r.config.get('worldPulseTask','本时刻按自己的想法活动，处理完后正常结束。'),timeout_ms=min(90000,int(timeout_seconds*1000))))
        settlement=None
        async def settle(source,report):
            nonlocal settlement
            settlement=self.r.rpc('world_settle',actor='root')
        try:
            result=await pulse.run(runtime,cycles=1,timeout_seconds=timeout_seconds,cycle_complete=settle,allow_partial=True)
            # A failed branch has no return edge; settle explicitly if every NPC failed.
            if state(self.r.backend)['round'].get('active'):
                round=state(self.r.backend)['round']
                for target in round['participants']:
                    if target not in round['outcomes']:
                        self.r.rpc('world_complete_pulse_actor',actor='root',target=target,signal_id=round['signal_id'],status='unavailable',reason='Pulse ended without a normal completion')
                settlement=self.r.rpc('world_settle',actor='root')
            return dict(pulse=result,settlement=settlement)
        finally:self.r.local.execution_id=None

    def run_pulse(self,actor,targets,timeout_seconds):
        if actor!='root':raise PermissionError('Only operator may run the world pulse')
        if not self.phase_lock.acquire(blocking=False):raise RuntimeError('Another world pulse is active')
        try:
            self.mount();self.start_loop()
            future=asyncio.run_coroutine_threadsafe(self.pulse_cycle(targets,timeout_seconds,getattr(self.r.local,'execution_id',None)),self.loop)
            try:result=future.result(timeout=timeout_seconds+15)
            except BaseException:future.cancel();raise
            self.mount()
            return result
        finally:self.phase_lock.release()

    def tool_world_run_npc(self,actor,p):
        return self.run_pulse(actor,[p['target']],min(120,max(1,p.get('timeout_ms',90000)/1000)))

    def tool_world_round(self,actor,p):
        if not self.r.config.get('worldAllowFullRun',True):raise PermissionError('This runtime permits only single-NPC tests')
        return self.run_pulse(actor,list(state(self.r.backend)['actors']),min(180,max(1,p.get('timeout_seconds',180))))

    def close(self):
        if not self.loop:return
        future=asyncio.run_coroutine_threadsafe(self.r.backend.signals.close(),self.loop)
        try:future.result(timeout=5)
        finally:self.loop.call_soon_threadsafe(self.loop.stop);self.thread.join(timeout=5);self.loop.close();self.loop=None
