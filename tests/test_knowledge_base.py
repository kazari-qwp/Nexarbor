"""Knowledge records, recovery, bounded agents and reuse across application recipes."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT=Path(__file__).resolve().parents[1]


class KnowledgeBaseTests(unittest.TestCase):
    def run_case(self,code,application='knowledge_base'):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',
                 DATANET_COMPONENT_ROOT=str(ROOT/'extensions'/application),DATANET_COMPONENT_PROFILE='{}')
        env.pop('DATANET_COMPONENT_SELECTION',None)
        value=subprocess.run([sys.executable,'-X','utf8','-c',textwrap.dedent(code)],env=env,cwd=ROOT,text=True,encoding='utf-8',capture_output=True,timeout=60)
        self.assertEqual(value.returncode,0,value.stdout+value.stderr)

    def test_four_storage_types_roundtrip_and_node_restore(self):
        self.run_case('''
            import tempfile,json
            from datanet.core.backend import Backend
            with tempfile.TemporaryDirectory() as folder:
                b=Backend(folder);s=b.knowledge
                for kind,value,schema in [('csv',{'name':'001','n':2},{'name':'string','n':'integer'}),('sqlite',{'name':'中文','n':3},{'name':'string','n':'integer'}),('rag','长文档：网络节点支持检索和持久化。',{}),('wiki','知识页面：稳定标识引用。',{})]:
                    c=b.dispatch('knowledge_create_collection',dict(name=kind,storage=kind,schema=schema))
                    r=b.dispatch('knowledge_store',dict(collection=c['id'],value=value,key='item'))
                    assert s.fetch(r['id'])['content']==value
                    assert c['node_id'] in b.network.nodes
                    assert len(s.search(collection=c['id'])['items'])==1
                    if kind=='rag':assert r['index']['reason']=='embedding_not_configured'
                ids=list(b.network.nodes);b.close();b=Backend(folder)
                assert set(ids)==set(b.network.nodes)
                assert len(b.knowledge.catalog())==4
                assert b.network.nodes[c['node_id']].read(dict(method='key',key='item')).items[0]['content']==value
                b.close()
        ''')

    def test_versions_dedup_stale_wiki_and_deletion(self):
        self.run_case('''
            import tempfile,json
            from datanet.knowledge.store import KnowledgeStore
            with tempfile.TemporaryDirectory() as folder:
                s=KnowledgeStore(folder);c=s.create_collection('资料','rag');w=s.create_collection('记忆','wiki')
                a=s.store(c['id'],'初始资料',key='source');same=s.store(c['id'],'初始资料',key='source')
                assert same['unchanged'] and same['version']==1
                page=s.store(w['id'],'基于资料的整理',key='page',sources=[a['id']])
                updated=s.update(a['id'],'更新资料',expected_version=1)
                assert updated['version']==2 and s.fetch(a['id'],1)['content']=='初始资料'
                assert s.fetch(page['id'])['needs_refresh']
                try:s.update(a['id'],'过期写入',expected_version=1)
                except ValueError:pass
                else:raise AssertionError('stale update accepted')
                s.delete(a['id'],expected_version=2)
                assert not s.search('更新资料')['items']
                try:s.fetch(a['id'])
                except KeyError:pass
                else:raise AssertionError('deleted record readable as current')
                assert s.fetch(a['id'],2)['content']=='更新资料'
                assert json.loads(s.export(c['id'])['content'])==[]
        ''')

    def test_batch_csv_sqlite_filter_pagination_and_routing(self):
        self.run_case('''
            import tempfile,json
            from datanet.knowledge.store import KnowledgeStore
            with tempfile.TemporaryDirectory() as folder:
                s=KnowledgeStore(folder)
                for kind in ['csv','sqlite']:
                    c=s.create_collection(kind,kind,schema={'name':'string','n':'integer'})
                    intake=s.stage([{'name':str(i).zfill(4),'n':i} for i in range(150)],purpose=kind)
                    result=s.commit_intake(intake['id'],c['id'])
                    assert len(result['records'])==150
                    assert s.commit_intake(intake['id'],c['id'])==result
                    hit=s.search(collection=c['id'],filters={'name':'0042'})
                    assert hit['total']==1 and s.fetch(hit['items'][0]['id'])['content']['n']==42
                    page=s.search(collection=c['id'],limit=11,offset=11)
                    assert len(page['items'])==11 and page['total']==150 and page['next_offset']==22
                    assert s.route(s.stage([{'name':'next','n':151}],purpose=kind)['id'])['collection']==c['id']
                    assert s.export(c['id'],'csv')['count']==150
        ''')

    def test_interrupted_materialization_recovers(self):
        self.run_case('''
            import tempfile
            from datanet.knowledge.store import KnowledgeStore
            with tempfile.TemporaryDirectory() as folder:
                s=KnowledgeStore(folder);c=s.create_collection('恢复','wiki')
                original=s._materialize
                s._materialize=lambda id: (_ for _ in ()).throw(OSError('simulated interruption'))
                try:s.store(c['id'],'中断前的原文',key='recover')
                except OSError:pass
                else:raise AssertionError('failure hidden')
                restored=KnowledgeStore(folder)
                hit=restored.search('中断前')['items'][0]
                assert restored.fetch(hit['id'])['content']=='中断前的原文'
                assert restored.fetch(hit['id'])['state']=='ready'
        ''')

    def test_mixed_batch_original_sources_and_database_aggregation(self):
        self.run_case('''
            import tempfile,json
            from pathlib import Path
            from datanet.knowledge.store import KnowledgeStore
            with tempfile.TemporaryDirectory() as folder:
                s=KnowledgeStore(folder)
                table=s.create_collection('账目','sqlite',schema={'category':'string','amount':'number'})
                wiki=s.create_collection('知识','wiki')
                raw=Path(folder)/'input.json';raw.write_text('["原始文件"]',encoding='utf-8')
                intake=s.stage([{'category':'a','amount':2.5},'知识说明',{'category':'a','amount':3.5}],original_file=raw)
                first=s.commit_intake(intake['id'],table['id'],indices=[0,2])
                assert first['status']=='partial' and first['remaining_indices']==[1]
                assert s.intake(intake['id'])['original_source']['name']=='input.json'
                final=s.commit_intake(intake['id'],wiki['id'],indices=[1])
                assert final['status']=='stored' and len(final['records'])==3
                rows=s.query(table['id'],aggregate={'function':'sum','field':'amount'},group_by=['category'])['items']
                assert rows==[{'category':'a','value':6.0}],rows
                id=first['records'][0]['id'];s.delete(id,expected_version=1)
                assert s.query(table['id'],aggregate={'function':'count'})['items'][0]['value']==1
                try:s.query(table['id'],fields=['amount); DROP TABLE records;--'])
                except ValueError:pass
                else:raise AssertionError('unbound SQL identifier allowed')
        ''')

    def test_duplicate_intakes_do_not_inflate_versions(self):
        self.run_case('''
            import tempfile
            from datanet.knowledge.store import KnowledgeStore
            with tempfile.TemporaryDirectory() as folder:
                s=KnowledgeStore(folder);c=s.create_collection('记忆','wiki')
                a=s.commit_intake(s.stage('同一份内容')['id'],c['id'])
                b=s.commit_intake(s.stage('同一份内容')['id'],c['id'])
                assert a['records'][0]['id']==b['records'][0]['id']
                assert b['records'][0]['version']==1
        ''')

    def test_mkdocs_wiki_export_uses_upstream_search(self):
        self.run_case('''
            import tempfile,json
            from pathlib import Path
            from datanet.knowledge.store import KnowledgeStore
            with tempfile.TemporaryDirectory() as folder:
                s=KnowledgeStore(folder);c=s.create_collection('知识Wiki','wiki')
                a=s.store(c['id'],'# 项目概况\\n项目采用组件式网络。',key='overview')
                b=s.store(c['id'],'# 使用方法\\n阅读[项目概况]('+a['id']+'.md)。',key='usage',sources=[a['id']])
                result=s.export(c['id'],'wiki')
                assert result['engine']=='mkdocs' and result['pages']==2
                assert Path(result['index_path']).is_file()
                index=Path(result['site_directory'])/'search/search_index.json'
                assert index.is_file() and '项目概况' in json.dumps(json.loads(index.read_text(encoding='utf-8')),ensure_ascii=False)
                assert Path(result['source_directory'],b['id']+'.md').is_file()
        ''')

    def test_single_main_and_direct_routing(self):
        self.run_case(AGENT_CASE)

    def test_import_paths_are_relative_to_workspace_and_cannot_escape(self):
        setup=AGENT_SETUP
        self.run_case(setup+'''
from pathlib import Path
with tempfile.TemporaryDirectory() as folder:
    workspace=Path(folder)/'workspace';workspace.mkdir()
    imports=workspace/'imports';imports.mkdir()
    source=imports/'people.csv'
    source.write_text('code,age\\n001,30\\n',encoding='utf-8-sig')
    backend=Backend(Path(folder)/'state');port=Port()
    app=Application(backend,port,dict(rootNetwork='knowledge_base',workspace=str(workspace)))
    app.bind_session('file-import-root')
    collection=app.invoke('root','kb_create_node',dict(name='CSV import',storage='sqlite',schema={'code':'string','age':'integer'}))
    try:
        result=app.invoke('root','kb_ingest',dict(file_path='imports/people.csv',collection=collection['id']))
        record=app.invoke('root','kb_fetch',dict(id=result['records'][0]['id']))
        assert record['content']=={'code':'001','age':30},record
        assert not port.runs,'Explicit collection imports must not call a model'
        outside=Path(folder)/'outside.csv';outside.write_text('code,age\\n002,31\\n',encoding='utf-8')
        for path in ['../outside.csv',str(outside)]:
            try:app.invoke('root','kb_ingest',dict(file_path=path,collection=collection['id']))
            except PermissionError:pass
            else:raise AssertionError('Workspace escape accepted: '+path)
    finally:backend.close()
''')

    def test_both_applications_share_components_without_grant_leaks(self):
        self.run_case(AGENT_CASE,application='all')


AGENT_SETUP = r"""
import tempfile,json
from uuid import uuid4
from datanet.core.backend import Backend
from datanet.core.application import Application
class Port:
    def __init__(self):self.agents={'root':dict(status='idle',options={})};self.tools={};self.runs=[];self.docs={};self.inboxes={};self.input_events={}
    def __call__(self,name,p):
        actor=p.get('actor')
        if name=='tools':self.tools[actor]=[t['name'] for t in p['definitions']];return {}
        if name in ['inbox-snapshot','messages']:return self.inboxes.get(actor,[])
        if name=='input-message':
            key=(actor,p['source'],p['event']['id']);self.input_events.setdefault(key,p['event']);return dict(queued=True)
        if name=='document-present':return (actor,p['document']) in self.docs
        if name=='inspect':return self.agents[actor]
        if name=='create':self.agents[actor]=dict(status='idle',options={});return dict(session_id=p['binding']['session_id'])
        if name=='load-document':
            key=(actor,p['document']);changed=self.docs.get(key)!=p['text'];self.docs[key]=p['text'];return changed
        if name in ['view-update','component-extension','capabilities']:return {}
        if name=='make-message':return dict(id=uuid4().hex,role='user',content=p['text'])
        if name=='steer':self.inboxes.setdefault(actor,[]).append(p['message']);return {}
        if name=='run':raise AssertionError('A direct knowledge operation unexpectedly called a model')
        raise AssertionError(name)
