"""原服务、商店、双人协议的结算与回滚规则。"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_requester
from domain.agent import AgentNode
from domain.core import Link, Module, Network, Node, NodeInfo
from projects.npc_town.modules.agreements_pair import AgreementsPairModule
from projects.npc_town.modules.place_info import PlaceInfoModule
from projects.npc_town.modules.records_store import RecordsStoreModule
from projects.npc_town.modules.service_actions import ServiceActionsModule
from projects.npc_town.modules.shop_market import ShopMarketModule

ROOT=Path(__file__).resolve().parents[1]


class TownBusinessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='.business-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.a=AgentNode(NodeInfo('a','A'));self.b=AgentNode(NodeInfo('b','B'));self.place=Node(NodeInfo('store','Store'))
        self.net=Network([self.a,self.b,self.place]);self.saver=NetworkSaver()
        self.backend=Backend(self.temp.name,network=self.net,saver=self.saver);self.addCleanup(lambda:self.backend.close())
        self.ar=RecordsStoreModule({'initial':{'ap':10,'coins':100,'rice':0,'health':0,'home':'house','ready':True}})
        self.br=RecordsStoreModule({'initial':{'ap':10,'coins':100,'rice':0,'health':0,'home':'house','ready':False}})
        self.stock=RecordsStoreModule({'initial':{'rice':10,'coins':100,'wood':10}})
        self.a.install(self.ar);self.b.install(self.br);self.place.install(self.stock)
        for node in (self.a,self.b):
            node.install(PlaceInfoModule({'location':'store'}));self.place.links.add(Link(node.info.node_id,'business'))
        self.service=ServiceActionsModule(self.transaction,{'address':'store','actions':[{'id':'rest','actor_set':{'health':2},'actor_deltas':{'health':1},'local_deltas':{'wood':-1},'cost':2}],'events':[{'id':'gift','probability':1,'limit':1,'rewards':{'health':1},'text':'gift'}]},channels='business',strength=2)
        self.shop=ShopMarketModule(self.transaction,{'products':[{'item':'rice','sale_price':3,'buyback_price':2}]},channels='business',strength=2)
        self.pair=AgreementsPairModule(self.transaction,{'address':'store','rules':[{'id':'pair','eligible_field':'ready','equal_fields':['home'],'pair_field':'spouse','forbid_existing_pair':True,'cost':1}]},channels='business',strength=2)
        self.place.install(self.service);self.place.install(self.shop);self.place.install(self.pair)
        self.saver.tables.module_types.update({
            'records.store':lambda spec:RecordsStoreModule(), 'place.info':lambda spec:PlaceInfoModule(),
            'service.actions':lambda spec:ServiceActionsModule(self.transaction),
            'shop.market':lambda spec:ShopMarketModule(self.transaction),
            'agreements.pair':lambda spec:AgreementsPairModule(self.transaction),
        })

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    async def values(self, records):return (await records.read())['values']

    async def test_service_set_then_delta_event_limit_and_idempotent_receipt(self):
        with as_requester('a'):
            first=await self.service.perform('rest',key='one')
            duplicate=await self.service.perform('rest',key='one')
            second=await self.service.perform('rest',key='two')
        self.assertEqual(first['values']['health'],4);self.assertEqual(first['values']['ap'],8)
        self.assertTrue(duplicate['duplicate']);self.assertEqual(second['values']['health'],3)
        self.assertEqual(second['values']['ap'],6);self.assertEqual((await self.values(self.stock))['wood'],8)
        self.assertEqual(self.service.state['event_counts'],{'gift':1})
        with as_requester('a'):
            with self.assertRaises(RuntimeError):await self.service.perform('rest',quantity=2,key='one')

    async def test_service_requires_exact_json_value_and_accounts_for_event_in_maximum(self):
        action=self.service.config['actions'][0]
        action['require_values']={'ready':1}
        with as_requester('a'):
            with self.assertRaisesRegex(RuntimeError,'不满足'):await self.service.perform('rest')
        action=self.service.config['actions'][0]
        action.pop('require_values');action['actor_maximums']={'health':3}
        with as_requester('a'):
            with self.assertRaisesRegex(RuntimeError,'超过上限'):await self.service.perform('rest')
        self.assertEqual((await self.values(self.ar))['ap'],10);self.assertEqual(self.service.state,{})

    async def test_service_after_hooks_are_ordered_and_failure_rolls_back_every_effect(self):
        self.service.config['after_hooks']=[{'target':'requester','module':'records.store','operation':'apply','arguments':{'set':{'marker':True}}},{'target':'requester','module':'records.store','operation':'read'}]
        with as_requester('a'):result=await self.service.perform('rest',key='one')
        self.assertTrue(result['after_results'][1]['data']['values']['marker'])
        before_actor=await self.values(self.ar);before_stock=await self.values(self.stock)
        class Failure(Module):
            def __init__(self):super().__init__('failure')
            async def stop(self):raise RuntimeError('hook failed')
        self.place.install(Failure());self.saver.tables.module_types['failure']=lambda spec:Failure()
        self.service.config['after_hooks'].append({'target':'local','module':'failure','operation':'stop'})
        with as_requester('a'):
            with self.assertRaisesRegex(RuntimeError,'hook failed'):await self.service.perform('rest',key='two')
        self.assertEqual(await self.values(self.ar),before_actor);self.assertEqual(await self.values(self.stock),before_stock)
        self.assertEqual(len(self.service.state['receipts']),1);self.assertEqual(self.service.state['event_counts'],{'gift':1})

    async def test_service_same_user_key_isolated_by_requester_and_rejects_wrong_location(self):
        with as_requester('a'):await self.service.perform('rest',key='one')
        with as_requester('b'):self.assertFalse((await self.service.perform('rest',key='one'))['duplicate'])
        self.assertEqual(len(self.service.state['receipts']),2)
        self.b.modules.get('place.info').state['location']='elsewhere'
        with as_requester('b'):
            with self.assertRaisesRegex(RuntimeError,'业务地址'):await self.service.perform('rest',key='two')
        with self.assertRaisesRegex(RuntimeError,'身份'):await self.service.perform('rest')

    async def test_shop_buy_sell_and_duplicate_signature(self):
        with as_requester('a'):
            await self.shop.buy('rice',2,'buy')
            self.assertTrue((await self.shop.buy('rice',2,'buy'))['duplicate'])
            with self.assertRaises(ValueError):await self.shop.sell('rice',1,'buy')
            await self.shop.sell('rice',1,'sell')
        own=await self.values(self.ar);stock=await self.values(self.stock)
        self.assertEqual((own['ap'],own['coins'],own['rice']),(8,96,1))
        self.assertEqual((stock['coins'],stock['rice']),(104,9))
        self.assertEqual((await self.shop.inspect())['products'][0]['stock'],9)

    async def test_shop_second_write_failure_rolls_back_customer_stock_and_receipt(self):
        original=self.stock.apply
        async def fail(**parameters):await original(**parameters);raise ValueError('shop storage failed')
        with patch.object(self.stock,'apply',side_effect=fail):
            with as_requester('a'):
                with self.assertRaisesRegex(ValueError,'shop storage failed'):await self.shop.buy('rice',2,'one')
        own=await self.values(self.ar);stock=await self.values(self.stock)
        self.assertEqual((own['ap'],own['coins'],own['rice']),(10,100,0));self.assertEqual(stock['rice'],10)
        self.assertEqual(self.shop.state,{})

    async def test_shop_concurrent_same_key_settles_once_and_invalid_product_rejected(self):
        with as_requester('a'):results=await asyncio.gather(*(self.shop.buy('rice',1,'one') for _ in range(5)))
        self.assertEqual(sum(not result['duplicate'] for result in results),1)
        self.assertEqual((await self.values(self.ar))['ap'],9)
        self.shop.config['products'].append({'item':'coins','sale_price':1})
        with self.assertRaisesRegex(ValueError,'同名'):await self.shop.inspect()

    async def test_pair_requires_two_approvals_and_preserves_retry_receipts(self):
        with as_requester('a'):first=await self.pair.agree('b','pair','a1')
        self.assertEqual(first['status'],'open');self.assertEqual(len(first['approvals']),1)
        with as_requester('b'):second=await self.pair.agree('a','pair','b1')
        self.assertEqual(second['status'],'completed')
        own=await self.values(self.ar);other=await self.values(self.br)
        self.assertEqual((own['spouse'],other['spouse']),('b','a'));self.assertEqual((own['ap'],other['ap']),(9,9))
        with as_requester('a'):
            self.assertTrue((await self.pair.agree('b','pair','a1'))['duplicate'])
            self.assertEqual(len((await self.pair.inspect())['agreements']),1)

    async def test_pair_visit_change_invalidates_previous_approval(self):
        with as_requester('a'):await self.pair.agree('b','pair','a1')
        self.a.modules.get('place.info').state['visit']=1
        with as_requester('b'):second=await self.pair.agree('a','pair','b1')
        self.assertEqual(second['status'],'open');self.assertEqual([entry['participant'] for entry in second['approvals']],['b'])
        with as_requester('a'):third=await self.pair.agree('b','pair','a2')
        self.assertEqual(third['status'],'completed');self.assertEqual((await self.values(self.ar))['ap'],8)

    async def test_pair_second_relationship_write_failure_rolls_back_approval_and_accounts(self):
        with as_requester('a'):await self.pair.agree('b','pair','a1')
        original=self.br.apply
        async def fail(**parameters):
            result=await original(**parameters)
            if parameters.get('references'):raise ValueError('pair storage failed')
            return result
        with patch.object(self.br,'apply',side_effect=fail):
            with as_requester('b'):
                with self.assertRaisesRegex(ValueError,'pair storage failed'):await self.pair.agree('a','pair','b1')
        own=await self.values(self.ar);other=await self.values(self.br)
        self.assertNotIn('spouse',own);self.assertNotIn('spouse',other)
        self.assertEqual((own['ap'],other['ap']),(9,10))
        self.assertEqual(len(self.pair.state['agreements'][0]['approvals']),1)

    async def test_service_shop_pair_journal_reopen_rebinds_actual_tools(self):
        with as_requester('a'):
            await self.service.perform('rest',key='one');await self.shop.buy('rice',1,'one');await self.pair.agree('b','pair','one')
        names=[tool.name for tool in self.place.tools]
        self.backend.save();self.backend.close();self.backend=Backend(self.temp.name,saver=self.saver)
        place=self.backend.network.get('store')
        self.assertEqual([tool.name for tool in place.tools],names)
        with as_requester('a'):
            self.assertTrue((await place.modules.get('service.actions').perform('rest',key='one'))['duplicate'])
            self.assertTrue((await place.modules.get('shop.market').buy('rice',1,'one'))['duplicate'])
            self.assertTrue((await place.modules.get('agreements.pair').agree('b','pair','one'))['duplicate'])
