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
            tail=dict(actor=actor,texts=app.input_tail(actor));app.emit('context/tail',**tail);self.tails.append(tail)
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
                assert 'world/time' not in [e.target_node_id for e in b.network.nodes[actor].read_interfaces]
                assert any(e.target_node_id=='world/time' for e in b.network.nodes[actor+'/context'].read_interfaces)
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
                assert any(e.target_node_id==child+'/context' and e.metadata.visibility=='private' for e in b.network.nodes[child].read_interfaces)
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
                matcher=app.plugins['capabilities/context_assembly'];plugin=app.plugins['capabilities/world_runtime']
                stable=app.state(miner)['prompt'];assert '男性' not in stable and '矿工' not in stable
                first=matcher.assemble(miner);assert len(first['sources'][0]['loaded'])==3
                text=' '.join(v for (actor,key),v in port.docs.items() if actor==miner)
                assert '你是一位男性居民' in text and '你是一位矿工' in text
                assert '你是一位伐木工' not in text and '医院选择birth' not in text
                assert not matcher.assemble(miner)['sources'][0]['loaded']
                page='world/knowledge/profession/miner'
                result=app.invoke(miner,'node_read',dict(target=page,request=dict(method='key',key='content')))
                assert '获得2矿石' in json.dumps(result,ensure_ascii=False)
                assert b.network.nodes[page].expose==['read']
                assert page not in {n.node_id for n,_ in b.network.walk(wood,strength=100)}
                try:app.invoke(wood,'node_read',dict(target=page,request=dict(method='key',key='content')))
                except RuntimeError as error:assert 'forbidden' in str(error)
                else:raise AssertionError('another profession knowledge leaked')
                port.views=[];plugin.mount()
                port.actions[miner]=(address('smithy'),'move_here',{})
                app.invoke('root','world_run_npc',dict(target=miner))
                assert app.state(miner)['prompt']==stable
                assert page in {n.node_id for n,_ in b.network.walk(miner,strength=2)}
                assert not any(e.target_node_id==page for e in b.network.nodes[miner].write_interfaces)
                assert not app.plugins['capabilities/text'].targets[miner]
                from datanet.world.state import presence
                state(b)['actors'][wood]['role']='miner';presence(b,state(b));plugin.mount()
                assert page in matcher.assemble(wood)['sources'][0]['matched']
                assert b.network.nodes[wood].__dict__.get('gender') is None
            finally:stop(app,b)
        """)

    def test_pregnancy_profiles_change_documents_without_changing_system_prompt(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/yue';lin='world/npc/lin';miner='world/npc/miner'
            try:
                from datanet.world.state import presence
                plugin=app.plugins['capabilities/world_runtime'];matcher=app.plugins['capabilities/context_assembly'];w=state(b)
                stable=app.state(actor)['prompt'];w['actors'][miner]['gender']='female';presence(b,w);plugin.mount()
                selected=matcher.assemble(miner)['sources'][0]['matched']
                assert 'world/knowledge/gender/female' in selected and 'world/knowledge/life/gestation' not in selected
                common=b.network.nodes['world/common']._read_key('content').items[0]['content']
                assert '预产' not in common and '孕期' not in common and '预产' not in app.resource('nodes/npc_resident','AGENTS.md')
                assert 'world/knowledge/life/pregnant' not in matcher.assemble(actor)['sources'][0]['matched']
                w['actors'][actor]['place']='hospital';w['pregnancies']['fixture']=dict(parents=[lin,actor],carrier=actor,due_tick=0,child=None)
                presence(b,w);plugin.mount()
                assert 'world/knowledge/life/pregnant' in matcher.assemble(actor)['sources'][0]['matched']
                assert 'world/knowledge/life/pregnant' not in matcher.assemble(lin)['sources'][0]['matched']
                port.actions[actor]=(business('hospital'),'birth',{})
                result=app.invoke('root','world_run_npc',dict(target=actor));child=result['settlement']['newborns'][0]
                selected=matcher.assemble(actor)['sources'][0]['matched']
                assert 'world/knowledge/life/pregnant' not in selected and 'world/knowledge/life/parent' in selected
                latest=app.rpc('context_assembly_get',target=actor,node_id=actor+'/context')
                assert latest['current']['metadata']['extensions']['npc']['pregnant'] is False and 'world/knowledge/life/pregnant' in latest['removed']
                assert app.state(actor)['prompt']==stable
                assert any('医院选择birth' in text for (owner,key),text in port.docs.items() if owner==actor)
                assert 'world/knowledge/profession/child' in matcher.assemble(child)['sources'][0]['matched']
                b.dispatch('save',{})
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                matched=app.plugins['capabilities/context_assembly'].assemble(actor)['sources'][0]['matched']
                assert 'world/knowledge/life/parent' in matched and 'world/knowledge/life/pregnant' not in matched
            finally:stop(app,b)
        """)

    def test_prompt_markers_versioning_and_compaction_independent_of_signals(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                actor='world/npc/miner';matcher=app.plugins['capabilities/context_assembly'];page='world/knowledge/profession/miner'
                stable=app.state(actor)['prompt'];first=matcher.assemble(actor);count=len(port.docs)
                assert not port.calls and not matcher.assemble(actor)['sources'][0]['loaded'] and len(port.docs)==count
                from datanet.core.agent_inputs import digest
                removed=[key for key in port.docs if key[0]==actor and key[1]=='agent-input:'+digest(['context-assembly:'+actor+'/context',page])]
                del port.docs[removed[0]]
                assert matcher.assemble(actor)['sources'][0]['loaded']==[page] and len(port.docs)==count
                b.network.nodes[page].write('content','矿工知识新版：留意镐子耐久。')
                assert matcher.assemble(actor)['sources'][0]['loaded']==[page]
                before=app.rpc('context_assembly_get',target=actor,node_id=actor+'/context')['revision']
                from datanet.world.state import presence
                state(b)['actors'][actor]['gender']='female';presence(b,state(b));matcher.assemble(actor)
                state(b)['actors'][actor]['gender']='male';presence(b,state(b));back=matcher.assemble(actor)
                assert not back['sources'][0]['loaded']
                assert app.rpc('context_assembly_get',target=actor,node_id=actor+'/context')['revision']==before+2
                for key in list(port.docs):
                    if key[0]==actor:del port.docs[key]
                again=matcher.assemble(actor);assert len(again['sources'][0]['loaded'])==3
                assert app.state(actor)['prompt']==stable and not port.calls
            finally:stop(app,b)
        """)


    def test_npc_uses_node_metadata_extender_without_adding_core_fields(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                actor='world/npc/miner';extra=app.plugins['capabilities/node_metadata'];matcher=app.plugins['capabilities/context_assembly']
                extra.set(actor,'npc',{'temperament':'cautious'})
                values=b.network.get_metadata(actor)['extensions']['npc'];assert values['role']=='miner' and values['temperament']=='cautious'
                matcher.assemble(actor)
                current=app.rpc('context_assembly_get',target=actor,node_id=actor+'/context')['current']['metadata']
                assert current['extensions']['npc']['temperament']=='cautious' and current['extensions']['npc']['role']=='miner'
                assert not hasattr(b.network.nodes[actor],'temperament') and 'temperament' not in state(b)['actors'][actor]
            finally:stop(app,b)
        """)

if __name__=='__main__':unittest.main()
