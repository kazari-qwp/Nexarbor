"""Requested directed graph: 1 -> 2 -> 3 -> 2 -> 4 -> 5 -> 6."""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.network import Network
from datanet.core.node_modules import NodeModules
from datanet.core.external_tools import ExternalTools
from datanet.core.async_runtime import AsyncRuntime

ROOT = Path(__file__).resolve().parents[1]


def load(name, source):
    spec=importlib.util.spec_from_file_location(name,source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class ToolCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory()
        sdk=load('collector_sdk_test',ROOT/'extensions/foundation/capabilities/module_sdk/python/datanet/studio/contract.py')
        self.manifest,self.definition=sdk.factory(ROOT/'extensions/foundation/capabilities/tool_collector')
        self.b=SimpleNamespace(network=Network(),agents={},_transaction_lock=RLock(),
            components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
        self.b.network.add_node(AgentNode('1','One',file_path=Path(self.temp.name)/'memory.md'))
        for number in range(2,7):self.b.network.add_node(Node(str(number),str(number),None))
        for origin,target in [('1','2'),('2','3'),('3','2'),('2','4'),('4','5'),('5','6')]:
            self.b.network.nodes[origin].connect(target,channels=['tools'])
        self.b.modules=NodeModules(self.b,{'tools.collector':self.definition})
        self.b.external_tools=ExternalTools(self.b)
        self.calls=[]
        async def execute(actor,name,arguments):
            self.calls.append((actor,name));return dict(actor=actor,tool=name,arguments=arguments)
        self.b.external_tools.register('test',[dict(name='tool_'+str(n),description='Tool '+str(n),
            parameters={'type':'object','additionalProperties':False}) for n in range(2,7)],execute)
        for n in range(2,7):
            self.b.network.nodes[str(n)].offered_tools=[dict(ref='test:tool_'+str(n),channels=['tools'])]
        self.mount('1',2);self.mount('3',10)

    def mount(self,node,strength):
        self.b.modules.mount(node,'tools.collector',access=dict(strength=strength,channels=['tools']))

    async def asyncTearDown(self):
        self.b.modules.clear()
        if getattr(self.b,'runtime',None):self.b.runtime.close()
        self.temp.cleanup()

    async def collect(self):
        result=await self.b.modules.call('1','tools.collector','collect')
        self.assertEqual(result['status'],'ok');return result['data']

    async def test_requested_range_two_delegates_to_range_ten(self):
        direct=[node.node_id for node,_,_ in self.b.network.walk_states('1',strength=2,channels=['tools'])]
        self.assertEqual(direct,['1','2','3','4'])
        tools=await self.collect()
        self.assertEqual({item['origin']['node_id'] for item in tools},{'2','3','4','5','6'})
        self.assertEqual(len(tools),5)
        self.assertEqual(next(t for t in tools if t['origin']['node_id']=='2')['via'],[])
        self.assertEqual(next(t for t in tools if t['origin']['node_id']=='6')['via'],['3'])
        self.assertEqual(self.calls,[])  # Collection does not execute any business tool.

    async def test_node_two_is_deduplicated_by_origin_and_reference(self):
        tools=await self.collect()
        self.assertEqual(sum(t['origin']=={'node_id':'2','tool':'test:tool_2'} for t in tools),1)
        # Equal function names on different original providers are separate tools.
        self.b.network.nodes['4'].offered_tools=[dict(ref='test:tool_2',channels=['tools'])]
        tools=await self.collect()
        self.assertEqual(sum(t['origin']['tool']=='test:tool_2' for t in tools),2)

    async def test_can_actually_invoke_six_via_three(self):
        tools=await self.collect();six=next(t for t in tools if t['origin']['node_id']=='6')
        with self.assertRaises(PermissionError):
            await self.b.external_tools.invoke('1','6','test:tool_6',{},strength=2,channels=['tools'])
        result=await self.b.modules.call('1','tools.collector','invoke',{'tool_id':six['id'],'arguments':{}})
        self.assertEqual(result['data'],{'actor':'3','tool':'tool_6','arguments':{}})
        self.assertEqual(self.calls,[('3','tool_6')])

    async def test_reducing_three_strength_removes_five_and_six(self):
        self.b.modules.unmount('3','tools.collector');self.mount('3',1)
        self.assertEqual({t['origin']['node_id'] for t in await self.collect()},{'2','3','4'})

    async def test_wrong_channel_and_unmount_remove_delegation(self):
        self.b.network.nodes['3'].interfaces.clear()
        self.b.network.nodes['3'].connect('2',channels=['other'])
        self.assertEqual({t['origin']['node_id'] for t in await self.collect()},{'2','3','4'})
        self.b.modules.unmount('3','tools.collector')
        self.assertEqual({t['origin']['node_id'] for t in await self.collect()},{'2','3','4'})

    async def test_retained_tool_and_forged_id_cannot_bypass_current_topology(self):
        six=next(t for t in await self.collect() if t['origin']['node_id']=='6')
        self.b.network.nodes['3'].interfaces.clear()
        for identifier in (six['id'],'forged'):
            result=await self.b.modules.call('1','tools.collector','invoke',{'tool_id':identifier,'arguments':{}})
            self.assertEqual(result['status'],'error')
        self.assertEqual(self.calls,[])

    async def test_host_access_requires_actual_collector_channel_and_distance(self):
        with self.assertRaises(PermissionError):
            await self.b.modules.access('1','3','tools.collector','collect',strength=1,channels=['tools'])
        with self.assertRaises(PermissionError):
            await self.b.modules.access('1','3','tools.collector','collect',strength=2,channels=['other'])
        response=await self.b.modules.access('1','3','tools.collector','collect',strength=2,channels=['tools'])
        self.assertEqual(response['status'],'ok')

    async def test_agent_gets_one_copy_and_uses_forwarded_tool(self):
        self.b.runtime=AsyncRuntime()
        executor_module=load('collector_executor_test',ROOT/'adapters/harness/studio/executor.py')
        self.b.components.rpc=lambda *args,**kwargs:None
        self.b.network.nodes['1'].execution_binding=dict(executor='harness',strength=2,channels=['tools'])
        executor=executor_module.NativeExecutor(self.b,None)
        visit=await asyncio.to_thread(executor.visit,{'actor':'1','target':'1'})
        self.assertEqual(len(visit['tools']),5)
        prepared=await asyncio.to_thread(executor.prepare,{'actor':'1'})
        acquired=[d for d in prepared['tools'] if d['name'].startswith('mod_')]
        self.assertEqual(len(acquired),5)
        self.assertFalse(any(d['name'].startswith('ext_') for d in prepared['tools']))
        six=next(d for d in acquired if 'tool_6' in d['description'])
        result=await asyncio.to_thread(executor.invoke,{'actor':'1','name':six['name'],'arguments':{}})
        self.assertEqual(result['tool'],'tool_6');self.assertEqual(result['actor'],'3')
        self.b.network.nodes['3'].interfaces.clear()
        prepared=await asyncio.to_thread(executor.prepare,{'actor':'1'})
        self.assertFalse(any(d['name']==six['name'] for d in prepared['tools']))
        self.assertEqual((await asyncio.to_thread(executor.invoke,{'actor':'1','name':six['name'],'arguments':{}}))['status'],'forbidden')

    def test_new_collector_appears_when_reopening_an_existing_v3_workspace(self):
        directory=str(Path(self.temp.name)/'reopen')
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),DATANET_PRODUCT_ROOT=str(ROOT),
            DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_PROFILE='{}')
        for enabled,expect in [(['capabilities/component_studio'],False),
                               (['capabilities/component_studio','capabilities/tool_collector'],True)]:
            env['DATANET_COMPONENT_SELECTION']=json.dumps(enabled)
            code='from datanet.core.backend import Backend; b=Backend('+repr(directory)+'); assert ("tools.collector" in b.studio.library) == '+repr(expect)+'; b.close()'
            result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