def stop(app,backend):
    for plugin in app.plugins.values():
        if hasattr(plugin,'close'):plugin.close()
    backend.close()
"""

AGENT_CASE=AGENT_SETUP+r"""
with tempfile.TemporaryDirectory() as folder:
    backend=Backend(folder);port=Port();app=Application(backend,port,dict(rootNetwork='knowledge_base',workspace=folder))
    app.bind_session('root-session')
    try:
        assert set(app.states)=={'root'}
        assert set(app.state('root')['grant']['names'])=={'knowledge_base'}
        result=app.invoke('root','kb_ingest',dict(content={'name':'Alice','age':30}))
        assert result['status']=='pending' and result['input_id'] in backend.network.nodes
        collection=app.invoke('root','kb_create_node',dict(name='People',storage='sqlite',schema={'name':'string','age':'integer'}))
        saved=app.invoke('root','kb_store',dict(collection=collection['id'],intake_id=result['intake_id']))
        app.invoke('root','task_document_write',dict(content='已归档',receipts=saved['records']))
        second=app.invoke('root','kb_ingest',dict(content={'name':'Bob','age':31}))
        assert second['status']=='stored'
        assert app.invoke('root','kb_search',dict(query='Alice'))['total']==1
        assert not port.runs
        assert not any(id in backend.network.nodes for id in ['knowledge/curator','knowledge/retriever'])
        assert 'datanet_spawn_helper' in port.tools['root']
        assert not any(t.startswith('datanet_create_') or t=='handle_problem' for t in port.tools['root'])
    finally:stop(app,backend)
"""

if __name__=='__main__':unittest.main()
