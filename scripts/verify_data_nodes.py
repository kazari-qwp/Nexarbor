"""真实存储引擎、核心快照、模块权限和复制隔离；全部临时文件在 E 盘。"""
import asyncio,json,os,subprocess,sys,tempfile,unittest,sqlite3,shutil
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'build/data-node-tests').mkdir(parents=True,exist_ok=True)
os.environ.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION=json.dumps(['capabilities/component_studio','capabilities/tool_collector','capabilities/data_nodes','capabilities/network_administrator','capabilities/knowledge_collection']),DATANET_COMPONENT_PROFILE='{}',HF_HOME=str(ROOT/'build/data-node-tests/model-cache'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
sys.path.insert(0,str(ROOT/'python'))
from datanet.core.backend import Backend
from datanet.core.resource_data import read_data,decode_data
from datanet.local_data.services import templates

class DataTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'build/data-node-tests');self.b=Backend(self.temp.name);self.bak=None
  doc=self.b.studio.state()['live']['document']
  for t in templates():doc['network']['nodes'].extend(t['snapshot']['nodes']);doc['files'].update(t['snapshot']['files'])
  self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head));self.b.dispatch('save',{})
 def tearDown(self):
  if self.b:self.b.close()
  self.assertTrue(Path(self.temp.name).resolve().is_relative_to(ROOT/'build/data-node-tests'));self.temp.cleanup()
 def call(self,node,op,args=None,module=None):
  r=self.b.runtime.run(self.b.modules.call(node,module or ('data.knowledge' if op in ('put','history','remove','restore','index','search','fetch') else 'data.local'),op,args or {}))
  self.assertEqual(r['status'],'ok',r);return r['data']
 def seed(self):
  self.call('template-value','write',dict(key='value',value={'count':7,'nested':['原始']}))
  for kind in ('csv','sqlite'):self.call('template-'+kind,'write',dict(key='one',value={'id':'one','text':'原始记录'}))
  for kind in ('rag','wiki'):self.call('template-'+kind,'put',dict(key='guide',value='# 数据指南\n\n原始资料正文。',metadata={'title':'数据指南'}))
 def copy(self,ids,mode='internal'):
  data=dict(document=self.b.studio.state()['live']['document'],ids=ids,mode=mode,catalog={k:dict(schema=v['manifest']['config_schema'],state_schema=v['manifest']['state_schema']) for k,v in self.b.studio.library.items()})
  source=Path(self.temp.name)/'copy-input.json';output=source.with_name('copy-output.json');source.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
  subprocess.run([shutil.which('node') or r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/copy_data_test.mjs'),str(source),str(output)],check=True,cwd=ROOT,capture_output=True)
  result=json.loads(output.read_text('utf-8'));self.b.studio.apply(dict(document=result['document'],base_commit=self.b.store.head));return result
 def test_all_native_drivers_and_schemas_are_real(self):
  self.seed()
  for kind in ('value','csv','sqlite','rag','wiki'):
   value=self.call('template-'+kind,'read',dict(key='value' if kind=='value' else 'one' if kind in ('csv','sqlite') else 'guide'));self.assertEqual(value['status'],'ok');self.assertTrue(value['items']);self.assertTrue(self.call('template-'+kind,'inspect'))
  db=self.b.network.nodes['template-sqlite'].db_path
  c=sqlite3.connect(db)
  try:self.assertEqual(c.execute('SELECT text FROM records WHERE id=?',('one',)).fetchone()[0],'原始记录')
  finally:c.close()
  self.assertIn('原始记录',self.b.network.nodes['template-csv'].file_path.read_text('utf-8-sig'))
 def test_copy_all_data_then_modify_copies_without_changing_sources(self):
  self.seed();result=self.copy(['template-'+k for k in ('value','csv','sqlite','rag','wiki')]);copied=dict(zip(('value','csv','sqlite','rag','wiki'),result['nodes']))
  for kind in ('csv','sqlite'):
   a=self.b.network.nodes['template-'+kind];b=self.b.network.nodes[copied[kind]];field='file_path' if kind=='csv' else 'db_path';self.assertNotEqual(getattr(a,field),getattr(b,field));self.call(copied[kind],'write',dict(key='one',value={'id':'one','text':'只改副本'}));self.assertEqual(self.call('template-'+kind,'read',{'key':'one'})['items'][0]['text'],'原始记录')
  self.call(copied['value'],'write',dict(key='value',value={'count':99}));self.assertEqual(self.call('template-value','read',{'key':'value'})['items'][0]['value']['count'],7)
  for kind in ('rag','wiki'):
   self.assertNotEqual(self.b.network.nodes[copied[kind]].directory,self.b.network.nodes['template-'+kind].directory);self.call(copied[kind],'put',dict(key='guide',value='副本的新正文',expected_version=1));self.assertIn('原始资料',self.call('template-'+kind,'read',{'key':'guide'})['items'][0]['content']);self.assertEqual(self.call(copied[kind],'read',{'key':'guide'})['items'][0]['content'],'副本的新正文')
 def test_binary_checkpoint_and_cold_restore_keep_modified_values(self):
  self.seed();self.b.dispatch('save',{});snapshot=self.b.snapshot();sql=self.b.network.nodes['template-sqlite'].db_path.relative_to(self.b.directory).as_posix();self.assertEqual(snapshot['files'][sql]['encoding'],'base64');self.assertTrue(decode_data(snapshot['files'][sql]).startswith(b'SQLite format 3'))
  self.b.close();self.b=Backend(self.temp.name)
  self.assertEqual(self.call('template-sqlite','read',{'key':'one'})['items'][0]['text'],'原始记录');self.assertIn('原始资料',self.call('template-wiki','read',{'key':'guide'})['items'][0]['content'])
 def test_versions_keyword_outline_links_delete_and_restore(self):
  self.seed();id='template-wiki';self.call(id,'put',dict(key='guide',value='# 数据指南\n\n## 新章节\n\n修改后的资料。',expected_version=1))
  self.assertEqual(len(self.call(id,'history',{'key':'guide'})['items']),2);self.assertTrue(self.call(id,'search',{'query':'修改'})['items'][0]['items'])
  outline=self.call(id,'fetch',{'key':'guide','view':'outline'})['items'][0];self.assertTrue(outline['outline']);self.call(id,'remove',{'key':'guide','expected_version':2});self.call(id,'restore',{'key':'guide','version':1,'expected_version':2});self.assertIn('原始资料',self.call(id,'read',{'key':'guide'})['items'][0]['content'])
 def test_only_reachable_channels_allow_data_calls(self):
  self.seed();self.b.network.nodes['root'].connect('template-csv',channels=['data'],threshold=1)
  ok=self.b.runtime.run(self.b.modules.access('root','template-csv','data.local','read',{'key':'one'},strength=1,channels=['data']));self.assertEqual(ok['status'],'ok')
  for target,channels,strength in [('template-csv',['private'],3),('template-csv',['data'],0),('template-sqlite',['data'],3)]:
   with self.assertRaises(PermissionError):self.b.runtime.run(self.b.modules.access('root',target,'data.local','read',{'key':'one'},strength=strength,channels=channels))
 def test_read_only_blocks_basic_and_dependent_knowledge_module(self):
  doc=self.b.studio.state()['live']['document'];node=next(n for n in doc['network']['nodes'] if n['node_id']=='template-wiki');node['modules']['data.local']['config']['read_only']=True;self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head))
  for module,op,args in [('data.local','write',{'key':'x','value':'no'}),('data.knowledge','put',{'key':'x','value':'no'})]:
   result=self.b.runtime.run(self.b.modules.call('template-wiki',module,op,args));self.assertEqual(result['status'],'error');self.assertIn('只读',result['error'])
 def test_preview_writes_only_the_returned_draft_and_preserves_live_database(self):
  self.seed();doc=self.b.studio.state()['live']['document'];node=next(n for n in doc['network']['nodes'] if n['node_id']=='template-sqlite')
  result=self.b.dispatch('data_preview',dict(node=node,files=doc['files'],operation='write',arguments={'key':'one','value':{'id':'one','text':'草稿值'}}));self.assertEqual(result['result']['status'],'ok');self.assertEqual(self.call('template-sqlite','read',{'key':'one'})['items'][0]['text'],'原始记录')
  doc['files'].update(result['files']);self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head));self.assertEqual(self.call('template-sqlite','read',{'key':'one'})['items'][0]['text'],'草稿值')
 def test_empty_directory_copy_changes_the_path_before_first_write(self):
  result=self.copy(['template-wiki']);copy=result['nodes'][0];self.assertNotEqual(self.b.network.nodes[copy].directory,self.b.network.nodes['template-wiki'].directory)
  self.call(copy,'put',{'key':'x','value':'仅副本有'});self.assertEqual(self.call('template-wiki','read',{'key':'x'})['status'],'not_found')
 def test_semantic_requires_a_model_and_never_uses_keyword_fallback(self):
  self.seed();result=self.b.runtime.run(self.b.modules.call('template-rag','data.local','query',{'request':{'method':'semantic','query':'资料'}}));self.assertEqual(result['status'],'error');self.assertIn('嵌入模型',result['error'])
 def test_directory_and_binary_lock_rollback_restores_old_data_and_removes_new_files(self):
  self.seed();b=self.b
  for id in ['template-wiki','template-sqlite','template-value']:b.network.nodes['root'].connect(id,channels=['data'])
  async def change():
   async with b.node_locks.transaction('root',['template-wiki','template-sqlite','template-value'],strength=1,channels=['data'],timeout=5):
    b.network.nodes['template-wiki'].write('guide','锁中的新正文');b.network.nodes['template-sqlite'].write('one',{'id':'one','text':'锁中的新记录'});b.network.nodes['template-value'].write('value',99)
    snapshot=await asyncio.to_thread(b.snapshot)
    self.assertNotIn('锁中的新正文',json.dumps(snapshot,ensure_ascii=False));raise RuntimeError('rollback')
  # Public host owner uses the same node lock transaction implementation as modules.
  with self.assertRaisesRegex(RuntimeError,'rollback'):b.runtime.run(change())
  self.assertIn('原始资料',self.call('template-wiki','read',{'key':'guide'})['items'][0]['content']);self.assertEqual(self.call('template-sqlite','read',{'key':'one'})['items'][0]['text'],'原始记录');self.assertEqual(self.call('template-value','read',{'key':'value'})['items'][0]['value']['count'],7)
 @unittest.skipUnless((ROOT/'build/models/bge-small-zh-v1.5').is_dir(),'需要已有本地嵌入模型才能执行真实向量验收')
 def test_real_vector_index_copy_works_after_source_directory_is_moved(self):
  model=ROOT/'build/models/bge-small-zh-v1.5';self.assertTrue(model.is_dir())
  doc=self.b.studio.state()['live']['document'];node=next(n for n in doc['network']['nodes'] if n['node_id']=='template-rag');node['parameters']['embedding']=dict(model_path=str(model),device='cpu',max_length=512,batch_size=8);self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head))
  self.call('template-rag','put',{'key':'solar','value':'太阳能电池板把阳光转换为电能，可用于家庭清洁能源供电。'});self.call('template-rag','put',{'key':'bread','value':'制作面包需要面粉、水、酵母和烤箱。'})
  result=self.copy(['template-rag']);id=result['nodes'][0];old=self.b.network.nodes['template-rag'].directory;backup=old.with_name(old.name+'-backup');self.assertTrue(old.is_relative_to(self.b.directory));self.assertTrue(backup.is_relative_to(self.b.directory));old.rename(backup)
  answer=self.call(id,'query',{'request':{'method':'semantic','query':'如何利用日照发电','top_k':1}});self.assertEqual(answer['status'],'ok');self.assertTrue(any(item['key']=='solar' for item in answer['items']));self.assertTrue(all(item['node_id']==id for item in answer['items']))
  self.call(id,'put',{'key':'solar','value':'副本：光伏电池将日照变为电能。','expected_version':1});self.assertEqual(self.call(id,'read',{'key':'solar'})['items'][0]['version'],2);self.assertTrue((backup/'catalog.sqlite3').exists())
 def test_maker_test_copy_keeps_binary_and_directory_resources(self):
  from datanet.studio.environment import sanitized
  self.seed();source=self.b.studio.state()['live']['document'];safe=sanitized(source)
  wiki=next(n for n in safe['network']['nodes'] if n['node_id']=='template-wiki');self.assertNotEqual(wiki['parameters']['directory'],'data/template-wiki');self.assertTrue(any(k.startswith(wiki['parameters']['directory']+'/') for k in safe['files']))
  sql=next(n for n in safe['network']['nodes'] if n['node_id']=='template-sqlite');self.assertEqual(safe['files'][sql['parameters']['db_path']]['encoding'],'base64')
 def test_record_content_and_schema_fields_are_never_rewritten_as_framework_metadata(self):
  doc=self.b.studio.state()['live']['document'];node=next(n for n in doc['network']['nodes'] if n['node_id']=='template-wiki');node['parameters'].update(directory='data/structured',storage='csv',schema={'node_id':'string','original_path':'string'})
  self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head));body={'node_id':'user field','original_path':'verbatim'};meta={'node_id':'metadata field','original_path':'metadata path'}
  result=self.call('template-wiki','put',{'key':'record','value':body,'metadata':meta})['items'][0];self.assertEqual(result['content'],body);self.assertEqual(result['metadata'],meta);self.assertEqual(self.call('template-wiki','inspect')['schema'],node['parameters']['schema'])
 def test_local_administrator_copies_binary_data_and_commits_a_fresh_database(self):
  self.seed();b=self.b
  mount=json.loads((ROOT/'extensions/foundation/capabilities/network_administrator/module/example.json').read_text('utf-8'));mount['access']['channels']=['admin','data','knowledge'];mount['access']['strength']=1;b.modules.mount('root','network.administrator',**mount)
  b.network.nodes['root'].connect('template-sqlite',channels=['data'])
  async def host(method,p):return dict(id='data-job',status='completed') if method=='start' else dict(status='completed')
  b.network_administrator.host=host;job=b.runtime.run(b.network_administrator.build('root',{'key':'data','requirement':'增加一份独立数据表'}));scope=b.network_administrator.task('root',job['task']);doc=deepcopy(scope['document'])
  sql=next(n for n in doc['network']['nodes'] if n['type']=='sqlite');self.assertEqual(doc['files'][sql['parameters']['db_path']]['encoding'],'base64');self.assertEqual(len(doc['network']['nodes']),2)
  preview=b.dispatch('data_preview',dict(node=sql,files=doc['files'],operation='write',arguments={'key':'one','value':{'id':'one','text':'管理员的副本'}}))
  fresh=deepcopy(sql);fresh['node_id']='new-table';fresh['name']='新数据表';fresh['parameters']['db_path']='data/new-table.sqlite3';doc['network']['nodes'].append(fresh);doc['files'][fresh['parameters']['db_path']]=preview['files'][sql['parameters']['db_path']]
  (b.studio.folder(scope['workspace'])/'network.json').write_text(json.dumps(doc),encoding='utf-8');result=b.runtime.run(b.network_administrator.apply('root',job['task']));id=result['created'][0]
  self.assertEqual(self.call(id,'read',{'key':'one'})['items'][0]['text'],'管理员的副本');self.assertEqual(self.call('template-sqlite','read',{'key':'one'})['items'][0]['text'],'原始记录');self.assertNotEqual(b.network.nodes[id].db_path,b.network.nodes['template-sqlite'].db_path)
 def test_primitive_knowledge_write_reports_the_real_node_identity(self):
  result=self.call('template-wiki','write',{'key':'primitive','value':'正文'})['items'][0];self.assertEqual(result['node_id'],'template-wiki');self.assertEqual(result['evidence']['node_id'],'template-wiki');self.assertNotIn('original_path',result)
 def test_preview_rejects_external_paths_and_unknown_operations(self):
  doc=self.b.studio.state()['live']['document'];node=next(n for n in doc['network']['nodes'] if n['node_id']=='template-sqlite');node['parameters']['db_path']='../outside.db'
  with self.assertRaisesRegex(ValueError,'越界'):self.b.dispatch('data_preview',dict(node=node,files={},operation='inspect'))
  node['parameters']['db_path']='data/db.sqlite3'
  with self.assertRaisesRegex(ValueError,'未知'):self.b.dispatch('data_preview',dict(node=node,files={},operation='execute_sql',arguments={'sql':'SELECT 1'}))

 def clear(self, id):
  from datanet.local_data.clear import clear_live
  doc=self.b.studio.state()['live']['document'];node=next(n for n in doc['network']['nodes'] if n['node_id']==id)
  return self.b.runtime.run(clear_live(self.b,dict(node=node,files=doc['files'],expected_commit=self.b.store.head)))
 def test_clear_all_native_data_keeps_configuration_and_remains_empty_after_restart(self):
  from copy import deepcopy
  self.seed();before=self.b.studio.state()['live']['document']
  for kind in ('value','csv','sqlite','rag','wiki'):
   id='template-'+kind;node=self.b.network.nodes[id];configuration=deepcopy(next(n for n in before['network']['nodes'] if n['node_id']==id));configuration['parameters'].pop('value',None)
   result=self.clear(id);self.assertEqual(result['scope'],'live')
   after=deepcopy(next(n for n in self.b.studio.state()['live']['document']['network']['nodes'] if n['node_id']==id));after['parameters'].pop('value',None);self.assertEqual(after,configuration)
   key='value' if kind=='value' else 'one' if kind in ('csv','sqlite') else 'guide';read=self.call(id,'read',{'key':key})
   self.assertEqual(read['items'][0]['value'],None) if kind=='value' else self.assertEqual(read['status'],'not_found')
   if kind in ('rag','wiki'):
    self.assertFalse(any('原始资料' in path.read_text('utf-8',errors='ignore') for path in node.directory.rglob('*') if path.is_file()))
    self.assertEqual(self.call(id,'history',{'key':'guide'})['status'],'not_found')
  self.assertEqual(self.b.network.nodes['template-csv'].file_path.read_text('utf-8').strip(),'id,text')
  db=sqlite3.connect(self.b.network.nodes['template-sqlite'].db_path)
  try:self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],0);self.assertEqual(len(db.execute('PRAGMA table_info(records)').fetchall()),2)
  finally:db.close()
  self.b.close();self.b=Backend(self.temp.name)
  for kind in ('csv','sqlite','rag','wiki'):self.assertEqual(self.call('template-'+kind,'read',{'key':'one' if kind in ('csv','sqlite') else 'guide'})['status'],'not_found')
 def test_clear_text_without_a_data_module_keeps_config_and_clears_real_file_and_backup(self):
  from copy import deepcopy
  doc=self.b.studio.state()['live']['document'];n=deepcopy(doc['network']['nodes'][1]);n.update(type='text_file',node_id='text',name='独立文本',data_kind='text',parameters={'file_path':'data/text.md','max_chars':100,'tool_channels':{}},modules={});doc['network']['nodes'].append(n);doc['files']['data/text.md']='真实正文';self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head))
  node=self.b.network.nodes['text'];node.write('content','第二版');self.assertTrue(node.backup_path.exists());before=deepcopy(next(n for n in self.b.studio.state()['live']['document']['network']['nodes'] if n['node_id']=='text'))
  self.clear('text');self.assertEqual(node.file_path.read_text('utf-8'),'');self.assertFalse(node.backup_path.exists());self.assertEqual(next(n for n in self.b.studio.state()['live']['document']['network']['nodes'] if n['node_id']=='text'),before)
 def test_clear_draft_is_independent_and_operator_can_clear_read_only_data(self):
  from copy import deepcopy
  self.seed();doc=self.b.studio.state()['live']['document'];node=deepcopy(next(n for n in doc['network']['nodes'] if n['node_id']=='template-sqlite'));node['modules']['data.local']['config']['read_only']=True
  result=self.b.dispatch('data_preview',dict(node=node,files=doc['files'],operation='clear'));self.assertTrue(result['node']['modules']['data.local']['config']['read_only']);self.assertNotEqual(result['files'][node['parameters']['db_path']],doc['files'][node['parameters']['db_path']]);self.assertEqual(self.call(node['node_id'],'read',{'key':'one'})['status'],'ok')
  n=next(n for n in doc['network']['nodes'] if n['node_id']=='template-sqlite');n['modules']['data.local']['config']['read_only']=True;self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head));self.clear(n['node_id']);self.assertEqual(self.call(n['node_id'],'read',{'key':'one'})['status'],'not_found');self.assertTrue(self.b.network.nodes[n['node_id']].modules['data.local']['config']['read_only'])
 def test_clear_waits_for_existing_access_and_rejects_stale_or_protected_storage(self):
  from datanet.local_data.clear import clear_live
  from copy import deepcopy
  self.seed();doc=self.b.studio.state()['live']['document'];node=next(n for n in doc['network']['nodes'] if n['node_id']=='template-wiki');request=dict(node=node,files=doc['files'],expected_commit=self.b.store.head)
  async def operation():
   async with self.b.node_locks.access(['template-wiki']):
    from contextvars import Context
    task=asyncio.create_task(clear_live(self.b,request),context=Context());await asyncio.sleep(.05);self.assertFalse(task.done());self.assertIn('原始资料',self.b.network.nodes['template-wiki'].read({'method':'key','key':'guide'}).items[0]['content'])
   await task
  self.b.runtime.run(operation())
  with self.assertRaisesRegex(ValueError,'网络已变化'):self.b.runtime.run(clear_live(self.b,request))
  unsafe=deepcopy(node);unsafe['parameters']['directory']='studio'
  with self.assertRaisesRegex(ValueError,'越界'):self.b.dispatch('data_preview',dict(node=unsafe,files={},operation='clear'))
 def test_failed_clear_restores_real_directory_and_value(self):
  from unittest.mock import patch
  from datanet.local_data import clear as operation
  self.seed();original=operation.clear_node
  def fail(node,home):original(node,home);raise RuntimeError('模拟清空中途失败')
  for id,key in [('template-wiki','guide'),('template-value','value'),('template-sqlite','one')]:
   with patch.object(operation,'clear_node',fail),self.assertRaisesRegex(RuntimeError,'模拟'):self.clear(id)
   result=self.call(id,'read',{'key':key});self.assertEqual(result['status'],'ok');self.assertIn('原始',json.dumps(result,ensure_ascii=False));self.assertFalse(self.b.failed)
 def test_clear_does_not_rebase_over_concurrent_unrelated_updates(self):
  from unittest.mock import patch
  from datanet.local_data import clear as operation
  self.seed();original=operation.clear_node
  def concurrent(node,home):
   original(node,home);self.b.network.nodes['template-value'].write('value',{'other':'其他执行者的新值'});self.b.dispatch('save',{})
  with patch.object(operation,'clear_node',concurrent):result=self.clear('template-wiki')
  self.assertFalse(result['rebase_safe']);self.assertEqual(self.call('template-value','read',{'key':'value'})['items'][0]['value']['other'],'其他执行者的新值');self.assertEqual(self.call('template-wiki','read',{'key':'guide'})['status'],'not_found')
 def test_clear_raw_vector_node_removes_all_index_versions_and_resets_cache(self):
  from datanet.components.nodes.llamaindex_node.llamaindex_node import LlamaIndexNode
  n=LlamaIndexNode('raw-index','底层向量节点',self.b.directory/'data/raw-index',embedding_config={'model_path':str(ROOT/'build/models/bge-small-zh-v1.5'),'device':'cpu','max_length':128,'batch_size':2});n.management_parent_id='root';self.b.network.add_node(n)
  folder=n.storage_path/'versions/abc';folder.mkdir(parents=True);(folder/'docstore.json').write_text('旧索引正文',encoding='utf-8');(n.storage_path/'current.json').write_text('{"version":"abc"}',encoding='utf-8');n.index=object();n._version='abc'
  before=n.embedding_config.copy();result=self.clear(n.node_id);self.assertEqual(result['scope'],'live');self.assertEqual(list(n.storage_path.iterdir()),[]);self.assertEqual(n.embedding_config,before);self.assertIsNone(n.index);self.assertIsNone(n._version);self.assertFalse(n.has_index())
 def test_clear_original_knowledge_module_removes_versions_without_removing_modules(self):
  from copy import deepcopy
  original=json.loads((ROOT/'configs/knowledge_v3/network.json').read_text('utf-8'));node=deepcopy(next(n for n in original['network']['nodes'] if n['node_id']=='knowledge'));doc=self.b.studio.state()['live']['document'];doc['network']['nodes'].append(node);self.b.studio.apply(dict(document=doc,base_commit=self.b.store.head))
  self.call('knowledge','put',{'id':'doc','title':'标题','text':'正文','tags':[]},module='knowledge.collection');before=deepcopy(self.b.network.nodes['knowledge'].modules['knowledge.collection']['config']);self.clear('knowledge')
  self.assertEqual(self.b.network.nodes['knowledge'].modules['knowledge.collection']['config'],before);self.assertEqual(self.b.network.nodes['knowledge'].modules['knowledge.collection']['state']['documents'],{});r=self.call('knowledge','search',{'query':''},module='knowledge.collection');self.assertEqual(r['items'],[])

if __name__=='__main__':unittest.main(verbosity=2)
