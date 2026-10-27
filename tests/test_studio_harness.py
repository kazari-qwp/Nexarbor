"""制作副本在真实节点、信号、执行器和冷重开上的行为。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.studio.testing import ModuleHarness
from app.studio.network_testing import NetworkHarness
from tests.test_studio_project_modules import SOURCE,ROOT

class HarnessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(prefix='studio-harness-source-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup);self.source=Path(self.temp.name)
        spec=dict(format='nexarbor-module/v4',id='counter',name='计数',description='增加计数',entry='module.py:Counter',requires=[],node_types=['node','agent'],config_schema={},state_schema={},operations=[dict(name='increment',parameters={'type':'object','properties':{'amount':{'type':'integer'}},'additionalProperties':False},result={})],agent_tools=[dict(id='increment',name='计数',operation='increment')],signals=['tick'])
        (self.source/'module.json').write_text(json.dumps(spec),encoding='utf-8')
        (self.source/'module.py').write_text(SOURCE+"\n    async def on_signal(self,context):\n        self.increment(context.signal.content['amount'])\n",encoding='utf-8')
        self.h=ModuleHarness(self.source);self.addAsyncCleanup(self.h.close)

    async def test_real_access_channel_denial_signal_and_cold_restore(self):
        h=self.h;h.add_node('a');h.add_node('b');h.mount('b');h.connect('a','b',channels=['route','tick'])
        with self.assertRaises(PermissionError):await h.call('b','increment',{'amount':100},actor='a',channels=['blocked'])
        self.assertEqual((await h.call('b','increment',{'amount':2},actor='a',channels=['route']))['data'],{'count':2})
        report=await h.emit('a',['tick'],content={'amount':3})
        self.assertEqual(report['status'],'completed')
        await h.restart()
        self.assertEqual((await h.call('b','increment',{'amount':1}))['data'],{'count':6})

    async def test_native_prepare_context_ack_and_model_tools(self):
        h=self.h;h.add_node('agent',agent=True);h.mount('agent');h.bind_agent('agent',{'executor':'harness','strength':2,'channels':[]})
        h.apply_context('agent',{'format':'nexarbor-context/v1','patch':{'inputs':[{'id':'one','text':'只执行已发布工具'}]}},source='test:event')
        view=await h.prepare_agent('agent');self.assertEqual(view['inputs'][0]['text'],'只执行已发布工具')
        name=next(tool['name'] for tool in view['tools'] if tool['description'].endswith('计数'))
        self.assertEqual(await h.agent_tool('agent',name,{'amount':4}),{'count':4})
        await h.acknowledge_agent('agent',view['inputs']);self.assertEqual((await h.prepare_agent('agent'))['inputs'],[])
        with self.assertRaises(PermissionError):await h.agent_tool('agent','invented',{})

    async def test_real_text_port_void_receipt_and_no_external_replacement(self):
        h=self.h;h.add_node('a');h.add_node('b');h.add_text('file','真实文件');h.connect('a','b',channels=['read'])
        h.register_readonly_ports();h.offer('b','runtime:read_text',['read'])
        result=await h.invoke('a','b','runtime:read_text',{'path':'data/file.md'},channels=['read'])
        self.assertEqual(result['text'],'真实文件')
        async def execute(actor,name,args):return None
        h.register_tools('test',[{'name':'empty','parameters':{'type':'object'}}],execute);h.offer('b','test:empty',['read'])
        self.assertIsNone(await h.invoke('a','b','test:empty',channels=['read']))
        with self.assertRaisesRegex(ValueError,'register_agent'):h.register_tools('runtime',[{'name':'agent_run'}],execute)

    async def test_network_fixture_keeps_actual_binding_and_persisted_module_tools(self):
        h=self.h;h.add_node('a',agent=True);h.mount('a');h.bind_agent('a',{'executor':'harness','strength':2,'channels':[]})
        fixture=self.source/'fixture';fixture.mkdir();(fixture/'initial.json').write_text(json.dumps(h.backend.snapshot()),encoding='utf-8')
        (fixture/'setup.json').write_text(json.dumps({'modules':{'counter':str(self.source)}}),encoding='utf-8')
        network=NetworkHarness(fixture);self.addAsyncCleanup(network.close)
        self.assertEqual((await network.call('a','a','counter','increment',{'amount':5}))['data'],{'count':5})
        await network.restart();self.assertEqual((await network.call('a','a','counter','increment',{'amount':2}))['data'],{'count':7})
        self.assertTrue((await network.prepare_agent('a'))['tools'])
