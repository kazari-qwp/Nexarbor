"""Permission, provenance and restart boundaries of the two-level knowledge app."""
import test_knowledge_base as base
AGENT_SETUP = base.AGENT_SETUP


def case(body):
    return AGENT_SETUP + '''
with tempfile.TemporaryDirectory() as folder:
    backend=Backend(folder);port=Port();app=Application(backend,port,dict(rootNetwork='knowledge_base',workspace=folder))
    app.bind_session('root-session')
    try:
''' + ''.join('        ' + line + '\n' for line in body.splitlines()) + '''
    finally:stop(app,backend)
'''


def test_scoped_writes_and_read_sources(self):
    self.run_case(case('''
app.invoke('root','kb_task',dict(content='保存 Wiki，并参考数据库'))
port.agents['root']['options']=dict(provider='mock',model='root-model',maxTokens=50000,reasoningEffort='high')
table=app.invoke('root','kb_create_node',dict(name='来源',storage='sqlite',schema={'name':'string'}))
raw=app.invoke('root','kb_store',dict(collection=table['id'],content={'name':'Alice'}))
worker=app.invoke('root','datanet_spawn_helper',dict(components=['wiki']))['node_id']
assert backend.agents[worker]['agentOptions']['model']=='root-model'
assert backend.agents[worker]['agentOptions']['maxTokens']==50000
assert backend.agents[worker]['agentOptions']['reasoningEffort']=='high'
assert 'datanet_spawn_helper' not in port.tools[worker]
assert app.invoke(worker,'kb_fetch',dict(id=raw['id']))['content']['name']=='Alice'
wiki=app.invoke(worker,'kb_create_node',dict(name='知识页面',storage='wiki'))
page=app.invoke(worker,'kb_store',dict(collection=wiki['id'],content='Alice 的资料',sources=[raw['id']]))
for action,args in [('kb_create_node',dict(name='越权',storage='rag')),('kb_store',dict(collection=table['id'],content={'name':'bad'})),('kb_update',dict(id=raw['id'],content={'name':'bad'},expected_version=1)),('kb_delete',dict(id=raw['id'],expected_version=1)),('datanet_spawn_helper',{})]:
    try:app.invoke(worker,action,args)
    except PermissionError:pass
    else:raise AssertionError('Scope escape '+action)
try:app.plugins['capabilities/scoped_workers'].tool_datanet_spawn_helper(worker,{})
except PermissionError:pass
else:raise AssertionError('Recursive helpers accepted')
for components in [[],['unknown'],['wiki','wiki']]:
    try:app.invoke('root','datanet_spawn_helper',dict(components=components))
    except ValueError:pass
    else:raise AssertionError('Invalid component selection accepted')
general=app.invoke('root','datanet_spawn_helper',{})
assert set(general['scope']['storage_types'])=={'wiki','csv','sqlite','rag'}
assert app.invoke(general['node_id'],'kb_fetch',dict(id=page['id']))['id']==page['id']
# Revoking a graph edge affects both direct reads and global searches.
node=backend.network.nodes[worker]
node.interfaces=[e for e in node.interfaces if e.target_node_id!=table['node_id']]
app.invoke(worker,'kb_create_node',dict(name='另一知识集合',storage='wiki'))
try:app.invoke(worker,'kb_fetch',dict(id=raw['id']))
except PermissionError:pass
else:raise AssertionError('Disconnected data still readable')
assert all(h['id']!=raw['id'] for h in app.invoke(worker,'kb_search',{})['items'])
assert all(c['id']!=table['id'] for c in app.invoke(worker,'kb_catalog',{}))
'''))


def test_task_documents_immutable_evidence_and_receipts(self):
    self.run_case(case('''
task=app.invoke('root','kb_task',dict(content='原始要求：保留所有来源'))
helper=app.invoke('root','datanet_spawn_helper',dict(components=['wiki']))
worker=helper['node_id']
assert app.invoke(worker,'task_document_read',{})['content']=='原始要求：保留所有来源'
wiki=app.invoke(worker,'kb_create_node',dict(name='Wiki',storage='wiki'))
page=app.invoke(worker,'kb_store',dict(collection=wiki['id'],content='结果'))
evidence=dict(node_id=wiki['node_id'],locator=page['id'],version=1)
app.invoke(worker,'task_document_write',dict(content='助手结果',sources=[evidence],receipts=[page]))
read=app.invoke('root','task_document_read',dict(node_id=helper['result_id']))
assert read['content']=='助手结果' and read['sources']==[evidence] and read['revision']==1
assert backend.network.write(worker,task['input_id'],'content','坏原文').status=='forbidden'
assert backend.network.write(worker,task['result_id'],'content','冒名结果').status=='forbidden'
assert app.invoke(worker,'task_document_read',{})['content'].startswith('原始要求')
try:app.invoke(worker,'task_document_write',dict(content='坏来源',sources=[dict(node_id=wiki['node_id'],locator=page['id'],version=999)]))
except (KeyError,RuntimeError):pass
else:raise AssertionError('Invalid evidence version accepted')
try:app.invoke(worker,'task_document_write',dict(content='坏定位符',sources=[dict(node_id=wiki['node_id'],locator='Wiki 的记录是 '+page['id'],version=1)]))
except ValueError as error:assert 'one exact record ID' in str(error)
else:raise AssertionError('Prose accepted as a record locator')
try:app.invoke(worker,'task_document_write',dict(content='冲突',expected_revision=0))
except ValueError:pass
else:raise AssertionError('Stale delivery accepted')
app.invoke('root','datanet_send_message',dict(target=worker,content='请按原始任务核查'))
assert port.inboxes[worker]
other=app.invoke('root','kb_task',dict(content='另一个任务'))
try:app.invoke(worker,'task_document_read',dict(task_id=other['task_id']))
except PermissionError:pass
else:raise AssertionError('Unassigned task readable')
unrelated=app.invoke('root','kb_store',dict(collection=wiki['id'],content='另一个任务的写入'))
try:app.invoke(worker,'task_document_write',dict(content='伪造任务回执',receipts=[unrelated]))
except ValueError:pass
else:raise AssertionError('Unrelated task receipt accepted')
'''))


