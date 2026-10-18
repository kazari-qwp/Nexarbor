"""真实后端的局部管理员验证；制作结果用确定性宿主桩提供，不调用模型。"""
import asyncio,json,os,sys,tempfile,unittest
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.update(PYTHONPATH=str(ROOT/'python'),DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION=json.dumps(['capabilities/component_studio','capabilities/tool_collector','capabilities/network_administrator','capabilities/metadata_fields','capabilities/records_store']),DATANET_COMPONENT_PROFILE='{}',PYTHONDONTWRITEBYTECODE='1')
sys.path.insert(0,str(ROOT/'python'))
from datanet.core.backend import Backend
from datanet.core.node import Node
from datanet.core.interface import Interface
from datanet.studio.service import write_json,read_json

class AdministratorTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'build');self.b=Backend(self.temp.name);b=self.b
  for id in ['admin','one','two','far','wrong','secret']:b.network.add_node(Node(id,id,None))
  def link(source,target,channels=['admin'],threshold=0):b.network.nodes[source].interfaces.append(Interface(target,dict(channels=channels,threshold=threshold,multiplier=1,attributes={})))
  link('admin','one');link('one','two');link('two','far');link('admin','wrong',['private']);link('one','secret',['private']);link('secret','one',['private'])
  self.mount=json.loads((ROOT/'extensions/foundation/capabilities/network_administrator/module/example.json').read_text(encoding='utf-8'));self.mount['access']['channels']=['admin','info','records','tools'];b.modules.mount('admin','network.administrator',**self.mount)
  self.calls=[]
  async def host(method,p):
   self.calls.append((method,p))
   if method=='start':return dict(id='task-'+str(len(self.calls)),status='running')
   return dict(id=p['task'],status='completed')
  b.network_administrator.host=host
 def tearDown(self):
  self.b.close();self.assertTrue(Path(self.temp.name).resolve().is_relative_to(ROOT/'build'));self.temp.cleanup()
 def call(self,operation,args=None):return self.b.runtime.run(self.b.modules.call('admin','network.administrator',operation,args))['data']
 def job(self,key='test'):
  job=self.call('build',dict(requirement='建立一个共享看板',key=key));scope=self.b.network_administrator.task('admin',job['task']);return job,scope,deepcopy(scope['document'])
 def save(self,scope,doc):write_json(self.b.studio.folder(scope['workspace'])/'network.json',doc)
 def new_node(self,id='new',module=False):
  n=dict(type='node',node_id=id,name='新看板',description='',management_parent_id='root',divergence=-1,data_kind=None,parameters={},connections=dict(interfaces=[]),agent=None,modules={},offered_tools=[],toolboxes=[],expose=[],execution=None,inputs=None,context_cursor=None)
  if module:n['modules']={'records.store':dict(config={'initial':{'score':3}},state={},access=dict(strength=0,channels=['records']))}
  return n
 def test_scope_uses_strength_channel_and_omits_boundary(self):
  data=self.call('inspect');nodes=data['document']['network']['nodes'];self.assertEqual({n['name'] for n in nodes},{'admin','one','two'});self.assertNotIn('secret',json.dumps(data));self.assertNotIn('far',json.dumps(data));self.assertNotIn('network.administrator',json.dumps(data));self.assertEqual(nodes[0]['node_id'],'root')
 def test_component_mode_and_idempotent_start(self):
  j,scope,doc=self.job();self.assertFalse(self.calls[0][1]['allow_component_creation']);again=self.call('build',dict(requirement='建立一个共享看板',key='test'));self.assertTrue(again['duplicate']);self.assertEqual(len(self.calls),1)
  with self.assertRaises(ValueError):self.call('build',dict(requirement='不同的需求',key='test'))
  with self.assertRaises(PermissionError):self.b.network_administrator.bind_child(dict(parent=scope['workspace'],id='module-forbidden'))
 def test_hidden_target_is_rejected_even_if_guessed(self):
  j,s,d=self.job();d['network']['nodes'][0]['connections']['interfaces'].append(dict(target_node_id='secret',metadata=dict(channels=['admin'],threshold=0,multiplier=1,attributes={})));self.save(s,d)
  with self.assertRaises(PermissionError):self.call('apply',dict(task=j['task']))
 def test_disconnect_revokes_old_scope(self):
  j,s,d=self.job();self.b.network.nodes['admin'].interfaces=[]
  with self.assertRaises(PermissionError):self.call('apply',dict(task=j['task']))
 def test_concurrent_state_or_metadata_change_refuses_overwrite(self):
  j,s,d=self.job();self.b.network.nodes['one'].description='别人刚刚修改'
  with self.assertRaises(ValueError):self.call('apply',dict(task=j['task']))
 def test_grant_and_state_escalations_rejected(self):
  for change in ['grant','external','official','existing']:
   with self.subTest(change=change):
    j,s,d=self.job(change);n=self.new_node(module=True)
    if change=='grant':n['modules']['records.store']['access']['strength']=99
    if change=='external':n['offered_tools']=[dict(ref='harness:pwsh',channels=['tools'])]
    if change=='official':n['modules']['network.administrator']=deepcopy(self.mount)
    if change=='existing':d['network']['nodes'][1]['divergence']=20
    d['network']['nodes'].append(n);self.save(s,d)
    with self.assertRaises(PermissionError):self.call('apply',dict(task=j['task']))
 def test_apply_is_local_preserves_boundary_and_deduplicates(self):
  j,s,d=self.job();n=self.new_node(module=True);d['network']['nodes'].append(n);d['network']['nodes'][0]['connections']['interfaces'].append(dict(target_node_id='new',metadata=dict(channels=['admin','records'],threshold=0,multiplier=1,attributes={})));self.save(s,d)
  result=self.call('apply',dict(task=j['task']));new=result['node_ids']['new'];self.assertNotEqual(new,'new');self.assertIn(('one','secret'),[(k,e.target_node_id) for k,node in self.b.network.nodes.items() for e in node.interfaces]);self.assertEqual(self.b.network.nodes['secret'].name,'secret');self.assertEqual(self.b.network.nodes['two'].interfaces[0].target_node_id,'far');self.assertIn('records.store',self.b.network.nodes[new].modules);self.assertIs(self.b.network.nodes['admin'].modules['network.administrator']['state'],self.b.modules.get('admin','network.administrator').state)
  self.assertTrue(self.call('apply',dict(task=j['task']))['duplicate']);self.assertEqual(len([x for x in self.b.network.nodes if x.startswith('admin-')]),1)
 def test_existing_modules_keep_state_and_context(self):
  self.b.modules.mount('one','records.store',config={'initial':{'score':3}},state={},access=dict(strength=0,channels=['records']));self.b.network.nodes['one'].context_cursor={'session_id':'keep-native-log'}
  j,s,d=self.job();alias=s['aliases']['one'];entry=next(n for n in d['network']['nodes'] if n['node_id']==alias);entry['modules']['records.store']['config']['initial']['score']=4;self.save(s,d);self.call('apply',dict(task=j['task']));self.assertEqual(self.b.network.nodes['one'].context_cursor,{'session_id':'keep-native-log'});self.assertEqual(self.b.network.nodes['one'].modules['records.store']['state'],{})
 def test_boundary_incoming_prevents_deletion(self):
  j,s,d=self.job();one=s['aliases']['one'];d['network']['nodes']=[n for n in d['network']['nodes'] if n['node_id']!=one]
  for n in d['network']['nodes']:n['connections']['interfaces']=[e for e in n['connections']['interfaces'] if e['target_node_id']!=one]
  self.save(s,d)
  with self.assertRaises(PermissionError):self.call('apply',dict(task=j['task']))
 def test_current_copy_and_environment_are_scoped(self):
  j,s,d=self.job();self.b.studio.copy_current(dict(id=s['workspace']));copy=read_json(self.b.studio.folder(s['workspace'])/'network.json',{});self.assertEqual(copy,s['document'])
  value=self.b.studio.environment(dict(id=s['workspace'],action='reset',source='current'));self.assertEqual({n['name'] for n in value['nodes']},{'admin','one','two'})
 def test_other_administrator_cannot_take_task(self):
  j,s,d=self.job()
  with self.assertRaises(PermissionError):self.b.network_administrator.task('one',j['task'])
 def test_failed_commit_rolls_back_created_nodes_edges_and_files(self):
  j,s,d=self.job();n=self.new_node(module=True);d['network']['nodes'].append(n);self.save(s,d);original=self.b.write_documents
  def fail(files):raise RuntimeError('注入文件提交失败')
  self.b.write_documents=fail
  try:
   with self.assertRaisesRegex(RuntimeError,'注入'):self.call('apply',dict(task=j['task']))
  finally:self.b.write_documents=original
  self.assertFalse(any(k.startswith('admin-') for k in self.b.network.nodes));self.assertEqual({e.target_node_id for e in self.b.network.nodes['admin'].interfaces},{'one','wrong'});self.assertNotIn(s['workspace'],self.b.extension_state.get('admin_receipts',{}))
 def test_lifecycle_commit_waits_for_active_access(self):
  async def scenario():
   admitted=asyncio.Event();release=asyncio.Event();events=[]
   async def reader():
    async with self.b.node_locks.access(['one']):admitted.set();await release.wait();events.append('reader-finished')
   read=asyncio.create_task(reader());await admitted.wait();submit=asyncio.create_task(self.b.node_locks.mutate(['one'],lambda:events.append('committed')));await asyncio.sleep(.02);self.assertFalse(submit.done());release.set();await asyncio.gather(read,submit);self.assertEqual(events,['reader-finished','committed'])
  self.b.runtime.run(scenario())
 def test_runtime_state_progress_during_making_is_preserved(self):
  self.b.modules.mount('one','records.store',config={'initial':{'score':3}},state={},access=dict(strength=0,channels=['records']))
  j,s,d=self.job();self.b.network.nodes['one'].modules['records.store']['state']['values']={'score':17};self.b.network.nodes['one'].modules['records.store']['state']['receipts']={}
  self.save(s,d);self.call('apply',dict(task=j['task']));self.assertEqual(self.b.network.nodes['one'].modules['records.store']['state']['values']['score'],17)
 def test_external_typed_reference_never_becomes_local_root_alias(self):
  self.b.modules.mount('one','records.store',config={'initial':{},'references':[{'key':'observer','node_id':'root'}]},state={},access=dict(strength=0,channels=['records']))
  j,s,d=self.job();entry=next(n for n in d['network']['nodes'] if n['node_id']==s['aliases']['one']);reference=entry['modules']['records.store']['config']['references'][0]['node_id'];self.assertTrue(reference.startswith('outside-'));self.save(s,d);self.call('apply',dict(task=j['task']));self.assertEqual(self.b.network.nodes['one'].modules['records.store']['config']['references'][0]['node_id'],'root')
 def test_creation_mode_child_inherits_same_local_copy(self):
  self.b.modules.unmount('admin','network.administrator');mount=deepcopy(self.mount);mount['config']['allow_component_creation']=True;self.b.modules.mount('admin','network.administrator',**mount)
  j,s,d=self.job();self.assertTrue(self.calls[0][1]['allow_component_creation']);child=self.b.studio.create(dict(kind='module',sample='blank'));self.b.network_administrator.bind_child(dict(parent=s['workspace'],id=child['id']));self.assertEqual(self.b.network_administrator.source(child['id']),s['document']);self.assertEqual(self.b.studio.maker_scope(dict(id=child['id']))['role'],'component')
 def test_creation_switch_revocation_blocks_new_delegation(self):
  self.b.modules.unmount('admin','network.administrator');mount=deepcopy(self.mount);mount['config']['allow_component_creation']=True;self.b.modules.mount('admin','network.administrator',**mount);j,s,d=self.job()
  self.b.modules.unmount('admin','network.administrator');self.b.modules.mount('admin','network.administrator',**self.mount)
  with self.assertRaises(PermissionError):self.b.network_administrator.bind_child(dict(parent=s['workspace'],id='module-child'))
 def test_scope_lookup_rejects_traversal(self):
  for value in ['module-../outside','module-..'+chr(92)+'outside','module-..']:
   self.assertFalse(self.b.network_administrator.has(value))
 def test_scoped_validation_rejects_escape_before_submission(self):
  j,s,d=self.job();d['network']['nodes'][0]['connections']['interfaces'].append(dict(target_node_id='secret',metadata=dict(channels=['admin'],threshold=0,multiplier=1,attributes={})));self.save(s,d)
  from datanet.studio.network_work import check_work
  with self.assertRaises(PermissionError):check_work(self.b.studio.folder(s['workspace']),self.b,self.b.studio.library)
  with self.assertRaises(PermissionError):self.b.studio.environment(dict(id=s['workspace'],action='reset',source='candidate'))
 def test_agent_can_delegate_through_reachable_module_only(self):
  self.b.root.connect('admin',channels=['admin'])
  result=self.b.runtime.run(self.b.modules.access('root','admin','network.administrator','inspect',{},strength=1,channels=['admin']));self.assertEqual(len(result['data']['document']['network']['nodes']),3)
  with self.assertRaises(PermissionError):self.b.runtime.run(self.b.modules.access('root','admin','network.administrator','inspect',{},strength=1,channels=['private']))
 def test_official_administrator_cannot_be_purged(self):
  self.b.modules.unmount('admin','network.administrator');self.assertFalse(self.b.studio.release_delete_info(dict(module='network.administrator'))['canDelete'])
 def test_successful_delete_removes_only_local_node(self):
  self.b.network.nodes['secret'].interfaces=[];j,s,d=self.job();alias=s['aliases']['two'];d['network']['nodes']=[n for n in d['network']['nodes'] if n['node_id']!=alias]
  for n in d['network']['nodes']:n['connections']['interfaces']=[e for e in n['connections']['interfaces'] if e['target_node_id']!=alias]
  self.save(s,d);result=self.call('apply',dict(task=j['task']));self.assertEqual(result['deleted'],['two']);self.assertIn('far',self.b.network.nodes);self.assertNotIn('two',self.b.network.nodes)
 def test_cold_restore_keeps_new_nodes_and_submission_receipt(self):
  j,s,d=self.job();d['network']['nodes'].append(self.new_node());self.save(s,d);result=self.call('apply',dict(task=j['task']));self.b.close();self.b=Backend(self.temp.name);self.assertIn(result['created'][0],self.b.network.nodes);self.assertTrue(self.call('apply',dict(task=j['task']))['duplicate'])

if __name__=='__main__':unittest.main(verbosity=2)
