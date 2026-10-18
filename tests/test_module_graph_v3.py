"""Real LangGraph scheduling through the current local component API."""
import asyncio
from copy import deepcopy
from pathlib import Path
from pkgutil import extend_path
import sys
from threading import RLock
from types import SimpleNamespace
import unittest
import datanet
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.node_modules import NodeModules
from datanet.core.module_protocol import ModuleDefinition, ComponentResult
from datanet.core.json_values import thaw
from datanet.core.signals import Signal
from test_tool_collector import load

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extensions/foundation/capabilities/langgraph_backend/python'))
datanet.__path__=extend_path(datanet.__path__,datanet.__name__)


def call(id, operation='echo', **arguments):
    return dict(type='call',id=id,operation=operation,arguments=arguments)


class ModuleGraphTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        sdk=load('graph_sdk_test',ROOT/'extensions/foundation/capabilities/module_sdk/python/datanet/studio/contract.py')
        self.manifest,self.definition=sdk.factory(ROOT/'extensions/foundation/capabilities/module_graph')
        self.b=SimpleNamespace(network=Network(),_transaction_lock=RLock(),
            components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
        for node in ('flow','left','right','origin','after'):self.b.network.add_node(Node(node,node,None))
        for node in ('left','right'):self.b.network.nodes['flow'].connect(node,channels=['work'])
        self.calls=[]
        async def default(ctx,activation):return ComponentResult(data=thaw(activation.parameters))
        self.handler=default
        async def execute(ctx, activation):
            self.calls.append((ctx.node_id,thaw(activation.parameters)))
            return await self.handler(ctx,activation)
        worker=ModuleDefinition(execute,operations=[dict(name='run',channels=['work'],parameters={'type':'object'},result={})])
        self.b.modules=NodeModules(self.b,{'modules.executor':self.definition,'work':worker})
        for node in ('left','right'):self.b.modules.mount(node,'work')
        self.b.signals=self.b.network.signals

    async def asyncTearDown(self):
        await self.b.signals.close();self.b.modules.clear()

    def mount(self,graph,**extra):
        config=dict(operations={name:dict(node=node,module='work',operation='run') for name,node in [('echo','left'),('other','right')]},
            graphs={'main':graph},signal_channels=['tick'],on_signal=[],timeout_seconds=5)
        config.update(extra)
        self.b.modules.mount('flow','modules.executor',config,access=dict(strength=1,channels=['work']))

    async def run_graph(self,input=None):
        return await self.b.modules.call('flow','modules.executor','run',dict(input={} if input is None else input))

    async def test_same_module_repeated_and_different_instances(self):
        self.mount(dict(type='sequence',steps=[call('first',value={'$ref':'/event/input/value'}),
            call('second',value={'$ref':'/results/first/value/data/value'}),call('third','other',done=True)]))
        result=await self.run_graph({'value':7})
        self.assertEqual(self.calls,[('left',{'value':7}),('left',{'value':7}),('right',{'done':True})])
        self.assertEqual(result['data']['executions'][0]['results']['second']['value']['data'],{'value':7})

    async def test_real_langgraph_parallel_branch_and_join(self):
        from datanet.abilities.langgraph_backend.backend import compile_graph
        self.assertTrue(type(compile_graph(dict(type='sequence',steps=[]),None)).__module__.startswith('langgraph.'))
        entered=set();both=asyncio.Event();finished=[]
        async def handler(ctx, activation):
            label=activation.parameters['label']
            if label in ('slow','selected'):
                entered.add(label)
                if len(entered)==2:both.set()
                await asyncio.wait_for(both.wait(),1)
                await asyncio.sleep(.03 if label=='slow' else .01)
            if label=='join':self.assertCountEqual(finished,['slow','selected'])
            finished.append(label);return ComponentResult(data=label)
        self.handler=handler
        self.mount(dict(type='sequence',steps=[dict(type='parallel',steps=[call('slow',label='slow'),
            dict(type='branch',select={'$ref':'/event/input/choice'},cases={'yes':call('selected','other',label='selected')},default=call('unused',label='unused'))]),call('join',label='join')]))
        result=await self.run_graph({'choice':'yes'})
        self.assertEqual(result['status'],'ok');self.assertNotIn('unused',finished);self.assertEqual(finished[-1],'join')

    async def test_branch_default_and_escaped_json_pointer(self):
        self.mount(dict(type='sequence',steps=[call('initial',**{'a/b':{'~name':'unknown'}}),
            dict(type='branch',select={'$ref':'/results/initial/value/data/a~1b/~0name'},cases={'yes':call('yes',value=True)},default=call('no',value=False))]))
        result=await self.run_graph();self.assertIn('no',result['data']['executions'][0]['results'])

    async def test_boolean_and_null_branch_keys_use_json_spelling(self):
        self.mount(dict(type='branch',select={'$ref':'/event/input/value'},cases={'true':call('truth'),
            'false':call('falsehood'),'null':call('nothing')},default=call('fallback')))
        for value,key in [(True,'truth'),(False,'falsehood'),(None,'nothing')]:
            result=await self.run_graph({'value':value})
            self.assertEqual(set(result['data']['executions'][0]['results']),{key})

    async def test_signal_match_is_passive_and_blocks_next_layer(self):
        self.mount(call('work',value={'$ref':'/event/input/value'}),
            on_signal=[dict(graph='main',kind='world.tick',where={'/input/enabled':True})])
        self.b.network.nodes['origin'].connect('flow',channels=['tick'])
        self.b.network.nodes['flow'].connect('after',channels=['tick'])
        async def after(context):self.assertEqual(self.calls,[('left',{'value':9})]);return 'ready'
        self.b.signals.bind('after',after)
        # Wrong kind / predicate produce a relay response without running the graph.
        for kind,payload in [('other',{'enabled':True}),('world.tick',{'enabled':False})]:
            report=await self.b.signals.propagate(Signal('origin',['tick'],1,kind=kind,content=payload))
            self.assertEqual(report['status'],'completed');self.assertEqual(self.calls,[])
        report=await self.b.signals.propagate(Signal('origin',['tick'],2,kind='world.tick',content={'enabled':True,'value':9}))
        self.assertEqual(report['status'],'completed',report)
        self.assertEqual(report['layers'],[['flow'],['after']])

    async def test_configured_signal_channel_is_per_instance(self):
        self.mount(call('work'),signal_channels=['custom'],on_signal=[dict(graph='main')])
        self.b.network.nodes['origin'].connect('flow',channels=['custom','tick'])
        await self.b.signals.propagate(Signal('origin',['tick'],1))
        self.assertEqual(self.calls,[])
        await self.b.signals.propagate(Signal('origin',['custom'],1))
        self.assertEqual(len(self.calls),1)

    async def test_access_and_signal_do_not_grant_missing_network_authority(self):
        self.mount(call('work'))
        self.b.network.nodes['flow'].interfaces.clear()
        with self.assertRaises(PermissionError):await self.run_graph()
        self.assertEqual(self.calls,[])
        self.b.network.nodes['origin'].connect('flow',channels=['tick'])
        # Rebind with a matching rule, keeping its missing network path.
        config=deepcopy(self.b.network.nodes['flow'].modules['modules.executor']['config'])
        self.b.modules.unmount('flow','modules.executor');config['on_signal']=[dict(graph='main')]
        self.b.modules.mount('flow','modules.executor',config,access=dict(strength=1,channels=['work']))
        report=await self.b.signals.propagate(Signal('origin',['tick'],1))
        self.assertEqual(report['status'],'failed');self.assertEqual(self.calls,[])

    async def test_invalid_graph_is_rejected_before_effects(self):
        self.mount(dict(type='sequence',steps=[call('duplicate'),call('duplicate')]))
        with self.assertRaises(ValueError):await self.run_graph()
        self.assertEqual(self.calls,[])

    async def test_error_stops_or_can_be_branched_explicitly(self):
        async def fail(ctx,activation):return ComponentResult(status='error',error='expected failure')
        self.handler=fail
        self.mount(dict(type='sequence',steps=[call('failure'),call('not_run','other')]))
        with self.assertRaisesRegex(RuntimeError,'expected failure'):await self.run_graph()
        self.assertEqual(len(self.calls),1)
        config=deepcopy(self.b.network.nodes['flow'].modules['modules.executor']['config'])
        self.b.modules.unmount('flow','modules.executor');self.calls.clear()
        config['operations']['echo']['require_success']=False
        config['graphs']['main']=dict(type='sequence',steps=[call('failure'),dict(type='branch',select={'$ref':'/results/failure/value/status'},
            cases={'error':call('handle','other')},default=call('unexpected','other'))])
        async def handler(ctx,activation):return await fail(ctx,activation) if ctx.node_id=='left' else ComponentResult(data='handled')
        self.handler=handler
        self.b.modules.mount('flow','modules.executor',config,access=dict(strength=1,channels=['work']))
        result=await self.run_graph();self.assertEqual(result['data']['executions'][0]['results']['handle']['value']['data'],'handled')

    async def test_concurrent_invocations_have_separate_results(self):
        self.mount(call('one',value={'$ref':'/event/input/value'}))
        a,b=await asyncio.gather(self.run_graph({'value':'a'}),self.run_graph({'value':'b'}))
        self.assertEqual(a['data']['executions'][0]['results']['one']['value']['data'],{'value':'a'})
        self.assertEqual(b['data']['executions'][0]['results']['one']['value']['data'],{'value':'b'})

    async def test_timeout_cancels_module_access(self):
        cancelled=asyncio.Event()
        async def handler(ctx,activation):
            try:await asyncio.sleep(10)
            finally:cancelled.set()
            return ComponentResult()
        self.handler=handler;self.mount(call('slow'),timeout_seconds=.05)
        with self.assertRaises(TimeoutError):await self.run_graph()
        self.assertTrue(cancelled.is_set());self.assertEqual(self.b.modules.executing,0)


if __name__=='__main__':unittest.main()
