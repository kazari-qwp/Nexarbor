"""位置/道路、移动钩子与双节点转交的原业务断言。"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_caller, as_requester
from domain.agent import AgentNode
from domain.annotated_link import AnnotatedLink
from domain.core import Link, Module, Network, Node, NodeInfo
from projects.npc_town.modules.movement_here import MovementHereModule
from projects.npc_town.modules.place_info import PlaceInfoModule
from projects.npc_town.modules.records_store import RecordsStoreModule
from projects.npc_town.modules.records_transfer import RecordsTransferModule
from projects.npc_town.modules.records_transfer.module import TransferFailure

ROOT=Path(__file__).resolve().parents[1]
CHANNELS=('movement','road','location','records','transfer','self')


class TownMovementTransferTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='.movement-',dir=ROOT/'build')
        self.addCleanup(self.temp.cleanup)
        self.a=AgentNode(NodeInfo('a','A'));self.b=AgentNode(NodeInfo('b','B'))
        self.home=Node(NodeInfo('home','Home',description='old place'))
        self.park=Node(NodeInfo('park','Park',description='green park'))
        self.net=Network([self.a,self.b,self.home,self.park]);self.saver=NetworkSaver()
        self.backend=Backend(self.temp.name,network=self.net,saver=self.saver)
        self.addCleanup(lambda:self.backend.close())
        self.ap=PlaceInfoModule({'location':'home'});self.bp=PlaceInfoModule({'location':'home'})
        self.hp=PlaceInfoModule({'visitors_from_edges':True});self.pp=PlaceInfoModule({'visitors_from_edges':True})
        for node,module in [(self.a,self.ap),(self.b,self.bp),(self.home,self.hp),(self.park,self.pp)]:node.install(module)
        self.ar=RecordsStoreModule({'initial':{'ap':5,'food':10}})
        self.br=RecordsStoreModule({'initial':{'ap':1,'food':2}})
        self.a.install(self.ar);self.b.install(self.br)
        for source,target in [('a','home'),('home','a'),('b','home'),('home','b')]:self.location(source,target)
        self.road1=self.edge('home','park','road');self.road2=self.edge('park','home','road')
        self.move=MovementHereModule(self.transaction,channels=CHANNELS,strength=5)
        self.park.install(self.move)
        self.transfer=RecordsTransferModule(self.transaction,channels=CHANNELS,strength=5)
        self.a.install(self.transfer)
        self.saver.tables.module_types.update({
            'place.info':lambda spec:PlaceInfoModule(),
            'records.store':lambda spec:RecordsStoreModule(),
            'movement.here':lambda spec:MovementHereModule(self.transaction),
            'records.transfer':lambda spec:RecordsTransferModule(self.transaction),
        })

    def edge(self,source,target,relation):
        edge=AnnotatedLink(target,CHANNELS,attributes={'relation':relation})
        self.net.get(source).links.add(edge);return edge

    def location(self,source,target):return self.edge(source,target,'location')

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    async def values(self):return (await self.ar.read())['values'],(await self.br.read())['values']

    def locations(self,node):return [edge.target_id for edge in node.links if getattr(edge,'attributes',{}).get('relation')=='location']

    async def test_place_visitors_use_only_own_location_edges(self):
        self.edge('home','park','business')
        info=await self.hp.read()
        self.assertEqual(info['visitors'],['a','b']);self.assertEqual(info['description'],'old place')
        self.ap.config['visitors_from_edges']=True
        with self.assertRaises(PermissionError):await self.ap.read()

    async def test_place_changes_enforce_requester_and_immediate_source(self):
        with as_requester('b'):
            with self.assertRaises(PermissionError):await self.hp.arrive('a')
            with as_caller('park'):
                with self.assertRaises(PermissionError):await self.ap.set_location('park','Park')
        with as_requester('a'):
            with self.assertRaises(PermissionError):await self.ap.set_location('park','Park')
        self.assertEqual(self.ap.state,{})

    async def test_movement_updates_both_location_edges_inputs_and_ordered_hooks(self):
        self.move.config['before_hooks']=[{'target':'requester','module':'records.store','operation':'apply','arguments':{'deltas':{'ap':-1}}}, {'target':'requester','module':'records.store','operation':'read'}]
        with as_requester('a'):result=await self.move.move()
        self.assertTrue(result['moved']);self.assertEqual(result['from_location'],'home')
        self.assertEqual([item['operation'] for item in result['before_results']],['apply','read'])
        self.assertEqual(result['before_results'][1]['data']['values']['ap'],4)
        self.assertEqual(self.locations(self.a),['park']);self.assertEqual(self.locations(self.home),['b'])
        self.assertEqual(self.locations(self.park),['a'])
        self.assertIn(self.road1,list(self.home.links));self.assertIn(self.road2,list(self.park.links))
        self.assertEqual((await self.ap.read())['visit'],1)
        self.assertEqual((await self.ap.read())['location'],'park')
        self.assertEqual(self.a.inputs.snapshot()['module:place.info']['tail'],['当前位置：park\nPark：green park'])
        with as_requester('a'):self.assertFalse((await self.move.move())['moved'])
        self.assertEqual((await self.ar.read())['values']['ap'],4)

    async def test_movement_failure_after_hooks_and_arrival_restores_whole_group(self):
        self.move.config['before_hooks']=[{'target':'requester','module':'records.store','operation':'apply','arguments':{'deltas':{'ap':-2}}}]
        edges={node.info.node_id:tuple(node.links) for node in (self.a,self.home,self.park)}
        with patch.object(self.ap,'set_location',side_effect=RuntimeError('location write failed')):
            with as_requester('a'):
                with self.assertRaisesRegex(RuntimeError,'location write failed'):await self.move.move()
        self.assertEqual((await self.ar.read())['values']['ap'],5)
        for node in (self.a,self.home,self.park):self.assertEqual(tuple(node.links),edges[node.info.node_id])
        self.assertEqual(self.hp.state,{});self.assertEqual(self.pp.state,{})
        self.assertEqual(self.a.inputs.snapshot(),{})
        self.assertEqual((await self.ap.read())['location'],'home')

    async def test_single_direction_road_and_bad_location_channels_do_not_mutate(self):
        self.park.links.add(Link("a", "movement"))
        self.park.links.remove(self.road2)
        with as_requester('a'):
            with self.assertRaisesRegex(RuntimeError,'双向'):await self.move.move()
        self.park.links.add(self.road2)
        self.move.config['location_channels']=['location','self']
        with as_requester('a'):
            with self.assertRaisesRegex(RuntimeError,'self'):await self.move.move()
        self.assertEqual((await self.ap.read())['location'],'home')
        self.assertEqual(self.locations(self.a),['home'])

    async def test_movement_hook_cannot_write_outside_locked_group(self):
        class Other(Module):
            def __init__(self):super().__init__('other')
            async def change(module):return await self.br.apply(deltas={'ap':5})
        self.a.install(Other());self.saver.tables.module_types['other']=lambda spec:Other()
        self.move.config['before_hooks']=[{'target':'requester','module':'other','operation':'change'}]
        with as_requester('a'):
            with self.assertRaisesRegex(RuntimeError,'locked|锁'):await self.move.move()
        self.assertEqual((await self.br.read())['values']['ap'],1)
        self.assertEqual((await self.ap.read())['location'],'home')

    async def test_transfer_cost_receipt_duplicate_and_ap_as_resource(self):
        result=await self.transfer.give('b','food',3,key='one')
        self.assertEqual(result['ap'],4)
        self.assertEqual(await self.values(),({'ap':4,'food':7},{'ap':1,'food':5}))
        self.assertTrue((await self.transfer.give('b','food',3,key='one'))['duplicate'])
        with self.assertRaisesRegex(TransferFailure,'不同参数'):await self.transfer.give('b','food',4,key='one')
        result=await self.transfer.give('b','ap',2,key='two')
        self.assertEqual(result['ap'],1)
        self.assertEqual(await self.values(),({'ap':1,'food':7},{'ap':3,'food':5}))

    async def test_transfer_second_write_failure_rolls_back_both_accounts_and_receipt(self):
        original=self.br.apply
        async def fail(**parameters):await original(**parameters);raise ValueError('recipient failed')
        with patch.object(self.br,'apply',side_effect=fail):
            with self.assertRaisesRegex(TransferFailure,'recipient failed'):await self.transfer.give('b','food',3,key='one')
        self.assertEqual(await self.values(),({'ap':5,'food':10},{'ap':1,'food':2}))
        self.assertEqual(self.transfer.state,{})
        self.assertFalse((await self.transfer.give('b','food',3,key='one'))['duplicate'])

    async def test_transfer_owner_type_location_resources_and_reachability(self):
        with as_requester('b'):
            with self.assertRaises(TransferFailure):await self.transfer.give('b','food',1)
        for target in ['a','home','unknown']:
            with self.assertRaises(TransferFailure):await self.transfer.give(target,'food',1)
        self.bp.state['location']='park'
        with self.assertRaises(TransferFailure):await self.transfer.give('b','food',1)
        self.bp.state.clear()
        with self.assertRaises(TransferFailure):await self.transfer.give('b','food',100)
        self.transfer.channels=('wrong',)
        with self.assertRaises(TransferFailure):await self.transfer.give('b','food',1)
        self.assertEqual(self.transfer.state,{})
        self.assertEqual(await self.values(),({'ap':5,'food':10},{'ap':1,'food':2}))

    async def test_transfer_concurrent_same_key_charges_once(self):
        results=await asyncio.gather(*(self.transfer.give('b','food',1,key='one') for _ in range(6)))
        self.assertEqual(sum(not item['duplicate'] for item in results),1)
        self.assertEqual(await self.values(),({'ap':4,'food':9},{'ap':1,'food':3}))

    async def test_reopen_keeps_annotated_edges_positions_tools_and_transfer_receipts(self):
        await self.transfer.give('b','food',1,key='one')
        with as_requester('a'):await self.move.move()
        names=[tool.name for tool in self.move.tools]
        self.backend.save();self.backend.close();self.backend=Backend(self.temp.name,saver=self.saver)
        a=self.backend.network.get('a');park=self.backend.network.get('park')
        self.assertEqual(self.locations(a),['park']);self.assertEqual(self.locations(park),['a'])
        self.assertEqual((await a.modules.get('place.info').read())['location'],'park')
        self.assertEqual([tool.name for tool in park.modules.get('movement.here').tools],names)
        duplicate=await a.modules.get('records.transfer').give('b','food',1,key='one')
        self.assertTrue(duplicate['duplicate'])
