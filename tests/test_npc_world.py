"""Node-local NPC modules, immediate effects, graph grants and restart."""
import os,subprocess,sys,textwrap,unittest
from pathlib import Path
from test_knowledge_base import AGENT_SETUP
ROOT=Path(__file__).resolve().parents[1]
SETUP=AGENT_SETUP+r"""
from datanet.world.model import instance,person,residents,presence,clock,tick
from pathlib import Path
ROOT=Path.cwd()
from datanet.core.node import Node
from datanet.core.interface import Interface

def address(place):return 'world/place/'+place
def business(place):return 'world/service/'+place
class WorldPort(Port):
    def __init__(self):super().__init__();self.actions={};self.calls=[];self.tails=[];self.failure=None;self.views=[];self.during=None;self.conclusions=[]
    def __call__(self,name,p):
        if name=='view-update':self.views.append(p['actor'])
        if name=='cancel-agent':return {}
        if name=='conclude':self.conclusions.append(p.get('execution_id'));return {}
        if name=='run':
            actor=p['actor'];self.calls.append(actor)
            app.event(actor,'agent/pre-step',{});app.event(actor,'agent/request',{})
            tail=dict(actor=actor,texts=app.input_tail(actor));app.emit('context/tail',**tail);self.tails.append(tail)
            if actor==self.failure:return dict(session_id=self.agents[actor]['session_id'],messages=[],completion='failed')
            action=self.actions.get(actor)
            if action:
                target,tool,args=action
                use(actor,target,tool,args)
            if self.during:self.during(actor)
            return dict(session_id=self.agents[actor]['session_id'],messages=[dict(role='assistant',content='本次活动结束。')],completion='completed')
        result=super().__call__(name,p)
        if name=='create':self.agents[p['actor']]['session_id']=p['binding']['session_id']
        return result

def use(actor,target,tool,args=None,read=False):
    direction='read' if read else 'write'
    assembly=instance(b,actor,'tools.assembly')
    def find():return next((k for k,v in assembly.aliases.items() if v['target']==target and v['tool']==tool and v['direction']==direction),None)
    name=find()
    if name is None:assembly.assemble();name=find()
    if name is None:raise PermissionError('No direct entry in current access scope')
    return app.invoke(actor,name,args or {})
def begin(actor,signal='fixture'):
    old=instance(b,actor,'agent.signal').state
    if old.get('status')=='running':b.dispatch('node_activity_end',dict(target=actor,signal_id=old['signal_id'],status='completed'))
    b.dispatch('node_clock_advance',dict(target='world/time',signal_id=signal))
    b.dispatch('node_activity_start',dict(target=actor,signal_id=signal))
"""
class WorldTests(unittest.TestCase):
    def case(self,code):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/npc_world'),DATANET_COMPONENT_PROFILE='{}')
        env.pop('DATANET_COMPONENT_SELECTION',None)
        result=subprocess.run([sys.executable,'-X','utf8','-c',SETUP+textwrap.dedent(code)],cwd=ROOT,env=env,text=True,encoding='utf-8',capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_disk_graph_has_no_start_special_nodes_or_settler(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                assert len(b.network.nodes)==51 and not port.calls
                assert not any('start' in k or 'settle' in k for k in b.network.nodes)
                assert 'world_init' not in b.components.routes and 'world_settle' not in b.components.routes
                assert 'npc_world' not in b.extension_state
                assert type(b.network.nodes[address('mine')]) is Node
                from datanet.core.agent_node import AgentNode
                assert type(b.network.nodes['world/npc/miner']) is AgentNode
                assert not hasattr(b.network.nodes[address('mine')],'place')
                assert set(app.states)=={'root',*residents(b)}
                doc=json.loads((ROOT/'extensions/npc_world/network_presets/small_town/network.json').read_text(encoding='utf-8'))
                assert len(doc['network']['nodes'])==len(b.network.nodes)
            finally:stop(app,b)
        """)

    def test_second_miner_reuses_modules_and_has_independent_identity(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                old='world/npc/miner';new='world/npc/miner2'
                a=person(b,old).state;c=person(b,new).state
                assert {k:v for k,v in a.items() if k not in ('id','name')}=={k:v for k,v in c.items() if k not in ('id','name')}
                assert set(b.network.nodes[old].modules)==set(b.network.nodes[new].modules)
                assert b.network.nodes[old].file_path!=b.network.nodes[new].file_path
                assert new in instance(b,business('home2'),'world.household').state['residents']
                assert instance(b,new,'input.opening').config!=instance(b,old,'input.opening').config
                assert new in [e.target_node_id for e in b.network.nodes[address('mine')].read_interfaces]
            finally:stop(app,b)
        """)

    def test_closed_signal_loop_and_immediate_effect_before_agent_end(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/woodcutter'
            try:
                port.actions[actor]=(business('forest'),'chop',{})
                def during(target):
                    assert person(b,actor).state['inventory']['wood']==2
                    assert instance(b,actor,'agent.signal').state['status']=='running'
                port.during=during
                result=app.invoke('root','world_run_npc',dict(target=actor));report=result['pulse']['reports'][0]
                assert report['returned'] and report['status']=='completed'
                assert report['layers']==[['world/time'],[actor],['world/savepoint'],['world/pulse']]
                assert instance(b,actor,'agent.signal').state['status']=='completed'
                assert 'settlement' not in result and '第1天-早' in ' '.join(port.tails[0]['texts'])
                assert 'world_submit' not in port.tools[actor] and not b.network.nodes['world/time'].expose
                port.actions={};port.during=None
                app.invoke('root','world_run_npc',dict(target=actor))
                assert '第1天-午' in ' '.join(port.tails[1]['texts'])
            finally:stop(app,b)
        """)

    def test_five_signal_savepoint_fanin_restart_and_duplicate(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                for _ in range(4):app.invoke('root','world_run_npc',dict(target=actor))
                assert instance(b,'world/savepoint','checkpoint.counter').state['count']==4
                assert not b.store.stats()['full_snapshot_requested']
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                before=b.store.stats()['full_snapshot_count']
                result=instance(b,'root','scene.operator').run([actor,'world/npc/woodcutter'],30)
                report=result['pulse']['reports'][0]
                assert report['returned'] and report['layers'][2]==['world/savepoint']
                counter=instance(b,'world/savepoint','checkpoint.counter')
                assert counter.state['count']==5 and b.store.stats()['full_snapshot_requested']
                assert b.store.stats()['full_snapshot_count']>before
                duplicate=b.dispatch('node_savepoint_arrive',dict(target='world/savepoint',signal_id=counter.state['last_signal']))
                assert duplicate==dict(count=5,reused=True)
                info=b.dispatch('persistence_info',{})
                point=b.dispatch('persistence_checkpoint',dict(expected_commit=info['commit_id'],bindings=info['bindings'],contexts={k:dict(session_id=v) for k,v in info['bindings'].items()}))
                assert point['kind']=='full' and not b.store.stats()['full_snapshot_requested']
                node=next(n for n in b.store.bundle(point['id'])['document']['network']['nodes'] if n['node_id']=='world/savepoint')
                assert node['modules']['checkpoint.counter']['state']['count']==5
                app.invoke('root','world_run_npc',dict(target=actor))
                assert counter.state['count']==6 and not b.store.stats()['full_snapshot_requested']
            finally:stop(app,b)
        """)

    def test_npc_map_access_returns_only_local_tools_and_view(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                for npc in residents(b):
                    names={d['name'] for d in app.definitions(npc)}
                    assert not {'node_list','node_tools','node_invoke'}&names
                    assert {'node_read','world_messages','datanet_memory_read','datanet_memory_write'}<=names
                for name,args in [('node_list',{}),('node_tools',dict(target=address('smithy'))),('node_invoke',dict(target=address('smithy'),tool='move_here',arguments={}))]:
                    try:app.invoke(actor,name,args)
                    except PermissionError:pass
                    else:raise AssertionError('discovery tool still granted')
                view=app.invoke(actor,'world_look',{})
                assert view['location']==dict(id=address('mine'),name='矿坑',service=business('mine'))
                assert view['neighbors']==[dict(id=address('smithy'),name='铁匠铺')]
                assembly=instance(b,actor,'tools.assembly');assembly.assemble()
                tools=[v for v in assembly.aliases.values() if v['target']==address('smithy')]
                assert [x['tool'] for x in tools]==['move_here'] and tools[0]['spec']['parameters']['properties']=={}
                assert not any(v['target']==business('smithy') for v in assembly.aliases.values())
                try:app.invoke(actor,'node_read',dict(target=address('smithy'),request=dict(method='key',key='content')))
                except RuntimeError as e:assert json.loads(str(e))['status']=='unsupported'
                else:raise AssertionError('address exposed text')
                begin(actor);result=use(actor,address('smithy'),'move_here')
                value=result['items'][0]['result'];assert value['arrived']==address('smithy') and value['destination']=='铁匠铺' and value['tick_finished']
                begin(actor,'next-slot');assembly.assemble()
                assert any(v['tool']=='repair' for v in assembly.aliases.values())
                assert dict(id='world/npc/smith',name=person(b,'world/npc/smith').state['name']) in app.invoke(actor,'world_look',{})['people']
            finally:stop(app,b)
        """)

    def test_move_changes_permissions_now_and_cannot_spend_two_actions(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                assert business('smithy') not in {n.node_id for n,_ in b.network.walk(actor,strength=2)}
                begin(actor);use(actor,address('smithy'),'move_here')
                assert person(b,actor).state['place']==address('smithy')
                assert business('smithy') in {n.node_id for n,_ in b.network.walk(actor,strength=2)}
                assert business('mine') not in {n.node_id for n,_ in b.network.walk(actor,strength=2)}
                assert 'world/npc/smith' in [e.target_node_id for e in b.network.nodes[address('smithy')].read_interfaces]
                try:use(actor,business('smithy'),'repair',dict(item='pickaxe'))
                except ValueError as e:assert 'Movement ended this time slot' in str(e)
                else:raise AssertionError('second action accepted')
                assert len(port.conclusions)==1
                try:use(actor,'world/npc/smith','talk',dict(content='should not send'))
                except ValueError as e:assert 'Movement ended this time slot' in str(e)
                else:raise AssertionError('conversation after movement accepted')
                assert not person(b,'world/npc/smith').state['inbox']
                begin(actor,'next-tick');assert use(actor,business('smithy'),'local_info',read=True)
                use(actor,'world/npc/smith','talk',dict(content='next tick'))
                assert person(b,'world/npc/smith').state['inbox'][-1]['content']=='next tick'
            finally:stop(app,b)
        """)

    def test_failed_movement_keeps_turn_and_parallel_npcs_do_not_wait_for_each_other(self):
        self.case("""
        from threading import Barrier
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                begin(actor)
                try:use(actor,address('smithy'),'move_here',dict(unexpected=True))
                except ValueError:pass
                else:raise AssertionError('invalid movement accepted')
                assert not port.conclusions and person(b,actor).state['place']==address('mine')
                assert person(b,actor).state['action_tick'] is None
                use(actor,address('smithy'),'move_here');assert len(port.conclusions)==1
                b.dispatch('node_activity_end',dict(target=actor,signal_id='fixture',status='completed'))
                gate=Barrier(2,timeout=5)
                port.during=lambda target:gate.wait()
                result=instance(b,'root','scene.operator').run([actor,'world/npc/woodcutter'],15)
                assert result['pulse']['reports'][0]['status']=='completed', result
                assert set(port.calls)=={actor,'world/npc/woodcutter'}
            finally:stop(app,b)
        """)

    def test_failed_action_rolls_back_resources_and_keeps_quota(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                presence(b,actor,address('smithy'));begin(actor)
                a=person(b,actor).state;a['coins']=1
                stock=instance(b,business('smithy'),'world.repair').state
                try:use(actor,business('smithy'),'repair',dict(item='pickaxe'))
                except ValueError:pass
                else:raise AssertionError('unfunded repair succeeded')
                assert stock['materials']=={'wood':8,'ore':8} and a['inventory']['pickaxe']==0 and a['action_tick'] is None
                a['coins']=8;use(actor,business('smithy'),'repair',dict(item='pickaxe'))
                assert a['coins']==6 and a['inventory']['pickaxe']==5
                assert b.network.get_metadata(address('smithy'))['extensions']['place']['materials']=={'wood':7,'ore':7}
            finally:stop(app,b)
        """)

    def test_mount_any_node_unmount_and_restore_are_explicit(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/woodcutter'
            try:
                # An ordinary service node gains a second gathering operation only by mounting.
                target=business('forest');assert 'drink' not in b.network.nodes[target].tools
                b.modules.mount(target,'world.refreshment',dict(address=address('forest'),price=1,restore=1))
                begin(actor);person(b,actor).state['stamina']=1;use(actor,target,'drink')
                assert person(b,actor).state['stamina']==2
                b.modules.unmount(target,'world.refreshment');assert 'drink' not in b.network.nodes[target].tools and 'drink' not in b.network.nodes[target].expose
                b.dispatch('save',{})
            finally:stop(app,b)
            b=Backend(folder)
            try:
                assert 'drink' not in b.network.nodes[target].tools
                assert person(b,actor).state['stamina']==2
                assert 'chop' in b.network.nodes[target].tools
                assert 'chop' not in b.network.nodes[business('mine')].tools
            finally:b.close()
        """)

    def test_rest_permission_and_public_metadata(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                presence(b,actor,address('home1'));begin(actor);person(b,actor).state['stamina']=1
                try:use(actor,business('home1'),'rest')
                except PermissionError as e:assert '自己登记居住' in str(e)
                else:raise AssertionError('visitor rested')
                assert person(b,actor).state['action_tick'] is None
                presence(b,actor,address('home2'));use(actor,business('home2'),'rest')
                assert person(b,actor).state['stamina']==4
                for home,count in [('home1',2),('home2',4)]:
                    assert len(b.network.get_metadata(address(home))['extensions']['place']['residents'])==count
                assert 'rest' not in b.network.nodes[business('hospital')].tools
            finally:stop(app,b)
        """)

    def test_failed_residents_keep_successful_effects_and_siblings_continue(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                port.failure='world/npc/miner';port.actions['world/npc/woodcutter']=(business('forest'),'chop',{})
                def later_error(actor):
                    if actor=='world/npc/woodcutter':raise RuntimeError('model failed after successful tool')
                port.during=later_error
                result=app.invoke('root','world_round',{})
                assert result['pulse']['reports'][0]['returned'] and result['pulse']['reports'][0]['status']=='partial'
                assert instance(b,port.failure,'agent.signal').state['status']=='unavailable'
                assert instance(b,'world/npc/woodcutter','agent.signal').state['status']=='unavailable'
                assert person(b,'world/npc/woodcutter').state['inventory']['wood']==2
                assert set(port.calls)==set(residents(b))
            finally:stop(app,b)
        """)

    def test_marriage_family_birth_and_next_signal_child(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            lin='world/npc/lin';yue='world/npc/yue'
            try:
                for actor in (lin,yue):presence(b,actor,address('civil_registry'));begin(actor,'marriage')
                use(lin,business('civil_registry'),'marry',dict(partner=yue));assert person(b,lin).state['spouse'] is None
                use(yue,business('civil_registry'),'marry',dict(partner=lin));assert person(b,lin).state['spouse']==yue
                for actor in (lin,yue):presence(b,actor,address('home1'));begin(actor,'family')
                use(lin,business('home1'),'plan_family',dict(partner=yue));use(yue,business('home1'),'plan_family',dict(partner=lin))
                pregnancy=next(iter(instance(b,business('home1'),'world.family').state['pregnancies'].values()))
                assert pregnancy['due_tick']==tick(b)+10
                app.event(yue,'context/prepare',{})
                assert 'world/knowledge/life/pregnant' in app.plugins['capabilities/context_assembly'].assemble(yue)['sources'][0]['matched']
                presence(b,yue,address('hospital'));begin(yue,'too-early')
                try:use(yue,business('hospital'),'birth')
                except ValueError:pass
                else:raise AssertionError('early birth')
                assert len(residents(b))==7
                pregnancy=next(iter(instance(b,business('home1'),'world.family').state['pregnancies'].values()))
                clock(b).state['tick']=pregnancy['due_tick'];begin(yue,'due')
                use(yue,business('hospital'),'birth');child=pregnancy['child']
                assert child in residents(b) and child not in port.calls
                assert child not in [e.target_node_id for e in b.network.nodes['world/time'].write_interfaces]
                assert child in instance(b,business('home1'),'world.household').state['residents']
                assert person(b,child).state['parents']==[lin,yue]
                app.event(yue,'context/prepare',{})
                assert 'world/knowledge/life/pregnant' not in app.plugins['capabilities/context_assembly'].assemble(yue)['sources'][0]['matched']
                app.invoke('root','world_run_npc',dict(target=child))
                assert port.calls==[child] and len(residents(b))==8
                app.plugins['capabilities/context_assembly'].assemble(child)
                assert any('你住在居民楼1。' in section['text'] for section in app.view(child)['sections'])
                assert any('# 小镇常识（只读）' in section['text'] for section in app.view(child)['sections'])
                assert any(who==child and '# 小镇地图' in text for (who,doc),text in port.docs.items())
            finally:stop(app,b)
        """)

    def test_context_identity_memory_and_restart_clock(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/woodcutter'
            try:
                stable=app.state(actor)['prompt'];matcher=app.plugins['capabilities/context_assembly']
                first=matcher.assemble(actor);assert len(first['sources'][0]['loaded'])==4
                system='\\n'.join(section['text'] for section in app.view(actor)['sections'])
                assert system.count('# 小镇常识（只读）')==1
                assert '本世界的居民不需要睡觉' in system
                assert 'common' not in app.invoke(actor,'world_look',{})
                try:app.invoke(actor,'node_read',dict(target='world/common',request=dict(method='key',key='content')))
                except RuntimeError as e:assert json.loads(str(e))['status']=='forbidden'
                else:raise AssertionError('redundant common read grant remains')
                family=app.invoke(actor,'node_read',dict(target='world/knowledge/life/family',request=dict(method='key',key='content')))
                assert '结婚需' in family['items'][0]['content']
                assert not matcher.assemble(actor)['sources'][0]['loaded']
                key=next(key for key,text in port.docs.items() if key[0]==actor and '# 小镇地图' in text)
                assert '矿坑 | 铁匠铺' in port.docs[key]
                port.docs.pop(key) # Simulate a document removed by native compaction.
                assert matcher.assemble(actor)['sources'][0]['loaded']==['world-map']
                assert not matcher.assemble(actor)['sources'][0]['loaded']
                saved=b.modules.unmount(actor+'/context','context.sources')
                assert not matcher.assemble(actor)['sources']
                assert not b.network.nodes[actor].inputs.snapshot()['context-assembly:'+actor+'/context']['tail']
                b.modules.mount(actor+'/context','context.sources',**saved)
                assert 'world/time' not in [e.target_node_id for e in b.network.nodes[actor].read_interfaces]
                assert 'world/time' in [e.target_node_id for e in b.network.nodes[actor+'/context'].read_interfaces]
                port.actions[actor]=(business('forest'),'chop',{})
                app.invoke('root','world_run_npc',dict(target=actor));assert app.state(actor)['prompt']==stable
                app.invoke(actor,'datanet_memory_write',dict(content='记住树林'))
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                assert b.network.nodes[actor].read_memory()['content']=='记住树林'
                assert person(b,actor).state['inventory']['wood']==2
                result=app.invoke('root','world_run_npc',dict(target=actor))
                assert result['pulse']['reports'][0]['returned'] and '第1天-午' in ' '.join(port.tails[0]['texts'])
            finally:stop(app,b)
        """)

if __name__=='__main__':unittest.main()
