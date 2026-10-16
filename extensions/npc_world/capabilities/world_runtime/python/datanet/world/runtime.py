"""World policy over core pulses, resident text, and the existing Agent executor."""
import asyncio
import json
from threading import Lock,Thread
from datanet.core.application import Component
from datanet.world.state import state,clock
from datanet.world import profiles

class Plugin(Component):
    def install(self):
        self.turns={};self.phase_lock=Lock();self.loop=None;self.thread=None;self.inflight={}
        self.on('session/root',self.root)
        self.on('tool/before',self.guide)
        self.on('agent/pre-step',self.pre_step)
        self.on('agent/request',self.request)
        self.on('context/tail',self.tail)

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
        for actor,a in list(state(self.r.backend)['actors'].items()):
            owner='nodes/npc_child' if a['role']=='child' else 'nodes/npc_resident'
            prompt=self.r.resource(owner,'prompt.md')+'\n你的名字：'+a['name']+'。你的初始打算：'+a['goal']
            if a.get('background'):prompt+='\n'+a['background']
            prompt+='\n\n'+profiles.prompt(self.r.backend,state(self.r.backend),actor)
            if actor in self.r.states:
                if self.r.state(actor)['prompt']!=prompt:self.r.plugins['capabilities/agent_runtime'].update_prompt('root',actor,prompt)
                continue
            old=self.r.backend.agents.get(actor)
            self.r.plugins['capabilities/agent_runtime'].create(actor,prompt,'root',2,['world_resident'],'npc_child' if a['role']=='child' else 'npc_resident',binding=old,resume=old is not None)
            self.r.rpc('agent_progress',target=actor,kind='world_npc')

    def guide(self,e):
        if e['actor']=='root' and e['name'].startswith('world_'):
            self.r.load('root','world:operator',self.r.resource('network_presets/small_town','AGENTS.md'))
        elif e['actor'] in (state(self.r.backend) or {}).get('actors',{}):self.resident_guide(e['actor'])

    def resident_guide(self,actor):
        self.r.load(actor,'world:resident',self.r.resource('nodes/npc_resident','AGENTS.md'))

    def pre_step(self,e):
        if e['actor'] not in (state(self.r.backend) or {}).get('actors',{}):return
        self.resident_guide(e['actor']);turn=self.turns.get(e['actor'])
        if turn and turn['active'] and turn['count']>=turn['limit']:raise RuntimeError('World NPC request budget exhausted')

    def request(self,e):
        actor=e['actor'];turn=self.turns.get(actor)
        if turn and turn['active']:
            if turn['count']>=turn['limit']:raise RuntimeError('World NPC request budget exhausted')
            turn['count']+=1
            self.r.rpc('agent_progress',target=actor,world_signal_id=turn['signal_id'],world_requests=turn['count'])

    def tail(self,e):
        w=state(self.r.backend);actor=e['actor']
        if not w or actor not in w['actors']:return
        a=w['actors'][actor];text='[小镇] 地点：'+a['place']+'。'
        if any(not m.get('read') for m in a['inbox']):text+='有未读交谈。'
        if any(v['carrier']==actor and not v.get('child') and v['due_tick']-w['tick']<=5 for v in w['pregnancies'].values()):text+='临近或已到预产时刻，请查看 world_look。'
        turn=self.turns.get(actor)
        if turn and turn['active']:text+=f"本次请求已用{turn['count']}/{turn['limit']}，处理完后自然结束。"
        e['texts'].append(text)

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

    def execute_npc(self,target,signal,execution_id,timeout_ms):
        previous=getattr(self.r.local,'execution_id',None);self.r.local.execution_id=execution_id
        limit=min(10,max(1,int(self.r.config.get('worldMaxRequests',8))))
        self.turns[target]=dict(active=True,signal_id=signal.signal_id,count=0,limit=limit)
        try:
            self.resident_guide(target)
            observation=self.r.rpc('world_look',actor=target)
            task=self.r.config.get('worldPulseTask','本时刻按自己的想法活动，处理完后正常结束。')
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
        async def clock_handler(context):
            return self.r.rpc('world_open_pulse',actor='root',signal_id=context.signal.signal_id)
        runtime.bind('world/time',clock_handler)
        async def npc_handler(context):
            target=context.delivery.node_id;signal=context.signal
            previous=self.inflight.get(target)
            if previous and not previous.done():raise RuntimeError('Previous NPC execution is still stopping')
            task=asyncio.create_task(asyncio.to_thread(self.execute_npc,target,signal,execution_id,min(90000,int(timeout_seconds*1000))))
            self.inflight[target]=task
            def finished(job):
                if self.inflight.get(target) is job:self.inflight.pop(target,None)
                if not job.cancelled():job.exception()
            task.add_done_callback(finished)
            try:
                result=await asyncio.shield(task)
                outcome=self.r.rpc('world_complete_pulse_actor',actor='root',target=target,signal_id=signal.signal_id,status='completed')
                return dict(**result,outcome=outcome)
            except BaseException as error:
                try:await asyncio.to_thread(self.r.host,'cancel-agent',actor=target)
                except Exception:pass
                self.r.rpc('world_complete_pulse_actor',actor='root',target=target,signal_id=signal.signal_id,status='unavailable',reason=str(error) or type(error).__name__)
                raise
        for target in targets:
            runtime.bind(target,npc_handler,capabilities=lambda t=target:tuple(self.r.state(t)['grant']['framework']),access_strength=2)
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
