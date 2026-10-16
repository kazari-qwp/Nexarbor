"""NPC application over core pulses, actual graph tools and resident text."""
import os,subprocess,sys,textwrap,unittest
from pathlib import Path
from test_knowledge_base import AGENT_SETUP
ROOT=Path(__file__).resolve().parents[1]
SETUP=AGENT_SETUP+r"""
from datanet.world.state import state,address,business
class WorldPort(Port):
    def __init__(self):super().__init__();self.actions={};self.calls=[];self.tails=[];self.failure=None;self.views=[]
    def __call__(self,name,p):
        if name=='view-update':self.views.append(p['actor'])
        if name=='cancel-agent':return {}
        if name=='run':
            actor=p['actor'];self.calls.append(actor)
            app.event(actor,'agent/pre-step',{});app.event(actor,'agent/request',{})
            tail=dict(actor=actor,texts=[]);app.emit('context/tail',**tail);self.tails.append(tail)
            if actor==self.failure:return dict(session_id=self.agents[actor]['session_id'],messages=[],completion='failed')
            action=self.actions.get(actor)
            if action:
                target,tool,args=action
                app.invoke(actor,'node_tools',dict(target=target,direction='write'))
                app.invoke(actor,'node_invoke',dict(target=target,tool=tool,direction='write',arguments=args))
            return dict(session_id=self.agents[actor]['session_id'],messages=[dict(role='assistant',content='本次活动结束。')],completion='completed')
        result=super().__call__(name,p)
        if name=='create':self.agents[p['actor']]['session_id']=p['binding']['session_id']
        return result
"""
class WorldTests(unittest.TestCase):
    def case(self,code):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/npc_world'),DATANET_COMPONENT_PROFILE='{}')
        env.pop('DATANET_COMPONENT_SELECTION',None)
        result=subprocess.run([sys.executable,'-X','utf8','-c',SETUP+textwrap.dedent(code)],cwd=ROOT,env=env,text=True,encoding='utf-8',capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_real_npc_location_tool_automatic_completion_and_closed_pulse(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town',worldAllowFullRun=False));app.bind_session('root-session')
            try:
                actor='world/npc/woodcutter';port.actions[actor]=(business('forest'),'chop',{})
                result=app.invoke('root','world_run_npc',dict(target=actor));report=result['pulse']['reports'][0]
                assert report['returned'] and report['status']=='completed'
                assert report['layers']==[['world/time'],[actor],['world/pulse']]
                assert [d['strength'] for d in report['deliveries']]==[2,1,0]
                assert port.calls==[actor]
                assert state(b)['actors'][actor]['inventory']['wood']==2
                assert state(b)['actors'][actor]['inventory']['axe']==2
                assert state(b)['round']['outcomes'][actor]['status']=='completed'
                assert not state(b)['round']['active']
                assert '第1天-早' in ' '.join(port.tails[0]['texts'])
                assert 'world_submit' not in port.tools[actor] and 'write_resident_text' not in port.tools[actor]
                assert not b.network.nodes['world/time'].expose
                assert not app.plugins['capabilities/text'].targets[actor]
                assert 'world/time' in [e.target_node_id for e in b.network.nodes[actor].read_interfaces if e.metadata.visibility=='private']
                assert all(not e.metadata.channels for n in b.network.nodes.values() if getattr(n,'kind',None)=='address' for e in n.write_interfaces)
                assert all(d['node_id'] not in [address('forest'),business('forest')] for d in report['deliveries'])
                second=app.invoke('root','world_run_npc',dict(target=actor))
                assert '第1天-午' in ' '.join(port.tails[1]['texts'])
                assert second['pulse']['reports'][0]['signal']['signal_id']!=report['signal']['signal_id']
            finally:stop(app,b)
        """)

    def test_business_range_readonly_clock_and_location_move(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                actor='world/npc/miner';reachable={n.node_id for n,_ in b.network.walk(actor,strength=2)}
                assert business('mine') in reachable and address('smithy') in reachable
                assert business('smithy') not in reachable
                assert app.invoke(actor,'node_tools',dict(target='world/time',direction='write'))=='该节点并未有向你开放的工具'
                port.actions[actor]=(address('smithy'),'move_here',{})
                app.invoke('root','world_run_npc',dict(target=actor));assert state(b)['actors'][actor]['place']=='smithy'
                port.actions[actor]=(business('smithy'),'repair',dict(item='pickaxe'))
                app.invoke('root','world_run_npc',dict(target=actor))
                assert state(b)['actors'][actor]['inventory']['pickaxe']==5
                assert state(b)['actors'][actor]['coins']==6
                assert business('mine') not in {n.node_id for n,_ in b.network.walk(actor,strength=2)}
            finally:stop(app,b)
        """)

    def test_error_is_not_normal_completion_and_siblings_continue(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                actor='world/npc/woodcutter';port.failure='world/npc/miner';port.actions[actor]=(business('forest'),'chop',{})
                result=app.invoke('root','world_round',{})
                assert result['pulse']['reports'][0]['status']=='partial'
                assert result['pulse']['reports'][0]['returned']
                assert result['settlement']['unavailable']==['world/npc/miner']
                assert state(b)['actors'][actor]['inventory']['wood']==2
                assert set(port.calls)==set(state(b)['actors'])
                assert state(b)['round']['outcomes']['world/npc/miner']['status']=='unavailable'
            finally:stop(app,b)
        """)

    def test_restore_uses_resident_time_and_rebinds_pulse_handlers(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/woodcutter'
            try:
                port.actions[actor]=(business('forest'),'chop',{})
                app.invoke('root','world_run_npc',dict(target=actor))
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                assert b.network.nodes['world/pulse'].state['sequence']==1
                assert b.network.nodes['world/time']._read_key('content').items[0]['content']=='第1天-早'
                result=app.invoke('root','world_run_npc',dict(target=actor))
                assert result['pulse']['reports'][0]['returned']
                assert b.network.nodes['world/pulse'].state['sequence']==2
                assert '第1天-午' in ' '.join(port.tails[0]['texts'])
            finally:stop(app,b)
        """)

    def test_birth_waits_for_next_pulse_and_has_private_clock_link(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                actor='world/npc/yue';lin='world/npc/lin'
                # Fixture establishes the already-agreed due pregnancy; production uses place tools.
                w=state(b);w['actors'][actor]['place']='hospital';w['pregnancies']['fixture']=dict(parents=[lin,actor],carrier=actor,due_tick=0,child=None)
                from datanet.world.state import presence
                presence(b,w);b.dispatch('save',{})
                port.actions[actor]=(business('hospital'),'birth',{})
                result=app.invoke('root','world_run_npc',dict(target=actor));child=result['settlement']['newborns'][0]
                assert child not in port.calls and child in app.states
                assert any(e.target_node_id=='world/time' and e.metadata.visibility=='private' for e in b.network.nodes[child].read_interfaces)
                port.actions={};port.calls=[]
                app.invoke('root','world_round',{})
                assert child in port.calls and len(state(b)['actors'])==7
            finally:stop(app,b)
        """)


    def test_identity_knowledge_private_links_and_profession_survives_moving(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                miner='world/npc/miner';wood='world/npc/woodcutter';yue='world/npc/yue'
                prompt=app.state(miner)['prompt']
                assert '你是一位男性居民' in prompt and '你是一位矿工' in prompt
                assert '你是一位伐木工' not in prompt and '医院选择birth' not in prompt
                assert '你是一位女性居民' in app.state(yue)['prompt'] and '你具备孕育能力' in app.state(yue)['prompt']
                assert '你目前正在怀孕' not in app.state(yue)['prompt']
                page='world/knowledge/profession/miner'
                result=app.invoke(miner,'node_read',dict(target=page,request=dict(method='key',key='content')))
                assert '获得2矿石' in json.dumps(result,ensure_ascii=False)
                assert b.network.nodes[page].expose==['read']
                reachable={n.node_id for n,_ in b.network.walk(wood,strength=100)}
                assert page not in reachable
                try:app.invoke(wood,'node_read',dict(target=page,request=dict(method='key',key='content')))
                except RuntimeError as error:assert 'forbidden' in str(error)
                else:raise AssertionError('another profession knowledge leaked')
                assert not any(x['node_id']==page for x in app.invoke(wood,'world_look',{})['knowledge'])
                port.views=[];app.plugins['capabilities/world_runtime'].mount();assert not port.views
                port.actions[miner]=(address('smithy'),'move_here',{})
                app.invoke('root','world_run_npc',dict(target=miner))
                assert app.state(miner)['prompt']==prompt
                assert page in {n.node_id for n,_ in b.network.walk(miner,strength=2)}
                assert not any(e.target_node_id==page for e in b.network.nodes[miner].write_interfaces)
                assert not app.plugins['capabilities/text'].targets[miner]
                from datanet.world.state import presence
                state(b)['actors'][wood]['role']='miner';presence(b,state(b));app.plugins['capabilities/world_runtime'].mount()
                assert '你是一位矿工' in app.state(wood)['prompt'] and '你是一位伐木工' not in app.state(wood)['prompt']
                assert page in {n.node_id for n,_ in b.network.walk(wood,strength=2)}
            finally:stop(app,b)
        """)

    def test_pregnancy_profiles_update_only_the_subject_and_restore(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/yue';lin='world/npc/lin';miner='world/npc/miner'
            try:
                from datanet.world.state import presence
                plugin=app.plugins['capabilities/world_runtime'];w=state(b)
                # A woman without gestational capability does not inherit that profile from gender.
                w['actors'][miner]['gender']='female';presence(b,w);plugin.mount()
                assert '你是一位女性居民' in app.state(miner)['prompt']
                assert '你具备孕育能力' not in app.state(miner)['prompt']
                common=b.network.nodes['world/common']._read_key('content').items[0]['content']
                assert '预产' not in common and '孕期' not in common
                assert '预产' not in app.resource('nodes/npc_resident','AGENTS.md')
                before=app.state(lin)['prompt']
                w['actors'][actor]['place']='hospital'
                w['pregnancies']['fixture']=dict(parents=[lin,actor],carrier=actor,due_tick=0,child=None)
                presence(b,w);plugin.mount()
                assert '你目前正在怀孕' in app.state(actor)['prompt'] and '医院选择birth' in app.state(actor)['prompt']
                assert app.state(lin)['prompt']==before and '你目前正在怀孕' not in app.state(miner)['prompt']
                port.actions[actor]=(business('hospital'),'birth',{})
                result=app.invoke('root','world_run_npc',dict(target=actor));child=result['settlement']['newborns'][0]
                assert '你目前正在怀孕' not in app.state(actor)['prompt']
                assert '你已经有孩子' in app.state(actor)['prompt'] and '你已经有孩子' in app.state(lin)['prompt']
                assert 'world/knowledge/life/pregnant' not in {n.node_id for n,_ in b.network.walk(actor,strength=2)}
                assert '你是刚出生' in app.state(child)['prompt'] and '你的性别尚未设定' in app.state(child)['prompt']
                assert '你具备孕育能力' not in app.state(child)['prompt']
                b.dispatch('save',{})
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                assert '你已经有孩子' in app.state(actor)['prompt'] and '你目前正在怀孕' not in app.state(actor)['prompt']
                assert 'world/knowledge/profession/miner' in {n.node_id for n,_ in b.network.walk(miner,strength=2)}
            finally:stop(app,b)
        """)

if __name__=='__main__':unittest.main()
