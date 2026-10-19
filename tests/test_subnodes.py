import asyncio,tempfile,unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from datanet.core.node import Node
from datanet.core.subnode import Subnode
from datanet.core.network import Network
from datanet.core.node_modules import NodeModules
from datanet.core.module_protocol import ModuleDefinition,ComponentResult
from datanet.core.serialization import network_document,_build

async def execute(ctx,activation):
 if activation.operation=='local':return ComponentResult(data=(await ctx.local.call('test','view',{},target='sub'))['data'])
 return ComponentResult(data=await ctx.network.nodes(channels=ctx.resolve_channels(activation.parameters.get('channels',['x']),activation.parameters.get('mode','allow'))))
DEFINITION=ModuleDefinition(execute,operations=[dict(name=op,channels=[],parameters={'type':'object'},result={}) for op in ['view','local']],node_types=['node'])
class Subnodes(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.b=SimpleNamespace(directory=Path(self.temp.name),network=Network(),agents={},_transaction_lock=RLock(),components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
  self.b.modules=NodeModules(self.b,{'test':DEFINITION})
  for id in ['owner','node-edge','sub-edge','blocked']:self.b.network.add_node(Node(id,id,None))
  self.sub=Subnode('sub','亚节点',parent_id='owner');self.b.network.add_node(self.sub)
  self.b.network.nodes['owner'].connect('node-edge',channels=['x']);self.b.network.nodes['owner'].connect('blocked',channels=['secret']);self.sub.connect('sub-edge',channels=['x'])
  for id in ['owner','sub']:self.b.modules.mount(id,'test',{}, {},access={'strength':4,'channels':['x','secret']})
 async def asyncTearDown(self):await self.b.network.signals.close();self.b.modules.clear();self.temp.cleanup()
 async def ids(self,id='sub',**params):return [i['metadata']['node_id'] for i in (await self.b.modules.call(id,'test','view',params))['data']]
 async def test_separate_tables_default_isolation_and_normal_module_installation(self):
  self.assertEqual(await self.ids(),['sub','sub-edge']);self.assertEqual(await self.ids('owner'),['owner','node-edge']);self.assertEqual(len(self.sub.interfaces),1);self.assertEqual(len(self.b.network.nodes['owner'].interfaces),2)
 async def test_use_parent_switch_only(self):
  self.sub.use_parent_links=True;self.assertEqual(set(await self.ids()),{'sub','sub-edge','node-edge'});self.assertEqual(await self.ids('owner'),['owner','node-edge'])
 async def test_share_switch_only(self):
  self.sub.share_links=True;self.assertEqual(set(await self.ids('owner')),{'owner','node-edge','sub-edge'});self.assertEqual(await self.ids(),['sub','sub-edge'])
 async def test_no_duplicate_strength_when_both_switches_are_on(self):
  self.sub.share_links=self.sub.use_parent_links=True;result=(await self.b.modules.call('sub','test','view',{}))['data'];self.assertEqual(next(x['strength'] for x in result if x['metadata']['node_id']=='sub-edge'),3)
 async def test_parent_pure_local_call_ignores_channels_and_preserves_budget(self):
  result=(await self.b.modules.call('owner','test','local',{}))['data'];self.assertEqual([i['metadata']['node_id'] for i in result],['sub','sub-edge']);self.assertEqual(result[0]['strength'],4)
 async def test_nested_sharing_is_only_to_direct_parent(self):
  child=Subnode('child','二级亚节点',parent_id='sub',share_links=True);self.b.network.add_node(child);child.connect('blocked',channels=['x']);self.assertIn('blocked',await self.ids());self.assertNotIn('blocked',await self.ids('owner'));self.sub.share_links=True;self.assertIn('blocked',await self.ids('owner'))
 async def test_ownership_cycle_rejected(self):
  self.sub.parent_id='sub'
  with self.assertRaisesRegex(ValueError,'环'):self.b.network.validate_ownership()
 async def test_blacklist_inverse_and_empty_semantics(self):
  self.assertEqual(set(await self.ids('owner',channels=[],mode='deny')),{'owner','node-edge','blocked'});self.assertEqual(await self.ids('owner',channels=['secret'],mode='deny'),['owner','node-edge']);self.assertEqual(await self.ids('owner',channels=[]),['owner'])
 async def test_subnode_roundtrip_preserves_independent_tables(self):
  restored=_build(network_document(self.b.network,self.b.directory),self.b.directory);self.assertIsInstance(restored.nodes['sub'],Subnode);self.assertEqual(restored.nodes['sub'].parent_id,'owner');self.assertEqual(restored.nodes['sub'].interfaces,self.sub.interfaces);self.assertEqual(restored.nodes['owner'].interfaces,self.b.network.nodes['owner'].interfaces)
 async def test_blacklist_access_grant_limits_queries(self):
  self.b.modules.unmount('owner','test');self.b.modules.mount('owner','test',{}, {},access={'strength':4,'channels':['secret'],'channel_mode':'deny'})
  self.assertEqual(await self.ids('owner',channels=[],mode='deny'),['owner','node-edge'])
 async def test_parent_alias_and_uncommitted_switches_are_isolated_and_rollback(self):
  network=self.b.network
  self.assertEqual(network.resolve_reference('sub','$parent'),'owner')
  ready,release=asyncio.Event(),asyncio.Event()
  async def writer():
   try:
    async with self.b.node_locks.transaction('sub',['sub'],strength=0,channels=[]):
     self.sub.share_links=True;self.sub.parent_id='node-edge';ready.set();await release.wait();raise RuntimeError('rollback')
   except RuntimeError as error:
    if str(error)!='rollback':raise
  task=asyncio.create_task(writer());await ready.wait()
  try:
   self.assertEqual(network.family_root('sub'),'owner');self.assertEqual(network.resolve_reference('sub','$parent'),'owner')
   self.assertNotIn('sub-edge',[e.target_node_id for e in network.routing_snapshot()[1]['node-edge']])
  finally:release.set();await task
  self.assertEqual(self.sub.parent_id,'owner');self.assertFalse(self.sub.share_links)
if __name__=='__main__':unittest.main()
