"""Explicit context nodes, actual documents, native ports, metadata, and restoration."""
import json,os,subprocess,sys,textwrap,unittest
from pathlib import Path
from test_knowledge_base import AGENT_SETUP
ROOT=Path(__file__).resolve().parents[1]
SETUP=AGENT_SETUP+r"""
from pathlib import Path
from datanet.core.node import Node
from datanet.core.text_node import TextFileNode
from datanet.core.interface import Interface

def connect(b,source,target):b.network.nodes[source].read_interfaces.append(Interface(target,dict(visibility='private',threshold=1)))
def setup(b,port):
    app=Application(b,port,{});app.bind_session('root-session');b.agents['root']={'session_id':'root-session'}
    b.network.add_node(Node('assembly','Context',None));connect(b,'root','assembly')
    return app,app.plugins['capabilities/context_assembly']
def source(id,kind,text,**extra):return dict(id=id,kind=kind,source=dict(type='text',text=text),**extra)
"""
class AssemblyTests(unittest.TestCase):
    def case(self,code,extra=()):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/npc_world'),DATANET_COMPONENT_SELECTION=json.dumps(['capabilities/context_assembly',*extra]),DATANET_COMPONENT_PROFILE='{}')
        p=subprocess.run([sys.executable,'-X','utf8','-c',SETUP+textwrap.dedent(code)],cwd=ROOT,env=env,text=True,encoding='utf-8',capture_output=True,timeout=25)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_default_no_sources_and_direct_four_input_ports(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=Port();app=Application(b,port,{});app.bind_session('root-session')
            try:
                plugin=app.plugins['capabilities/context_assembly'];assert plugin.assemble('root')=={'sources':[]}
                assert not port.docs
                file=Path(folder)/'direct.md';file.write_text('direct input document',encoding='utf-8');ref=dict(file=str(file))
                patch=dict(system_prompt=ref,context=[dict(id='guide',text=ref)],inputs=[dict(id='task',text=ref)],tail=[ref])
                app.update_inputs('root','external',**patch);app.update_inputs('root','external',**patch)
                assert len(port.input_events)==1 and len(port.docs)==1
                assert app.input_tail('root')==['direct input document']
                assert app.view('root')['sections'][0]['text']=='direct input document'
                assert not b.root.inputs.pending()
                b.dispatch('save',{})
            finally:stop(app,b)
            b=Backend(folder);app=Application(b,port,{});app.bind_session('root-session')
            try:
                app.publish_inputs('root');assert len(port.input_events)==1
                assert app.input_tail('root')==['direct input document']
            finally:stop(app,b)
        """)
    def test_documents_and_node_sources_all_four_surfaces(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=Port();app,p=setup(b,port)
            file=Path(folder)/'persona.md';file.write_text('fixed persona',encoding='utf-8')
            clock=b.directory/'clock.md';clock.write_text('day one',encoding='utf-8');b.network.add_node(TextFileNode('time','Clock','text',clock));connect(b,'assembly','time')
            try:
                specs=[dict(id='persona',kind='system_prompt',source=dict(type='file',path=str(file))),source('facts','context','reference facts'),source('task','inputs','one job',event_id='job-1'),dict(id='time',kind='tail',source=dict(type='node',target='time'))]
                p.configure('assembly',specs,document_roots=[folder]);p.bind('root','assembly')
                first=p.assemble('root')['sources'][0];assert first['loaded']==['facts']
                assert any(s['text']=='fixed persona' for s in app.view('root')['sections'])
                assert app.input_tail('root')==['day one'] and len(port.input_events)==1
                count=len(port.docs);assert not p.assemble('root')['sources'][0]['loaded'] and len(port.docs)==count
                before=app.rpc('context_assembly_get',target='root',node_id='assembly')['revision']
                clock.write_text('day two',encoding='utf-8');p.assemble('root')
                assert app.input_tail('root')==['day two'] and len(port.docs)==count
                assert app.rpc('context_assembly_get',target='root',node_id='assembly')['revision']==before
                file.write_text('changed persona',encoding='utf-8');p.assemble('root')
                assert any(s['text']=='changed persona' for s in app.view('root')['sections'])
                assert len(port.input_events)==1
            finally:stop(app,b)
        """)
    def test_core_metadata_and_optional_extension_automatic_compatibility(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=Port();app,p=setup(b,port);extra=app.plugins['capabilities/node_metadata']
            specs=[source('base','context','core rule',when={'node_id':'root'}),source('miner','context','miner rule',when={'/extensions/demo/role':'miner'}),source('smith','context','smith rule',when={'/extensions/demo/role':'smith'})]
            try:
                assert app.catalog['capabilities/context_assembly']['requires']==[]
                assert 'capabilities/signal_response' not in app.enabled
                p.configure('assembly',specs);p.bind('root','assembly')
                assert p.assemble('root')['sources'][0]['matched']==['base']
                extra.set('root','demo',{'role':'miner'});assert p.assemble('root')['sources'][0]['loaded']==['miner']
                extra.set('root','demo',{'role':'smith'});assert p.assemble('root')['sources'][0]['loaded']==['smith']
                current=lambda:app.rpc('context_assembly_get',target='root',node_id='assembly')
                assert current()['removed']==['miner'] and current()['current']['metadata']['extensions']['demo']['role']=='smith'
                app.enabled.remove('capabilities/node_metadata');assert p.assemble('root')['sources'][0]['matched']==['base']
                app.enabled.add('capabilities/node_metadata');assert not p.assemble('root')['sources'][0]['loaded']
                port.docs.clear();assert p.assemble('root')['sources'][0]['loaded']==['base','smith']
                assert not b.network.signal_runs and not hasattr(b.root,'role')
            finally:stop(app,b)
        """,['capabilities/node_metadata'])
    def test_source_permission_is_explicit_not_business_graph_scanning(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=Port();app,p=setup(b,port)
            file=b.directory/'secret.md';file.write_text('not automatically injected',encoding='utf-8');b.network.add_node(TextFileNode('secret','Secret','text',file));connect(b,'root','secret')
            try:
                p.configure('assembly',[source('allowed','context','chosen material')]);p.bind('root','assembly');p.assemble('root')
                assert all('not automatically injected' not in s for s in port.docs.values())
                p.configure('assembly',[dict(id='secret',kind='context',source=dict(type='node',target='secret'))])
                try:p.assemble('root')
                except PermissionError:pass
                else:raise AssertionError('Agent business access was incorrectly used by the assembly node')
                connect(b,'assembly','secret');assert p.assemble('root')['sources'][0]['loaded']==['secret']
                b.root.read_interfaces=[e for e in b.root.read_interfaces if e.target_node_id!='assembly']
                assert p.assemble('root')['sources'][0]['revoked'];assert not app.input_tail('root')
            finally:stop(app,b)
        """)
    def test_file_root_grants_and_partial_document_reload(self):
        self.case("""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=Port();app,p=setup(b,port)
            file=Path(folder)/'guide.md';file.write_text('guide v1',encoding='utf-8')
            specs=[dict(id='guide',kind='context',source=dict(type='file',path=str(file)))]
            try:
                try:p.configure('assembly',specs)
                except PermissionError:pass
                else:raise AssertionError('File read lacked an explicit host root grant')
                p.configure('assembly',specs,document_roots=[folder]);p.bind('root','assembly');assert p.assemble('root')['sources'][0]['loaded']==['guide']
                file.write_text('guide v2',encoding='utf-8');assert p.assemble('root')['sources'][0]['loaded']==['guide']
                assert not p.assemble('root')['sources'][0]['loaded']
                for key in list(port.docs):
                    if 'guide v2' in port.docs[key]:del port.docs[key]
                assert p.assemble('root')['sources'][0]['loaded']==['guide']
                b.dispatch('save',{})
            finally:stop(app,b)
            b=Backend(folder);port=Port();app=Application(b,port,{});app.bind_session('root-session')
            try:assert app.plugins['capabilities/context_assembly'].assemble('root')['sources'][0]['loaded']==['guide']
            finally:stop(app,b)
        """)
if __name__=='__main__':unittest.main()
