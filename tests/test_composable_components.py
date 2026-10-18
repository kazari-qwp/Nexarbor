"""制作器之外的业务验收；不读生成测试的答案或替组件放宽要求。"""
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from datanet.core.module_protocol import ComponentResult
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.node_modules import NodeModules
from datanet.core.external_tools import ExternalTools
from test_tool_collector import load,ROOT

class Composable(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        sdk=load('composable_sdk',ROOT/'extensions/foundation/capabilities/module_sdk/python/datanet/studio/contract.py')
        self.factories={}
        folders=[*list((ROOT/'extensions/composable/capabilities').iterdir()),*[ROOT/'extensions/foundation/capabilities'/name for name in ['place_info','move_here','tool_collector']]]
        for folder in folders:
            if (folder/'module.json').exists():
                spec,definition=sdk.factory(folder);self.factories[spec['id']]=definition
        self.b=SimpleNamespace(directory=ROOT/'build',network=Network(),agents={},_transaction_lock=RLock(),components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
        self.b.modules=NodeModules(self.b,self.factories);self.b.external_tools=ExternalTools(self.b);self.b.signals=self.b.network.signals;self.b.dispatch=lambda *a:None
    async def asyncTearDown(self):await self.b.signals.close();self.b.modules.clear()
    def node(self,id,agent=False):
        node=AgentNode(id,id,file_path=ROOT/'build'/('fixture-'+id+'.md')) if agent else Node(id,id,None)
        self.b.network.add_node(node);return node
    def mount(self,node,module,config=None,channels=('records',),strength=2):
        return self.b.modules.mount(node,module,config=config or {},access=dict(strength=strength,channels=list(channels)))
    async def call(self,actor,node,module,operation,parameters=None,channels=('records',)):
        return await self.b.modules.access(actor,node,module,operation,parameters or {},strength=2,channels=list(channels))
    async def values(self,node):return (await self.b.modules.call(node,'records.store','read'))['data']['values']
    async def test_set_then_delta_and_reference_compare_use_the_original_snapshot(self):
        self.node('a',True);self.mount('a','records.store',{'initial':{'gold':10},'references':[{'key':'home','node_id':'old'}]})
        result=await self.call('a','a','records.store','apply',{'set':{'gold':5},'deltas':{'gold':2},'expected':{'home':'old'},'references':[{'key':'home','node_id':'new'}],'key':'one'})
        self.assertEqual(result['status'],'ok',result);self.assertEqual(result['data']['values'],{'gold':7,'home':'new'})
    async def test_two_stores_and_two_actors_can_each_use_the_same_request_key(self):
        for actor in ['a','b']:
            self.node(actor,True);self.mount(actor,'records.store',{'initial':{'gold':10,'wood':0,'ap':10},'minimum':{'gold':0,'ap':0,'wood':0}})
        for shop in ['s1','s2']:
            self.node(shop);self.mount(shop,'records.store',{'initial':{'gold':0,'wood':4},'minimum':{'wood':0}})
            self.mount(shop,'service.actions',{'actions':[{'id':'buy','title':'购买','description':'买木头','actor_deltas':{'gold':-2,'wood':1},'local_deltas':{'gold':2,'wood':-1},'cost':1}]},channels=['records','service'])
            for actor in ['a','b']:
                self.b.network.nodes[actor].connect(shop,channels=['service']);self.b.network.nodes[shop].connect(actor,channels=['records'])
        for actor in ['a','b']:
            for shop in ['s1','s2']:
                first=await self.call(actor,shop,'service.actions','perform',{'action':'buy','key':'same'},channels=['service']);self.assertEqual(first['status'],'ok',first)
                retry=await self.call(actor,shop,'service.actions','perform',{'action':'buy','key':'same'},channels=['service']);self.assertTrue(retry['data']['duplicate'],retry)
            self.assertEqual(await self.values(actor),{'gold':6,'wood':2,'ap':8})
        for shop in ['s1','s2']:self.assertEqual(await self.values(shop),{'gold':4,'wood':2})
    async def test_two_recipients_each_charge_once_and_private_read_stays_private(self):
        for actor in ['a','b','c']:self.node(actor,True)
        self.mount('a','records.store',{'initial':{'ap':3},'minimum':{'ap':0}})
        for box in ['b','c']:
            self.mount(box,'messages.box',{'send_cost':1,'read_policy':'self'},channels=['records','chat'])
            self.b.network.nodes['a'].connect(box,channels=['chat']);self.b.network.nodes[box].connect('a',channels=['records','chat'])
            first=await self.call('a',box,'messages.box','send',{'text':'你好','key':'same'},channels=['chat']);self.assertEqual(first['status'],'ok',first)
            retry=await self.call('a',box,'messages.box','send',{'text':'你好','key':'same'},channels=['chat']);self.assertTrue(retry['data']['duplicate'],retry)
            denied=await self.call('a',box,'messages.box','read',channels=['chat']);self.assertEqual(denied['status'],'error')
            own=await self.b.modules.call(box,'messages.box','read');self.assertEqual(len(own['data']['messages']),1)
        self.assertEqual((await self.values('a'))['ap'],1)
