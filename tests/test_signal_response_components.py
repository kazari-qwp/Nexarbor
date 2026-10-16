"""Shared response workflows and prompt matching without an NPC application."""
import os,subprocess,sys,textwrap,unittest
from pathlib import Path
from test_knowledge_base import AGENT_SETUP
ROOT=Path(__file__).resolve().parents[1]
SETUP=AGENT_SETUP+r"""
import asyncio
from pathlib import Path
from datanet.core.node import Node,NodeResult
from datanet.core.interface import Interface
from datanet.core.signals import Signal

def add(b,*nodes):
    for node in nodes:b.network.add_node(Node(node,node,None))
def link(b,source,target,channels=('tick',)):
    b.network.nodes[source].write_interfaces.append(Interface(target,{'channels':list(channels),'threshold':1}))
def rule(id,channels,*steps):return dict(id=id,channels=channels,steps=[dict(tool=name,arguments=args) for name,args in steps])
"""
class ComponentTests(unittest.TestCase):
    def case(self,code,component='signal_response'):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/npc_world'),DATANET_COMPONENT_SELECTION='["capabilities/'+component+'"]',DATANET_COMPONENT_PROFILE='{}')
        result=subprocess.run([sys.executable,'-X','utf8','-c',SETUP+textwrap.dedent(code)],cwd=ROOT,env=env,text=True,encoding='utf-8',capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_channels_order_references_and_parallel_layer_barrier(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});p=app.plugins['capabilities/signal_response']
            add(b,'a','b','sink');link(b,'root','a');link(b,'root','b');link(b,'a','sink',['other']);link(b,'b','sink',['other'])
            async def run():
                started=set();both=asyncio.Event();events=[]
                async def first(c,n):
                    node=c.delivery.node_id;started.add(node)
                    if len(started)==2:both.set()
                    await asyncio.wait_for(both.wait(),1)
                    if node=='a':await asyncio.sleep(.02)
                    events.append(node+'.first');return dict(n=n+1)
                async def second(c,n):assert n==42;events.append('a.second');return n
                async def third(c):assert 'a.second' in events;events.append('a.third')
                async def sink(c):assert set(events)=={'a.first','b.first','a.second','a.third'};return True
                async def forbidden(c):raise AssertionError('Unmatched responder executed')
                p.bind('a',[rule('ignored',['unused'],('forbidden',{})),rule('main',['tick'],('first',{'n':{'$ref':'/signal/content/n'}}),('second',{'n':{'$ref':'/steps/0/value/n'}})),rule('later',['other'],('third',{}))],dict(first=first,second=second,third=third,forbidden=forbidden))
                p.bind('b',[rule('work',['tick'],('first',{'n':41}))],dict(first=first))
                p.bind('sink',[rule('finish',['other'],('sink',{}))],dict(sink=sink))
                report=await b.signals.propagate(Signal('root',['tick','other'],3,content={'n':41}))
                assert report['status']=='completed' and report['layers']==[['a','b'],['sink']]
                assert report['deliveries'][0]['value']['matched']==2
                assert b.snapshot()['signal_response']['a'][1]['steps'][0]['tool']=='first'
                await b.signals.close()
            try:asyncio.run(run())
            finally:stop(app,b)
        """)

    def test_tool_grants_failure_stop_and_no_match_relay(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});p=app.plugins['capabilities/signal_response']
            add(b,'bad','relay','sink','blocked');link(b,'root','bad');link(b,'root','relay');link(b,'bad','blocked');link(b,'relay','sink')
            async def run():
                calls=[]
                async def first(c):calls.append('effect');return NodeResult(items=[{'result':'done'}])
                async def fail(c):return NodeResult(status='error',errors=['expected failure'])
                async def forbidden(c):raise AssertionError('must not execute')
                async def sink(c):calls.append('sink')
                try:p.bind('bad',[rule('bad',['tick'],('unknown',{}))],{})
                except PermissionError:pass
                else:raise AssertionError('Tool grant bypassed')
                p.bind('bad',[rule('bad',['tick'],('first',{}),('fail',{}),('forbidden',{}))],dict(first=first,fail=fail,forbidden=forbidden))
                p.bind('relay',[rule('other',['other'],('forbidden',{}))],dict(forbidden=forbidden))
                p.bind('sink',[rule('finish',['tick'],('sink',{}))],dict(sink=sink))
                signal=Signal('root',['tick'],3,failure_policy='continue');report=await b.signals.propagate(signal)
                assert report['status']=='partial' and calls==['effect','sink']
                assert 'blocked' not in [d['node_id'] for d in report['deliveries']]
                assert next(d for d in report['deliveries'] if d['node_id']=='relay')['value']['matched']==0
                assert 'step 2' in report['deliveries'][0]['error']
                await b.signals.propagate(signal);assert calls==['effect','sink']
                await b.signals.close()
            try:asyncio.run(run())
            finally:stop(app,b)
        """)

    def test_timed_out_sync_tool_blocks_reentry_until_it_stops(self):
        self.case("""
        import threading
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});p=app.plugins['capabilities/signal_response'];add(b,'a');link(b,'root','a')
            async def run():
                release=threading.Event();calls=[]
                def work(c):calls.append(1);release.wait(1);return True
                p.bind('a',[rule('work',['tick'],('work',{}))],dict(work=work))
                try:
                    report=await b.signals.propagate(Signal('root',['tick'],2,node_timeout_seconds=.02));assert report['status']=='timed_out'
                    report=await b.signals.propagate(Signal('root',['tick'],2));assert report['status']=='failed' and calls==[1]
                finally:
                    release.set();await asyncio.gather(*p.workers.values(),return_exceptions=True)
                report=await b.signals.propagate(Signal('root',['tick'],2));assert report['status']=='completed' and len(calls)==2
                await b.signals.close()
            try:asyncio.run(run())
            finally:stop(app,b)
        """)

    def test_prompt_matching_works_with_non_npc_metadata_and_without_signals(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=Port();app=Application(b,port,{});app.bind_session('root-session');b.agents['root']={'session_id':'root-session'}
            p=app.plugins['capabilities/prompt_matching'];b.root.name='finance'
            docs=[dict(id='policy',name='部门规范',when={'name':['finance','legal']},delivery='instructions',text='按所在部门处理资料。')]
            p.bind('root',scope='company',documents=lambda:docs)
            try:
                assert p.tool_match_prompts('root',{})['scopes'][0]['loaded']==['policy']
                first=len(port.docs);assert not p.match('root')['scopes'][0]['loaded'] and len(port.docs)==first
                b.root.name='other';assert not p.match('root')['scopes'][0]['matched']
                b.root.name='finance';assert not p.match('root')['scopes'][0]['loaded']
                assert app.rpc('prompt_matching_get',actor='root',scope='company')['revision']==3
                port.docs.clear();assert p.match('root')['scopes'][0]['loaded']==['policy']
                assert not b.network.signal_runs and not hasattr(b.root,'department')
            finally:stop(app,b)
        """,'prompt_matching')


    def test_node_metadata_extends_plain_text_and_agent_nodes_and_restores(self):
        self.case("""
        from datanet.core.text_node import TextFileNode
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});p=app.plugins['capabilities/node_metadata']
            add(b,'plain');b.network.add_node(TextFileNode('text','Text','text',b.directory/'text.md'))
            try:
                for target in ['root','plain','text']:
                    p.set(target,'demo',{'label':'额外字段','score':2})
                    assert b.network.get_metadata(target)['extensions']['demo']['score']==2
                    assert not hasattr(b.network.nodes[target],'score')
                p.register('computed',lambda target:dict(display_name=b.network.nodes[target].name))
                assert b.network.get_metadata('plain')['extensions']['computed']=={'display_name':'plain'}
                try:p.set('plain','computed',{'display_name':'override'})
                except ValueError:pass
                else:raise AssertionError('Provider-owned field overwritten')
                try:p.set('plain','core',{'name':'override'})
                except ValueError:pass
                else:raise AssertionError('Core namespace overwritten')
                snap=b.network.get_metadata('plain');assert snap['name']=='plain' and snap['extensions']['demo']['score']==2
            finally:stop(app,b)
            b=Backend(folder)
            assert b.network.get_metadata('plain')['extensions']['demo']['score']==2
            app=Application(b,Port(),{})
            try:assert b.network.get_metadata('plain')['extensions']['demo']['score']==2
            finally:stop(app,b)
        """,'node_metadata')


    def test_metadata_is_automatic_for_describe_and_respects_namespace_visibility(self):
        self.case("""
        from datanet.core.access_budget import active_agent
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});p=app.plugins['capabilities/node_metadata'];add(b,'plain','observer')
            try:
                p.set('plain','private',{'secret':'own knowledge'})
                p.register('public',lambda target:dict(weather='sunny'),public=True)
                assert b.network.nodes['plain'].describe(include_schema=False)['extensions']['private']['secret']=='own knowledge'
                token=active_agent.set((SimpleNamespace(max_signal_strength=2),'observer'))
                try:
                    result=b.network.nodes['plain'].get_metadata()
                    assert 'private' not in result['extensions'] and result['extensions']['public']['weather']=='sunny'
                finally:active_agent.reset(token)
                saved=b.snapshot();b.restore(saved)
                assert b.network.get_metadata('plain')['extensions']['private']['secret']=='own knowledge'
                app.enabled.remove('capabilities/node_metadata')
                assert 'extensions' not in b.network.get_metadata('plain')
            finally:stop(app,b)
        """,'node_metadata')

if __name__=='__main__':unittest.main()
