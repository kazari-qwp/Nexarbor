"""World tests use actual graph tools and checkpoints; no paid full-world simulation."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from test_knowledge_base import AGENT_SETUP
ROOT=Path(__file__).resolve().parents[1]
SETUP=AGENT_SETUP+r"""
from datanet.world.state import state,address,business
from datanet.core.access_budget import active_agent
from datanet.rounds import barrier
class WorldPort(Port):
    def __call__(self,name,p):
        if name in ('conclude','cancel-agent'):return {}
        return super().__call__(name,p)
def tool(app,actor,target,name,**args):
    app.invoke(actor,'node_tools',dict(target=target,direction='write'))
    return app.invoke(actor,'node_invoke',dict(target=target,tool=name,direction='write',arguments=args))
def finish(app,b):
    for actor in barrier.pending(state(b)['barrier']):app.invoke(actor,'world_submit',{})
    return app.invoke('root','world_round',dict(action='settle'))
def begin(app):return app.invoke('root','world_round',dict(action='begin'))
def move(app,actor,destination):return tool(app,actor,address(destination),'move_here')
"""
class WorldTests(unittest.TestCase):
    def case(self,code):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/npc_world'),DATANET_COMPONENT_PROFILE='{}')
        env.pop('DATANET_COMPONENT_SELECTION',None)
        result=subprocess.run([sys.executable,'-X','utf8','-c',SETUP+textwrap.dedent(code)],cwd=ROOT,env=env,text=True,encoding='utf-8',capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_graph_authority_privacy_and_movement_restore(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'))
            try:
                app.bind_session('root-session');miner='world/npc/miner';lin='world/npc/lin';yue='world/npc/yue'
                assert len(app.states)==7 and not port.runs
                assert set(port.tools[miner])=={'world_look','world_messages','world_submit','node_read','node_list','node_tools','node_invoke','datanet_memory_read','datanet_memory_write'}
                reachable={n.node_id for n,_ in b.network.walk(miner,strength=2)}
                assert business('mine') in reachable and address('smithy') in reachable
                assert business('smithy') not in reachable and 'world/npc/smith' not in reachable and address('tavern') not in reachable
                forbidden=[business('smithy'),'world/npc/smith',address('tavern')]
                for target in forbidden:
                    try:app.invoke(miner,'node_tools',dict(target=target,direction='write'))
                    except RuntimeError as error:assert 'forbidden' in str(error)
                    else:raise AssertionError('Out-of-range tool discovery accepted')
                text=app.invoke(miner,'node_read',dict(target='world/common',request=dict(method='key',key='content')))
                assert '10个时刻' in text['items'][0]['content']
                for target,toolname,args in [('world/common','write',dict(key='content',value='hack')), (yue,'memory_read',{})]:
                    try:tool(app,lin,target,toolname,**args)
                    except (PermissionError,RuntimeError,ValueError):pass
                    else:raise AssertionError('Private write/read leaked')
                assert active_agent.get() is None
                begin(app)
                app.invoke(lin,'node_tools',dict(target=yue,direction='write'))
                try:app.invoke(lin,'node_invoke',dict(target=yue,tool='talk',direction='write',arguments=dict(content='伪造身份',actor=yue)))
                except (TypeError,ValueError):pass
                else:raise AssertionError('Actor spoof accepted')
                try:b.network.nodes[business('mine')].invoke_tool('mine')
                except PermissionError:pass
                else:raise AssertionError('Unauthenticated public tool accepted')
                tool(app,lin,yue,'talk',content='明天商量婚礼。')
                assert app.invoke(yue,'world_messages',{})['items'][0]['content']=='明天商量婚礼。'
                assert not app.invoke(yue,'world_messages',{})['items']
                move(app,miner,'smithy')
                assert state(b)['actors'][miner]['place']=='mine'
                receipt=app.invoke(miner,'world_submit',{});assert app.invoke(miner,'world_submit',{})==receipt
                try:move(app,miner,'smithy')
                except ValueError:pass
                else:raise AssertionError('Changed submitted action')
                try:app.invoke('root','world_round',dict(action='settle'))
                except ValueError:pass
                else:raise AssertionError('Bypassed barrier')
                app.invoke(miner,'datanet_memory_write',dict(content='我的私人经历'))
                finish(app,b);assert state(b)['actors'][miner]['place']=='smithy'
                assert business('smithy') in {n.node_id for n,_ in b.network.walk(miner,strength=2)}
                assert business('mine') not in {n.node_id for n,_ in b.network.walk(miner,strength=2)}
                assert active_agent.get() is None
            finally:b.close()
            b=Backend(folder);app=Application(b,WorldPort(),dict(rootNetwork='small_town'))
            try:
                app.bind_session('root-session');assert state(b)['tick']==1
                assert b.network.nodes[miner].read_memory()['content']=='我的私人经历'
                begin(app);tool(app,miner,business('smithy'),'repair',item='pickaxe');finish(app,b)
                assert state(b)['actors'][miner]['inventory']['pickaxe']==5
                assert state(b)['actors'][miner]['coins']==6
            finally:b.close()
        """)

    def test_family_due_hospital_child_next_round_idempotent(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,WorldPort(),dict(rootNetwork='small_town'));app.bind_session('root-session')
            lin,yue='world/npc/lin','world/npc/yue'
            try:
                # Reach the registry using real adjacent movement tools.
                for destination in ['tavern','civil_registry']:
                    begin(app);move(app,lin,destination);move(app,yue,destination);finish(app,b)
                begin(app);tool(app,lin,business('civil_registry'),'marry',partner=yue);finish(app,b)
                assert state(b)['actors'][lin]['spouse'] is None
                begin(app);tool(app,lin,business('civil_registry'),'marry',partner=yue);tool(app,yue,business('civil_registry'),'marry',partner=lin);finish(app,b)
                assert state(b)['actors'][lin]['spouse']==yue
                for destination in ['tavern','home1']:
                    begin(app);move(app,lin,destination);move(app,yue,destination);finish(app,b)
                begin(app);tool(app,lin,business('home1'),'plan_family',partner=yue);tool(app,yue,business('home1'),'plan_family',partner=lin)
                created_tick=state(b)['tick'];finish(app,b)
                pregnancy=next(iter(state(b)['pregnancies'].values()));assert pregnancy['due_tick']==created_tick+10
                begin(app);move(app,yue,'hospital');finish(app,b)
                begin(app);tool(app,yue,business('hospital'),'birth');finish(app,b)
                assert len(state(b)['actors'])==6 and not state(b)['results'][yue]['ok']
                while state(b)['tick']<created_tick+10:begin(app);finish(app,b)
                begin(app);tool(app,yue,business('hospital'),'birth');result=finish(app,b)
                child=result['newborns'][0];assert child not in state(b)['barrier']['participants']
                assert child in app.states and len(state(b)['actors'])==7
                assert state(b)['actors'][child]['parents']==sorted([lin,yue])
                assert '私人经历' not in b.network.nodes[child].read_memory()['content']
                assert app.invoke('root','world_round',dict(action='settle'))==result
                begin(app);assert child in state(b)['barrier']['participants']
                finish(app,b);assert len(state(b)['actors'])==7
            finally:b.close()
            b=Backend(folder);app=Application(b,WorldPort(),dict(rootNetwork='small_town'))
            try:
                app.bind_session('root-session');assert child in app.states
                assert b.network.nodes[child].expose==['talk','give']
                begin(app)
                try:tool(app,child,business('hospital'),'birth')
                except PermissionError:pass
                else:raise AssertionError('Child allowed adult service')
                finish(app,b);assert len(state(b)['actors'])==7
            finally:b.close()
        """)

    def test_parallel_runs_budgets_failure_and_expiration(self):
        self.case("""
        import time,threading
        class ParallelPort(WorldPort):
            def __init__(self):super().__init__();self.live=0;self.peak=0;self.lock=threading.Lock()
            def __call__(self,name,p):
                if name=='cancel-agent' and p['actor'].endswith('/miner'):raise RuntimeError('already disconnected')
                if name=='run':
                    actor=p['actor']
                    with self.lock:self.live+=1;self.peak=max(self.peak,self.live)
                    try:
                        time.sleep(.08)
                        app.event(actor,'agent/pre-step',{});app.event(actor,'agent/request',{})
                        if actor.endswith('/miner'):raise RuntimeError('simulated model failure')
                        app.invoke(actor,'world_submit',{})
                        return dict(session_id=self.agents[actor]['session_id'],messages=[])
                    finally:
                        with self.lock:self.live-=1
                result=super().__call__(name,p)
                if name=='create':self.agents[p['actor']]['session_id']=p['binding']['session_id']
                return result
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=ParallelPort();app=Application(b,port,dict(rootNetwork='small_town',worldMaxRequests=2));app.bind_session('root-session')
            try:
                result=app.invoke('root','world_round',dict(action='run'))
                assert port.peak>1 and state(b)['tick']==1
                assert result['settlement']['unavailable']==['world/npc/miner']
                begin(app);state(b)['barrier']['deadline']=time.time()-1
                app.invoke('root','world_round',dict(action='settle'));assert state(b)['tick']==2
                begin(app)
                plugin=app.plugins['capabilities/world_runtime'];actor='world/npc/miner'
                plugin.turns[actor]=dict(active=True,tick=2,count=2,limit=2)
                try:app.event(actor,'agent/request',{})
                except RuntimeError:pass
                else:raise AssertionError('Request budget bypassed')
                app.invoke('root','world_round',dict(action='cancel'))
            finally:b.close()
        """)

    def test_production_trade_atomic_failure_and_checkpoint_mid_round(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,WorldPort(),dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/woodcutter'
            begin(app);tool(app,actor,business('forest'),'chop');app.invoke(actor,'world_submit',{});b.close()
            b=Backend(folder);app=Application(b,WorldPort(),dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                assert actor in state(b)['barrier']['submitted'];finish(app,b)
                assert state(b)['actors'][actor]['inventory']['wood']==2
                begin(app);move(app,actor,'shop');finish(app,b)
                begin(app);tool(app,actor,business('shop'),'trade',side='sell',item='wood',quantity=2);finish(app,b)
                assert state(b)['actors'][actor]['coins']==10
                begin(app);tool(app,actor,business('shop'),'trade',side='buy',item='ore',quantity=10)
                before=state(b)['actors'][actor]['coins'];stock=state(b)['shop']['ore']['stock'];finish(app,b)
                assert not state(b)['results'][actor]['ok']
                assert state(b)['actors'][actor]['coins']==before and state(b)['shop']['ore']['stock']==stock
            finally:b.close()
        """)

if __name__=='__main__':unittest.main()
