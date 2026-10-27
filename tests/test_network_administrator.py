"""原管理员边界：真实新表、生命周期提交、局部回滚；制作宿主为本地夹具。"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from app.runtime.backend import Backend
from app.network_saver import NetworkSaver
from app.projects.host_tools import HostTools
from app.studio.service import Studio,write_json,read_json
from domain.agent import MarkdownAgentNode
from domain.core import Network,Node,NodeInfo,Link,MarkdownNode
ROOT=Path(__file__).resolve().parents[1];MODULES=ROOT/'projects/discussion_collaboration/modules'

class NetworkAdministratorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(prefix='new-admin-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name);runtime=self.folder/'runtime';runtime.mkdir()
        nodes=[Node(NodeInfo(name,name),bias=-1) for name in ('admin','one','two','far','wrong','secret')]
        caller_file=runtime/'caller.md';caller_file.write_text('caller memory',encoding='utf-8');nodes.append(MarkdownAgentNode(NodeInfo('caller','caller'),caller_file))
        library={'network.administrator':MODULES/'network_administrator','records.store':ROOT/'projects/npc_town/modules/records_store'}
        saver=NetworkSaver();self.host_tools=HostTools(saver.tables,lambda:self.backend,None,[])
        def configure(backend):
            backend.restore_extra=lambda current,document:self.host_tools.register(document.get('node_properties',{}))
            Studio(backend,library,project_directory=self.folder,ports=self.host_tools.definitions,register_properties=self.host_tools.register)
        self.configure=configure;self.backend=Backend(runtime,saver=saver,network=Network(nodes),configure=configure);self.closed=False
        async def close():
            if not self.closed:await self.backend.signals.close();self.backend.close();self.closed=True
        self.addAsyncCleanup(close)
        def link(source,target,channels=('admin',)):self.backend.network.get(source).links.add(Link(target,channels))
        link('admin','one');link('one','two');link('two','far');link('admin','wrong',['private']);link('one','secret',['private']);link('secret','one',['private']);link('caller','admin',['tools'])
        await self.backend.studio.mount({'node':'admin','module':'network.administrator','access':dict(channels=['admin','tools','info','records','chat'],strength=2)})
        self.admin=self.backend.network.get('admin').modules.get('network.administrator');self.service=self.backend.network_administrator;self.calls=[]
        async def host(method,parameters):
            self.calls.append((method,parameters))
            return dict(id='task-'+str(len(self.calls)),status='running') if method=='start' else dict(id=parameters['task'],status='completed')
        self.service.host=host

    async def job(self,key='test'):
        result=await self.admin.build(requirement='建立共享看板',key=key);scope=self.service.task('admin',result['task']);return result,scope,deepcopy(scope['document'])

    def save(self,scope,document):write_json(self.backend.studio.folder(scope['workspace'])/'network.json',document)

    def node(self,id='new'):
        return dict(node_id=id,name='新看板',description='',type='node',bias=-1,aggregation='sum',links=[],tables={'modules':[]})

    async def test_original_channel_strength_scope_and_masked_root(self):
        result=await self.admin.inspect();names={node['name'] for node in result['document']['network']['nodes']}
        self.assertEqual(names,{'admin','one','two'});self.assertNotIn('secret',json.dumps(result));self.assertNotIn('far',json.dumps(result));self.assertNotIn('network.administrator',json.dumps(result))
        self.assertEqual(result['document']['network']['nodes'][0]['node_id'],'root')

    async def test_idempotent_start_owner_and_component_mode(self):
        result,scope,document=await self.job();again=await self.admin.build(requirement='建立共享看板',key='test');self.assertTrue(again['duplicate']);self.assertEqual(result['task'],again['task'])
        with self.assertRaisesRegex(ValueError,'相同制作键'):await self.admin.build(requirement='改变需求',key='test')
        with self.assertRaises(PermissionError):self.service.task('one',result['task'])
        self.assertFalse(self.service.workspace({'id':scope['workspace']})['allow_component_creation'])
        with self.assertRaises(PermissionError):self.service.record('../outside')

    async def test_local_apply_retains_boundary_objects_sessions_and_deduplicates(self):
        result,scope,document=await self.job();one=self.backend.network.get('one');caller=self.backend.network.get('caller');state={'session_id':'native-caller'};self.backend.agents['caller']=state
        document['network']['nodes'].append(self.node());document['network']['nodes'][0]['links'].append(dict(target_id='new',channels=['admin'],threshold=0,processor={'type':'multiplier','factor':1}))
        self.save(scope,document);applied=await self.admin.apply(task=result['task']);created=applied['node_ids']['new']
        self.assertIs(self.backend.network.get('one'),one);self.assertIs(self.backend.network.get('caller'),caller);self.assertIs(self.backend.agents['caller'],state)
        self.assertIn('secret',[edge.target_id for edge in one.links]);self.assertIsNotNone(self.backend.network.get(created));self.assertTrue((await self.admin.apply(task=result['task']))['duplicate'])
        self.backend.save(full=True);await self.backend.signals.close();self.backend.close();self.closed=True
        restored=Backend(self.folder/'runtime',saver=self.backend.saver,configure=self.configure)
        try:self.assertIsNotNone(restored.network.get(created));self.assertTrue(restored.extension_state['admin_receipts'][scope['workspace']])
        finally:await restored.signals.close();restored.close()

    async def test_disconnect_configuration_and_scope_escalation_are_rejected(self):
        result,scope,document=await self.job();self.backend.network.get('one').info.name='并发名称';self.save(scope,document)
        with self.assertRaisesRegex(ValueError,'配置已经变化'):await self.admin.apply(task=result['task'])
        self.backend.network.get('one').info.name='one';self.backend.network.get('one').links.remove(next(iter(self.backend.network.get('one').links)))
        with self.assertRaisesRegex(PermissionError,'可达范围'):await self.admin.apply(task=result['task'])
        malicious=deepcopy(document);malicious['network']['nodes'][0]['links'].append(dict(target_id='secret',channels=['admin']))
        with self.assertRaises((PermissionError,ValueError)):self.service.check(scope['workspace'],malicious)

    async def test_delete_checks_outside_incoming_and_can_delete_unreferenced_local_node(self):
        result,scope,document=await self.job();target=scope['aliases']['one'];document['network']['nodes']=[node for node in document['network']['nodes'] if node['node_id']!=target]
        for node in document['network']['nodes']:node['links']=[edge for edge in node['links'] if edge['target_id']!=target]
        self.save(scope,document)
        with self.assertRaisesRegex(PermissionError,'边界外'):await self.admin.apply(task=result['task'])
        self.backend.network.get('secret').links.remove(next(iter(self.backend.network.get('secret').links)))
        applied=await self.admin.apply(task=result['task']);self.assertEqual(applied['deleted'],['one']);self.assertIsNone(self.backend.network.get('one'));self.assertIsNotNone(self.backend.network.get('secret'))

    async def test_failed_commit_restores_files_node_identity_and_outside_signal_object(self):
        result,scope,document=await self.job();before=self.backend.network.get('admin');signals=self.backend.signals.records
        node=self.node();node['type']='markdown';node['data']=dict(type='markdown',path='data/new.md',directory=False,save_data=True);document['network']['nodes'].append(node);document['files']['data/new.md']='new file'
        self.save(scope,document);original_save=self.backend.save
        def fail(**kwargs):raise OSError('injected save failure')
        with patch.object(self.backend,'save',side_effect=fail):
            with self.assertRaisesRegex(OSError,'injected'):await self.admin.apply(task=result['task'])
        self.assertIs(self.backend.network.get('admin'),before);self.assertIs(before.modules.get('network.administrator'),self.admin);self.assertIs(self.admin._access_origin,before);self.assertIs(self.backend.signals.records,signals)
        self.assertEqual(len(self.backend.network),7);self.assertEqual(list((self.backend.directory/'created').rglob('*.md')),[])
        self.assertEqual(set((await self.admin.inspect())['document']['network']['nodes'][0]['tables']['modules']),set())


    async def test_runtime_state_and_external_typed_references_keep_original_identity(self):
        await self.backend.studio.mount({'node':'one','module':'records.store','config':dict(initial={'score':3},references=[{'key':'observer','node_id':'caller'}]),'access':dict(channels=['records'],strength=0)})
        module=self.backend.network.get('one').modules.get('records.store');result,scope,document=await self.job()
        entry=next(node for node in document['network']['nodes'] if node['node_id']==scope['aliases']['one']);reference=entry['tables']['modules'][0]['config']['references'][0]['node_id'];self.assertTrue(reference.startswith('outside-'))
        module.state['values']={'score':17};module.state['receipts']={};self.save(scope,document);await self.admin.apply(task=result['task'])
        self.assertIs(self.backend.network.get('one').modules.get('records.store'),module);self.assertEqual(module.state['values']['score'],17);self.assertEqual(module.config['references'][0]['node_id'],'caller')

    async def test_repeated_units_apply_with_real_module_tables_and_scope_quota(self):
        result,scope,document=await self.job();node=self.node();node['tables']['modules']=[dict(module_id='records.store',config={'initial':{'score':3}},state={},strength=0,channels=['records'],channel_mode='allow')]
        document['network']['nodes'].append(node);document['network'].update(repeat_unit_count=3,repeat_unit=['new']);self.save(scope,document)
        applied=await self.admin.apply(task=result['task']);self.assertEqual(len(applied['created']),3)
        for name in applied['created']:self.assertEqual(self.backend.network.get(name).modules.get('records.store').config['initial']['score'],3)
        result,scope,document=await self.job('quota');document['network']['nodes'].append(self.node());document['network'].update(repeat_unit_count=40,repeat_unit=['new']);self.save(scope,document)
        with self.assertRaisesRegex(ValueError,'上限'):await self.admin.apply(task=result['task'])

    async def test_ports_are_scoped_readonly_and_new_nodes_reuse_visible_grants(self):
        properties=self.backend.extension_state.setdefault('node_properties',{})
        for node in ('one','secret'):properties[node]={'offered_ports':[{'ref':'runtime:read_text','channels':['info']}]}
        self.host_tools.ensure(self.backend.network,properties)
        result,scope,document=await self.job();catalog=self.backend.studio.catalog_ports({'query':'runtime:read_text'},scope['workspace']);self.assertEqual(catalog['ports'][0]['offers'],[dict(node=scope['aliases']['one'],channels=['info'])]);self.assertNotIn('secret',json.dumps(catalog))
        new=self.node();document['network']['nodes'].append(new);document['network']['properties']['new']={'offered_ports':[{'ref':'runtime:read_text','channels':['info']}]};self.save(scope,document)
        applied=await self.admin.apply(task=result['task']);self.assertEqual(len(list(self.backend.network.get(applied['node_ids']['new']).tools)),1)
        forged=deepcopy(document);forged['network']['properties']['new']['offered_ports'][0]['channels']=['private']
        with self.assertRaises(PermissionError):self.service.check(scope['workspace'],forged)

    async def test_lifecycle_waits_for_active_access_and_validation_is_scoped(self):
        result,scope,document=await self.job();self.save(scope,document);admitted=asyncio.Event();release=asyncio.Event();events=[]
        async def reader():
            async with self.backend.node_locks.access(['one']):admitted.set();await release.wait();events.append('reader-finished')
        read=asyncio.create_task(reader());await admitted.wait();submit=asyncio.create_task(self.admin.apply(task=result['task']));await asyncio.sleep(.02);self.assertFalse(submit.done());release.set();await read;await submit;events.append('committed');self.assertEqual(events,['reader-finished','committed'])
        self.backend.studio.copy_current({'id':scope['workspace']});self.assertEqual(read_json(self.backend.studio.folder(scope['workspace'])/'network.json',{}),scope['document'])


    async def test_component_child_inherits_scope_and_revocation_prevents_delegation(self):
        self.admin.config['allow_component_creation']=True;result,scope,document=await self.job();self.assertTrue(self.calls[0][1]['allow_component_creation'])
        child=self.backend.studio.create({'kind':'module','sample':'blank'});self.service.bind_child({'parent':scope['workspace'],'id':child['id']})
        self.assertEqual(self.service.source(child['id']),scope['document']);self.assertEqual(self.backend.studio.maker_scope({'id':child['id']})['role'],'component')
        self.admin.config['allow_component_creation']=False
        with self.assertRaises(PermissionError):self.service.bind_child({'parent':scope['workspace'],'id':'module-next'})

    async def test_existing_state_and_grants_cannot_be_rewritten_in_candidate(self):
        await self.backend.studio.mount({'node':'one','module':'records.store','config':dict(initial={'score':3}),'access':dict(channels=['records'],strength=0)})
        result,scope,document=await self.job();entry=next(node for node in document['network']['nodes'] if node['node_id']==scope['aliases']['one'])
        entry['tables']['modules'][0]['state']['values']={'score':999}
        with self.assertRaisesRegex(PermissionError,'状态或授权'):self.service.check(scope['workspace'],document)
        entry['tables']['modules'][0]['state']={};entry['bias']=99
        with self.assertRaisesRegex(PermissionError,'已有节点'):self.service.check(scope['workspace'],document)


    async def test_scoped_environment_and_existing_tool_interface_are_protected(self):
        properties=self.backend.extension_state.setdefault('node_properties',{});properties['one']={'offered_ports':[{'ref':'runtime:read_text','channels':['info']}]};self.host_tools.ensure(self.backend.network,properties)
        result,scope,document=await self.job();self.save(scope,document)
        from app.studio.environment import prepare
        from app.studio.network_testing import NetworkHarness
        home=prepare(self.backend.studio,{'id':scope['workspace'],'source':'candidate'});h=NetworkHarness(home)
        try:
            actual=h.backend.extension_state['node_properties'][scope['aliases']['one']]['offered_ports'];self.assertEqual(actual,properties['one']['offered_ports'])
        finally:await h.close()
        entry=next(node for node in document['network']['nodes'] if node['node_id']==scope['aliases']['one'])
        tool=next(item for item in entry['tables']['tools']['members'] if 'tool' in item);tool['parameters']={}
        with self.assertRaisesRegex(PermissionError,'工具表'):self.service.check(scope['workspace'],document)
        document['network']['nodes'][0]['links'].append(dict(target_id='secret',channels=['admin']));self.save(scope,document)
        with self.assertRaises((PermissionError,ValueError)):prepare(self.backend.studio,{'id':scope['workspace'],'source':'candidate'})