def test_read_mode_and_worker_restart(self):
    self.run_case(case('''
wiki=app.invoke('root','kb_create_node',dict(name='Wiki',storage='wiki'))
record=app.invoke('root','kb_store',dict(collection=wiki['id'],content='保留资料'))
task=app.invoke('root','kb_task',dict(content='查找资料',mode='read'))
helper=app.invoke('root','datanet_spawn_helper',dict(components=['wiki']))
worker=helper['node_id']
assert helper['scope']['storage_types']==[]
assert 'kb_store' not in port.tools[worker]
assert app.invoke(worker,'kb_fetch',dict(id=record['id']))['content']=='保留资料'
try:app.invoke('root','kb_store',dict(collection=wiki['id'],content='只读期间写入'))
except PermissionError:pass
else:raise AssertionError('Read mode mutation accepted')
app.invoke(worker,'task_document_write',dict(content='带来源的读取结果',sources=[dict(node_id=wiki['node_id'],locator=record['id'],version=1)]))
stop(app,backend)
backend=Backend(folder);port=Port();app=Application(backend,port,dict(rootNetwork='knowledge_base',workspace=folder))
app.bind_session('resumed-root')
app.invoke('root','datanet_send_message',dict(target=worker,content='继续核查'))
assert worker in app.states and 'kb_store' not in port.tools[worker]
assert app.invoke(worker,'task_document_read',dict(node_id=helper['result_id']))['content']=='带来源的读取结果'
# Starting a new write intake is allowed after a read task.
new=app.invoke('root','kb_ingest',dict(content='新任务资料',collection=wiki['id']))
assert new['status']=='stored'
'''))


def test_upstream_wiki_tools_and_lazy_guides(self):
    self.run_case(case('''
app.invoke('root','kb_task',dict(content='整理 Wiki'))
raw=app.invoke('root','kb_create_node',dict(name='原始资料',storage='rag'))
source=app.invoke('root','kb_store',dict(collection=raw['id'],content='初版资料'))
wiki=app.invoke('root','kb_create_node',dict(name='Wiki',storage='wiki'))
page=app.invoke('root','kb_store',dict(collection=wiki['id'],content='---\\naliases: [2024, true, 2026-10-15, WAL]\\ntags: [12, false]\\n---\\n# 组件网络\\n组件式权限网络，参见 [[missing-page]]。',sources=[source['id']],key='overview'))
assert not any('wiki:upstream' in key[1] for key in port.docs)
hit=app.invoke('root','kb_wiki',dict(action='search',collection=wiki['id'],query='权限网络'))
assert hit['engine']=='llm-wiki' and hit['items'][0]['id']==page['id']
try:app.invoke('root','kb_search',dict(collection=wiki['id'],query='权限网络',semantic=True))
except RuntimeError as error:assert 'embedding configuration' in str(error)
else:raise AssertionError('Keyword-only Wiki hits labeled as semantic search')
app.invoke('root','kb_update',dict(id=source['id'],content='更新资料',expected_version=1))
lint=app.invoke('root','kb_wiki',dict(action='lint',collection=wiki['id']))
assert 'missing-page' in lint['wantedPages'] and lint['stale'][0]['id']==page['id']
assert ('root','wiki:upstream:query') in port.docs and ('root','wiki:upstream:lint') in port.docs
'''))


def test_batch_intakes_keep_the_original_task_and_helper_access(self):
    self.run_case(case('''
task=app.invoke('root','kb_task',dict(content='批量整理资料，不丢失原始需求'))
helper=app.invoke('root','datanet_spawn_helper',dict(components=['wiki']))
first=app.invoke('root','kb_ingest',dict(content='第一份资料'))
second=app.invoke('root','kb_ingest',dict(content='第二份资料'))
assert first['task_id']==second['task_id']==task['task_id']
for item in [first,second]:
    assert app.invoke(helper['node_id'],'kb_intake',dict(id=item['intake_id']))['content'] in ['第一份资料','第二份资料']
assert app.invoke(helper['node_id'],'task_document_read',{})['content']=='批量整理资料，不丢失原始需求'
new=app.invoke('root','kb_task',dict(content='独立归档任务',mode='write'))
assert new['task_id']!=task['task_id']
'''))


# Keep this suite focused; borrow only run_case from the existing harness.
import unittest
class KnowledgeHelperTests(unittest.TestCase):
    run_case = base.KnowledgeBaseTests.run_case
    test_scoped_writes_and_read_sources = test_scoped_writes_and_read_sources
    test_task_documents_immutable_evidence_and_receipts = test_task_documents_immutable_evidence_and_receipts
    test_read_mode_and_worker_restart = test_read_mode_and_worker_restart
    test_upstream_wiki_tools_and_lazy_guides = test_upstream_wiki_tools_and_lazy_guides
    test_batch_intakes_keep_the_original_task_and_helper_access = test_batch_intakes_keep_the_original_task_and_helper_access


if __name__ == '__main__':unittest.main()
