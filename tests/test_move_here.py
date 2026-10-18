"""移动模块的权限、事务和真实工具路由，不调用模型。"""
import asyncio
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.node_modules import NodeModules
from datanet.core.module_protocol import ModuleDefinition,ComponentResult
from datanet.core.module_tools import ModuleTools
from test_tool_collector import load,ROOT

class MoveHereTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(dir=ROOT/'build');self.directory=Path(self.temp.name)
        sdk=load('move_sdk',ROOT/'extensions/foundation/capabilities/module_sdk/python/datanet/studio/contract.py')
        self.factories={name:sdk.factory(ROOT/'extensions/foundation/capabilities'/folder)[1] for name,folder in [('movement.here','move_here'),('place.info','place_info'),('tools.collector','tool_collector')]}
        self.b=SimpleNamespace(directory=self.directory,network=Network(),agents={},_transaction_lock=RLock(),components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
        for key in ('npc','other'):self.b.network.add_node(AgentNode(key,key,file_path=self.directory/(key+'.md')))
        for key in ('old','new','far','hidden'):self.b.network.add_node(Node(key,key,None))
        self.b.modules=NodeModules(self.b,self.factories);self.b.signals=self.b.network.signals;self.b.dispatch=lambda *a:None
        self.tools=ModuleTools(self.b)
        for actor in ('npc','other'):
            self.connect(actor,'old','location');self.connect('old',actor,'location')
            self.b.modules.mount(actor,'place.info',config={'location':'old'},access={'strength':0,'channels':['movement']})
        for a,b in [('old','new'),('new','old'),('new','far'),('far','new')]:self.connect(a,b,'road')
        for target in ('old','new','far'):
            self.b.modules.mount(target,'place.info',config={'description':'地点说明','visitors':['npc','other'] if target=='old' else []},access={'strength':0,'channels':['movement']})
            self.b.modules.mount(target,'movement.here',access={'strength':3,'channels':['movement','tools']})
    def connect(self,a,b,relation):self.b.network.nodes[a].connect(b,channels=['movement','tools'],threshold=1,attributes={'relation':relation})
    async def asyncTearDown(self):
        await self.b.signals.close();self.assertEqual(self.b.node_locks.exclusive,{});self.assertEqual(self.b.node_locks.active,{})
        self.b.modules.clear();self.temp.cleanup()
    async def move(self,actor='npc',target='new'):
        return await self.b.modules.access(actor,target,'movement.here','move',{},strength=4,channels=['movement','tools'])
    async def info(self,node):return (await self.b.modules.call(node,'place.info','read'))['data']
    def edges(self):return {id:deepcopy(node.interfaces) for id,node in self.b.network.nodes.items()}
    async def test_move_updates_links_rosters_inputs_and_preserves_other_edges(self):
        self.b.network.nodes['npc'].connect('old',channels=['notes'],attributes={'relation':'business'})
        result=await self.move();self.assertEqual(result['status'],'ok',result)
        self.assertEqual((await self.info('npc'))['location'],'new');self.assertEqual((await self.info('old'))['visitors'],['other']);self.assertEqual((await self.info('new'))['visitors'],['npc'])
        self.assertTrue(any(e.target_node_id=='new' for e in self.b.network.nodes['npc'].interfaces));self.assertTrue(any(e.metadata.attributes.get('relation')=='business' for e in self.b.network.nodes['npc'].interfaces))
        self.assertFalse(any(e.target_node_id=='npc' and e.metadata.attributes.get('relation')=='location' for e in self.b.network.nodes['old'].interfaces))
        self.assertIn('当前位置：new',str(self.b.network.nodes['npc'].inputs.snapshot()));self.assertFalse((await self.move())['data']['moved'])
    async def test_static_tool_can_be_discovered_invoked_and_is_not_duplicated(self):
        entries=await self.tools.visit('npc','new',strength=2,channels=['movement']);self.assertEqual(len(entries),1)
        self.assertIn('移动到此',entries[0]['definition']['description']);await self.tools.visit('npc','new',strength=2,channels=['movement'])
        self.assertEqual(len(self.tools.acquired('npc',strength=2,channels=['movement'])),1)
        result=await self.tools.invoke('npc',entries[0],{},strength=2,channels=['movement']);self.assertTrue(result['moved'])
    async def test_collector_can_forward_move_without_changing_the_authenticated_requester(self):
        self.b.modules.mount('old','tools.collector',access={'strength':2,'channels':['movement','tools']})
        tools=(await self.b.modules.access('npc','old','tools.collector','collect',{},strength=1,channels=['tools']))['data']
        selected=next(t for t in tools if t['origin']=={'node_id':'new','tool':'module:movement.here/move_here'})
        result=await self.b.modules.access('npc','old','tools.collector','invoke',{'tool_id':selected['id'],'arguments':{}},strength=1,channels=['tools'])
        self.assertEqual(result['status'],'ok',result);self.assertEqual((await self.info('npc'))['location'],'new');self.assertEqual((await self.info('other'))['location'],'old')
    async def test_bad_parameters_non_neighbor_and_missing_authority_do_not_change_graph(self):
        before=self.edges()
        with self.assertRaises(Exception):await self.b.modules.access('npc','new','movement.here','move',{'npc_id':'other'},strength=3,channels=['movement'])
        self.assertEqual((await self.move(target='far'))['status'],'error')
        for target,strength,channels in [('hidden',5,['movement']),('new',1,['movement']),('new',3,['wrong'])]:
            with self.assertRaises((PermissionError,KeyError)):await self.b.modules.access('npc',target,'movement.here','move',{},strength=strength,channels=channels)
        self.assertEqual(self.edges(),before)
    async def test_failure_after_writes_rolls_back_edges_state_metadata_and_agent_inputs(self):
        original=self.factories['place.info'].execute;before=self.edges();inputs=deepcopy(self.b.network.nodes['npc'].inputs.snapshot())
        async def fail(ctx,activation):
            result=await original(ctx,activation)
            if activation.operation=='set_location':raise ValueError('模拟末尾失败')
            return result
        with patch.object(self.factories['place.info'],'execute',fail):result=await self.move()
        self.assertEqual(result['status'],'error');self.assertEqual(self.edges(),before);self.assertEqual((await self.info('npc'))['location'],'old')
        self.assertEqual((await self.info('new'))['visitors'],[]);self.assertEqual(self.b.network.nodes['npc'].inputs.snapshot(),inputs);self.assertEqual(self.b.modules._published,{})
    async def test_readers_wait_for_the_whole_move_and_two_npcs_share_one_destination_safely(self):
        original=self.factories['place.info'].execute;ready,release=asyncio.Event(),asyncio.Event()
        async def wait(ctx,activation):
            result=await original(ctx,activation)
            if activation.operation=='set_location' and ctx.node_id=='npc':ready.set();await release.wait()
            return result
        with patch.object(self.factories['place.info'],'execute',wait):
            moving=asyncio.create_task(self.move());await asyncio.wait_for(ready.wait(),3)
            reader=asyncio.create_task(self.info('new'));second=asyncio.create_task(self.move('other'))
            await asyncio.sleep(.02);self.assertFalse(reader.done());self.assertFalse(second.done());release.set()
            first=await moving;other=await second;self.assertEqual(first['status'],'ok',first);self.assertEqual(other['status'],'ok',other);await reader
        self.assertEqual((await self.info('new'))['visitors'],['npc','other']);self.assertEqual((await self.info('old'))['visitors'],[])

class EdgePortTests(unittest.IsolatedAsyncioTestCase):
    async def test_preflight_blocks_out_of_range_and_ungranted_channels_and_batch_failure_is_atomic(self):
        b=SimpleNamespace(network=Network(),_transaction_lock=RLock(),components=SimpleNamespace(module_owners={},enabled=set(),module_extensions={}))
        for id in ('a','b','hidden'):b.network.add_node(Node(id,id,None))
        b.network.nodes['a'].connect('b',channels=['x'])
        async def execute(ctx,activation):return ComponentResult(data=await ctx.network.patch_edges(activation.parameters['changes']))
        definition=ModuleDefinition(execute,operations=[dict(name='edit',channels=['x'],parameters={'type':'object'},result={})]);b.modules=NodeModules(b,{'editor':definition});b.modules.mount('a','editor',access={'strength':1,'channels':['x']})
        def change(target='b',channels=['x']):return dict(source='b',target=target,action='add',metadata=dict(channels=channels,attributes={}))
        before=deepcopy(b.network.nodes['b'].interfaces)
        for changes in [[change(),change('hidden')],[change(),change(channels=['secret'])]]:
            with self.assertRaises(PermissionError):await b.modules.call('a','editor','edit',{'changes':changes})
            self.assertEqual(b.network.nodes['b'].interfaces,before)
        await b.modules.call('a','editor','edit',{'changes':[change(),change()]});self.assertEqual(len(b.network.nodes['b'].interfaces),1);b.modules.clear()

class MoveExampleTests(unittest.IsolatedAsyncioTestCase):
    async def test_shipped_network_can_move_to_shop_and_back_through_actual_tools(self):
        from datanet.core.serialization import _build
        sdk=load('example_sdk',ROOT/'extensions/foundation/capabilities/module_sdk/python/datanet/studio/contract.py')
        factories={name:sdk.factory(ROOT/'extensions/foundation/capabilities'/folder)[1] for name,folder in [('movement.here','move_here'),('place.info','place_info')]}
        document=json.loads((ROOT/'examples/move_here/network.json').read_text(encoding='utf-8'))
        with TemporaryDirectory(dir=ROOT/'build') as directory:
            base=Path(directory)
            for file,content in document['files'].items():(base/file).write_text(content,encoding='utf-8')
            b=SimpleNamespace(directory=base,network=_build(document['network'],base),agents={},_transaction_lock=RLock(),components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
            b.modules=NodeModules(b,factories);b.signals=b.network.signals;b.dispatch=lambda *a:None;b.modules.restore();tools=ModuleTools(b)
            try:
                for target in ('shop','square'):
                    entries=await tools.visit('root',target,strength=2,channels=['movement','tools']);self.assertEqual(len(entries),1)
                    result=await tools.invoke('root',entries[0],{},strength=2,channels=['movement','tools']);self.assertTrue(result['moved'])
                    self.assertEqual(b.network.nodes['root'].modules['place.info']['state']['location'],target)
                    self.assertEqual(b.network.nodes[target].modules['place.info']['state']['visitors'],['root'])
            finally:await b.signals.close();b.modules.clear()
