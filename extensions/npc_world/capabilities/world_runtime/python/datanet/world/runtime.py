"""Native Harness events plus an explicit, bounded single-phase scheduler."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from threading import Lock
import json
from datanet.core.application import Component
from datanet.world.state import state,clock
from datanet.rounds import barrier

class Plugin(Component):
    def install(self):
        self.turns={};self.running=set();self.lock=Lock();self.phase_lock=Lock()
        self.on('session/root',self.root)
        self.on('tool/before',self.guide)
        self.on('agent/pre-step',self.pre_step)
        self.on('agent/request',self.request)
        self.on('agent/turn-stopping',self.stopping)
        self.on('context/tail',self.tail)

    def root(self,e):
        if self.r.config.get('rootNetwork')!='small_town':return
        owner='network_presets/small_town'
        self.r.rpc('world_init',actor='root',config=self.r.resource(owner,'town.json',True),common=self.r.resource(owner,'COMMON.md'))
        self.r.rpc('bind_agent',target='root',session_id=e['session_id'],kind='root',manager_id=None,creator_node_id=None)
        e['view']=self.r.bind('root',e['session_id'],'world_operator',self.r.resolve(['world_operator']),self.r.resource(owner,'prompt.md'))
        self.mount()

    def mount(self):
        for actor,a in list(state(self.r.backend)['actors'].items()):
            if actor in self.r.states:continue
            owner='nodes/npc_child' if a['role']=='child' else 'nodes/npc_resident'
            prompt=self.r.resource(owner,'prompt.md')+'\n你的名字：'+a['name']+'。你的初始打算：'+a['goal']
            if a.get('background'):prompt+='\n'+a['background']
            old=self.r.backend.agents.get(actor)
            self.r.plugins['capabilities/agent_runtime'].create(actor,prompt,'root',2,['world_resident'],'npc_child' if a['role']=='child' else 'npc_resident',binding=old,resume=old is not None)
            self.r.rpc('agent_progress',target=actor,kind='world_npc')

    def guide(self,e):
        if e['actor']=='root' and e['name'].startswith('world_'):
            self.r.load('root','world:operator',self.r.resource('network_presets/small_town','AGENTS.md'))
        elif e['actor'] in (state(self.r.backend) or {}).get('actors',{}):
            self.resident_guide(e['actor'])

    def resident_guide(self,actor):
        self.r.load(actor,'world:resident',self.r.resource('nodes/npc_resident','AGENTS.md'))

    def pre_step(self,e):
        if e['actor'] not in (state(self.r.backend) or {}).get('actors',{}):return
        self.resident_guide(e['actor'])
        turn=self.turns.get(e['actor'])
        if turn and turn['active'] and turn['count']>=turn['limit']:raise RuntimeError('World NPC request budget exhausted')

    def request(self,e):
        actor=e['actor'];turn=self.turns.get(actor)
        if turn and turn['active']:
            if turn['count']>=turn['limit']:raise RuntimeError('World NPC request budget exhausted')
            turn['count']+=1
            self.r.rpc('agent_progress',target=actor,world_tick=turn['tick'],world_requests=turn['count'])

    def stopping(self,e):
        actor=e['actor'];turn=self.turns.get(actor);w=state(self.r.backend) or {}
        if turn and turn['active'] and actor not in w['barrier']['submitted'] and turn['count']<turn['limit']:
            self.r.host('steer',actor=actor,text='本时刻尚未提交。请用 world_submit 提交已选行动；未选行动表示等待。')

    def tail(self,e):
        w=state(self.r.backend);actor=e['actor']
        if not w or actor not in w['actors']:return
        a=w['actors'][actor];c=clock(w['tick'])
        if w['barrier'].get('active'):
            status='已提交' if actor in w['barrier']['submitted'] else '待提交'
        else:status='等待下一时刻开启'
        text=f"[小镇] 第{c['day']}天·{c['slot']}；地点：{a['place']}；{status}。"
        if any(not m.get('read') for m in a['inbox']):text+='有未读交谈。'
        if any(v['carrier']==actor and not v.get('child') and v['due_tick']-w['tick']<=5 for v in w['pregnancies'].values()):text+='临近或已到预产时刻，请查看 world_look。'
        turn=self.turns.get(actor)
        if turn and turn['active']:
            left=max(0,turn['limit']-turn['count'])
            text+=f"本时刻模型请求已用{turn['count']}/{turn['limit']}。"
            if left<=1:text+='下次必须提交 world_submit；不要再查询或写记忆。'
        e['texts'].append(text)

    def tool_world_look(self,actor,p):return self.r.rpc('world_look',actor=actor)
    def tool_world_messages(self,actor,p):return self.r.rpc('world_messages',actor=actor)
    def tool_world_submit(self,actor,p):
        result=self.r.rpc('world_submit',actor=actor,**p)
        self.r.host('conclude')
        return result
    def tool_world_observe(self,actor,p):
        w=self.r.rpc('world_observe',actor=actor)
        if p.get('target'):
            if p['target'] not in w['actors']:raise ValueError('Unknown resident')
            return dict(clock=clock(w['tick']),resident=w['actors'][p['target']],binding=self.r.backend.agents.get(p['target']),result=w['results'].get(p['target']))
        return dict(clock=clock(w['tick']),places=w['config']['places'],roads=w['config']['roads'],
                    residents=[dict(id=k,name=a['name'],place=a['place'],role=a['role'],session_id=self.r.backend.agents.get(k,{}).get('session_id')) for k,a in w['actors'].items()],
                    active=w['barrier'].get('active',False),pending=barrier.pending(w['barrier']) if w['barrier'].get('active') else [],
                    events=w['events'][-20:],results=w['results'])

    def schedule(self,actor,target,timeout_ms):
        w=state(self.r.backend)
        if actor!='root' or target not in w['actors']:raise PermissionError('Only operator may run a resident')
        if not w['barrier'].get('active') or target not in w['barrier']['participants']:raise ValueError('Begin the time slot first')
        if target in w['barrier']['submitted']:return dict(status='already_submitted')
        import time
        timeout_ms=min(timeout_ms,max(1,int((w['barrier']['deadline']-time.time())*1000)))
        with self.lock:
            if target in self.running:raise RuntimeError('Resident already running')
            self.running.add(target)
        try:
            limit=min(10,max(1,int(self.r.config.get('worldMaxRequests',8))))
            saved=self.r.backend.agents[target]
            count=saved.get('world_requests',0) if saved.get('world_tick')==w['tick'] else 0
            self.turns[target]=dict(active=True,tick=w['tick'],count=count,limit=limit)
            self.resident_guide(target)
            observation=self.r.rpc('world_look',actor=target)
            # Exact prior results are admitted once per game slot; the tail remains short.
            text='现在是新的小镇时刻。按自己的想法行动，最后提交一次。\n'+json.dumps(observation,ensure_ascii=False)
            result=self.r.plugins['capabilities/agent_runtime'].execute(actor,target,text,kind='world_npc',timeout_ms=timeout_ms)
            if target not in state(self.r.backend)['barrier']['submitted']:raise RuntimeError('Resident ended without submitting; requests='+str(self.turns[target]['count'])+'/'+str(limit))
            return dict(status='submitted',session_id=result['session_id'],requests=self.turns[target]['count'])
        except Exception as error:
            # An already-disconnected native handle must not block the barrier.
            try:self.r.host('cancel-agent',actor=target)
            except Exception:pass
            self.r.rpc('world_abandon',actor='root',target=target,reason=str(error))
            return dict(status='unavailable',reason=str(error))
        finally:
            if target in self.turns:self.turns[target]['active']=False
            with self.lock:self.running.discard(target)

    def tool_world_run_npc(self,actor,p):
        if not self.phase_lock.acquire(blocking=False):raise RuntimeError('Another world operation is in progress')
        try:
            self.mount()
            return self.schedule(actor,p['target'],min(120000,max(1000,p.get('timeout_ms',90000))))
        finally:self.phase_lock.release()

    def tool_world_round(self,actor,p):
        if not self.phase_lock.acquire(blocking=False):raise RuntimeError('Another world operation is in progress')
        try:return self.round_operation(actor,p)
        finally:self.phase_lock.release()

    def round_operation(self,actor,p):
        if actor!='root':raise PermissionError('Only operator may advance the world')
        action=p['action']
        if action=='begin':return self.r.rpc('world_begin',actor=actor,timeout_seconds=p.get('timeout_seconds',180))
        if action=='settle':
            result=self.r.rpc('world_settle',actor=actor);self.mount();return result
        if action=='cancel':
            w=state(self.r.backend)
            with self.lock:
                if self.running:raise ValueError('Wait for bounded NPC runs to finish before cancelling the round')
            if not w['barrier'].get('active'):return dict(cancelled=False)
            for target in barrier.pending(w['barrier']):self.r.rpc('world_abandon',actor=actor,target=target,reason='operator_end_slot')
            result=self.r.rpc('world_settle',actor=actor);self.mount();return result
        if action!='run':raise ValueError('Unknown round action')
        if not self.r.config.get('worldAllowFullRun',True):raise PermissionError('This runtime allows only single-resident tests')
        with self.lock:
            if self.running:raise RuntimeError('A resident is already running')
        self.mount();self.r.rpc('world_begin',actor=actor,timeout_seconds=p.get('timeout_seconds',180))
        execution=getattr(self.r.local,'execution_id',None)
        def run(target):
            self.r.local.execution_id=execution
            return self.schedule(actor,target,120000)
        targets=barrier.pending(state(self.r.backend)['barrier']);results={}
        with ThreadPoolExecutor(max_workers=max(1,len(targets)),thread_name_prefix='world-npc') as pool:
            jobs={pool.submit(run,t):t for t in targets}
            for job in as_completed(jobs):results[jobs[job]]=job.result()
        settled=self.r.rpc('world_settle',actor=actor);self.mount()
        return dict(runs=results,settlement=settled)
