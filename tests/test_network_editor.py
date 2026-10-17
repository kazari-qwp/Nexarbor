"""Editor acceptance: configured composition, actual permissions and persistence."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT=Path(__file__).resolve().parents[1]
SETUP='''
import tempfile,json,time
from pathlib import Path
tempfile.tempdir=str(Path.cwd()/'build/editor-test-temp')
Path(tempfile.tempdir).mkdir(parents=True,exist_ok=True)
from copy import deepcopy
from datanet.core.backend import Backend
from datanet.core.application import Application
from datanet.editor.runtime import ValidationPort
from datanet.editor.documents import preset,template,link
def setup(folder):
    b=Backend(folder);app=Application(b,ValidationPort(),{'allowedAgentToolboxes':['world_resident']});app.bind_session('editor-root');b.modules.bind(app)
    return b,app,app.plugins['capabilities/network_editor']
def empty(editor):return editor.host_request('template',dict(kind='empty',document=editor.current()['document']))
def compose(editor):
    d=template(editor.r.catalog,empty(editor),'infrastructure',{})
    d=template(editor.r.catalog,d,'place',dict(id='woods',name='小树林',kind='forest'))
    d=template(editor.r.catalog,d,'place',dict(id='shop',name='商店',kind='shop'))
    link(d,'world/place/woods','world/place/shop',reciprocal=True)
    for slug,name in [('alice','阿青'),('bob','阿白')]:
        d=template(editor.r.catalog,d,'resident',dict(id=slug,name=name,role='woodcutter',gender='unspecified',place='world/place/woods',coins=10,personality='安静而好奇。',motivation='想赚一点金币。'))
    return d
'''

class EditorTests(unittest.TestCase):
    def case(self,code):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/editor'),DATANET_COMPONENT_PROFILE='{}')
        env.pop('DATANET_COMPONENT_SELECTION',None)
        p=subprocess.run([sys.executable,'-X','utf8','-c',SETUP+textwrap.dedent(code)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_full_preset_and_empty_to_two_place_two_npc_validation(self):
        self.case('''
        with tempfile.TemporaryDirectory() as folder:
            b,app,e=setup(folder)
            try:
                full=preset(app.catalog,'network_presets/small_town')
                result=e.validate(full);assert result['valid'],result
                d=compose(e);result=e.validate(d);assert result['valid'],result
                assert len([n for n in d['network']['nodes'] if 'world.resident' in n['modules']])==2
                assert 'world/place/woods' in json.dumps(d)
                assert set(b.network.nodes)=={'root'} and not b.agents.get('world/npc/alice')
            finally:b.close()
        ''')

    def test_pending_native_input_blocks_structure_edits(self):
        self.case('''
        class PendingPort(ValidationPort):
            def __call__(self,op,p):
                if op=='inspect':return dict(status='idle',pending_messages=1)
                return super().__call__(op,p)
        with tempfile.TemporaryDirectory() as folder:
            b,app,e=setup(folder)
            try:
                app.port=PendingPort();before=e.current()['commit']
                try:e.apply(dict(document=compose(e),base_commit=before))
                except RuntimeError as error:assert 'root' in str(error)
                else:raise AssertionError('queued native input was treated as idle')
                assert set(b.network.nodes)=={'root'} and e.current()['commit']==before
            finally:b.close()
        ''')

    def test_real_access_and_apply_preserves_same_native_identity(self):
        self.case('''
        with tempfile.TemporaryDirectory() as folder:
            b,app,e=setup(folder)
            try:
                d=compose(e)
                result=e.apply(dict(document=d,base_commit=e.current()['commit']));assert result.get('applied'),result
                old=b.agents['world/npc/alice']['session_id']
                view=e.view(dict(actor='world/npc/alice',strength=2))
                read={x['id'] for x in [item for group in view['paths'].values() for item in group if 'access.read' in item['channels']]}
                assert 'world/place/shop' in read and 'world/service/shop' not in read
                assert 'world/npc/bob' in read
                assert any(t['name']=='datanet_memory_read' for t in view['tools'])
                live=e.current();next=deepcopy(live['document'])
                next['network']['nodes'][0]['name']='新根名称'
                result=e.apply(dict(document=next,base_commit=live['commit']));assert result.get('applied'),result
                assert b.agents['world/npc/alice']['session_id']==old
            finally:b.close()
        ''')

    def test_draft_cas_paths_and_stale_live_revision(self):
        self.case('''
        with tempfile.TemporaryDirectory() as folder:
            b,app,e=setup(folder)
            try:
                d=compose(e);commit=e.current()['commit']
                saved=e.save_draft(dict(document=d,expected_version=0,base_commit=commit,layout={'root':{'x':1,'y':2}}))
                assert saved['version']==1
                try:e.save_draft(dict(document=d,expected_version=0))
                except ValueError:pass
                else:raise AssertionError('stale draft accepted')
                for path in ['../outside','C:/private.txt','safe/../../outside']:
                    bad=deepcopy(d);bad['files'][path]='x';assert not e.validate(bad)['valid']
                bad=deepcopy(d);bad['network']['nodes'][0]['parameters']['file_path']='../outside';assert not e.validate(bad)['valid']
                b.dispatch('save',{})
                # A save without a data change may reuse the previous core commit.
                b.network.nodes['root'].name='changed';b.dispatch('save',{})
                try:e.apply(dict(document=d,base_commit=commit))
                except ValueError:pass
                else:raise AssertionError('stale live revision accepted')
            finally:b.close()
            b,app,e=setup(folder)
            try:assert e.draft['version']==1 and e.draft['layout']['root']['x']==1
            finally:b.close()
        ''')

    def test_missing_reference_and_invalid_event_graph_fail_before_apply(self):
        self.case('''
        with tempfile.TemporaryDirectory() as folder:
            b,app,e=setup(folder)
            try:
                d=compose(e);bad=deepcopy(d)
                n=next(n for n in bad['network']['nodes'] if n['node_id']=='world/npc/alice')
                n['modules']['agent.session']['config']['manager']='missing'
                assert not e.validate(bad)['valid']
                bad=deepcopy(d);n=next(n for n in bad['network']['nodes'] if n['node_id']=='world/npc/alice')
                n['modules']['event.trigger']['config']['graphs']['refresh']={'type':'call','id':'x','operation':'nonexistent','arguments':{}}
                assert not e.validate(bad)['valid']
                assert set(b.network.nodes)=={'root'}
            finally:b.close()
        ''')

    def test_pulse_parallel_work_movement_budget_talk_and_cold_restore(self):
        self.case('''
        from datanet.world.model import instance
        from threading import Barrier,Lock,Event
        class Port(ValidationPort):
            barrier=Barrier(2);calls=[];guard=Lock();talked=Event()
            def __call__(self,op,p):
                if op=='run':
                    actor=p['actor'];self.barrier.wait(timeout=10)
                    app.event(actor,'agent/pre-step',{});app.event(actor,'agent/request',{})
                    assembly=instance(b,actor,'tools.assembly');assembly.assemble()
                    def use(tool,args={}):
                        key=next(k for k,v in assembly.aliases.items() if v['tool']==tool)
                        return app.invoke(actor,key,args)
                    if actor.endswith('alice'):
                        use('chop')
                        self.talked.wait(timeout=10)
                        use('move_here')
                    else:
                        key=next(k for k,v in assembly.aliases.items() if v['target']=='world/npc/alice' and v['tool']=='talk')
                        app.invoke(actor,key,{'content':'你好。'})
                        self.talked.set()
                    with self.guard:self.calls.append(actor)
                    return dict(session_id=b.agents[actor]['session_id'],messages=[dict(role='assistant',content='本次活动结束。')],completion='completed')
                return super().__call__(op,p)
        with tempfile.TemporaryDirectory() as folder:
            b,app,e=setup(folder);app.port=Port()
            try:
                result=e.apply(dict(document=compose(e),base_commit=e.current()['commit']));assert result.get('applied'),result
                e.start(dict(pulse='world/pulse',cycles=1,timeout=30));e.job_thread.join(timeout=40)
                assert e.job['status']=='completed',e.job
                assert len(app.port.calls)==2,e.job
                assert e.job['reports'][0]['reports'][0]['returned']
                a=instance(b,'world/npc/alice','world.resident').state
                assert a['place']=='world/place/shop' and a['inventory']['wood']==2,a
                assert instance(b,'world/npc/alice','action.budget').state['spent']==9
                assert instance(b,'world/npc/bob','action.budget').state['spent']==1
                assert b.store.stats()['commit_id']>1
            finally:b.close()
            b,app,e=setup(folder)
            try:
                assert instance(b,'world/npc/alice','world.resident').state['place']=='world/place/shop'
                assert instance(b,'world/npc/alice','action.budget').state['spent']==9
                assert len(b.network.nodes)>10
            finally:b.close()
        ''')

if __name__=='__main__':unittest.main()
