"""Current v3 protocol invariants; no application compatibility fixtures."""
import asyncio
import tempfile
import unittest
import importlib.util
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from datanet.core.module_protocol import ModuleDefinition, ComponentResult
from datanet.core.node_modules import NodeModules
from datanet.core.service_registry import ComponentServices
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.network import Network
from datanet.core.signals import Signal, restore_records
from datanet.core.serialization import network_document, _build
from datanet.core.external_tools import ExternalTools


def definition(fn, operations=('run',), signals=(), schema=None):
    return ModuleDefinition(fn, operations=[dict(name=name, channels=['red'],
        parameters=schema or {'type':'object'}, result={}) for name in operations], signals=signals)


def backend(definitions):
    b = SimpleNamespace(network=Network(), agents={}, _transaction_lock=RLock(),
        components=SimpleNamespace(module_owners={}, module_extensions={}, enabled=set()))
    for name in ('a','b','c','hidden'): b.network.add_node(Node(name,name,None))
    b.modules = NodeModules(b, definitions); b.signals = b.network.signals
    b.external_tools = ExternalTools(b)
    return b


def mount(b, node, name, strength=0, channels=(), **kwargs):
    return b.modules.mount(node,name,access=dict(strength=strength,channels=list(channels)),**kwargs)


class Protocol(unittest.IsolatedAsyncioTestCase):
    async def test_parameter_names_cannot_collide_with_binding_internals(self):
        payload=dict(key='receipt-1',function='data',self='data',_name='not-an-operation',_spec={'parameters':{}},parameters={'nested':True})
        async def receive(ctx,activation):return ComponentResult(data=dict(operation=activation.operation,parameters=dict(activation.parameters)))
        async def forward(ctx,activation):return ComponentResult(data=await ctx.network.call('b','echo','run',dict(activation.parameters)))
        b=backend({'echo':definition(receive),'forward':definition(forward)})
        mount(b,'a','forward',strength=1,channels=['red']);mount(b,'b','echo',channels=['red'])
        b.network.nodes['a'].connect('b',channels=['red'])
        try:
            direct=await b.modules.call('b','echo','run',payload)
            self.assertEqual(direct['data']['parameters'],payload);self.assertEqual(direct['data']['operation'],'run')
            chained=await b.modules.call('a','forward','run',payload)
            self.assertEqual(chained['data']['data'],direct['data'])
        finally:await b.signals.close();b.modules.clear()

    async def test_registration_rejects_legacy_sync_and_nonstandard_signatures(self):
        for fn in (lambda ctx,activation: None,):
            with self.assertRaises(TypeError): ModuleDefinition(fn)
        async def wrong(ctx,activation,extra=None): pass
        with self.assertRaises(TypeError): ModuleDefinition(wrong)
        services=object.__new__(ComponentServices);services.module_types={}
        with self.assertRaises(TypeError): services.node_module('bad',object)
        self.assertEqual(services.module_types,{})

    async def test_result_must_have_fixed_envelope(self):
        async def execute(ctx, activation): return {'looks':'valid'}
        b=backend({'bad':definition(execute)});mount(b,'a','bad')
        with self.assertRaises(TypeError): await b.modules.call('a','bad','run')

    async def test_parameters_and_state_are_validated(self):
        async def execute(ctx, activation):
            ctx.state['count']='wrong';return ComponentResult()
        d=definition(execute,schema={'type':'object','properties':{'count':{'type':'integer'}},'additionalProperties':False})
        d.state_schema={'type':'object','properties':{'count':{'type':'integer'}}}
        b=backend({'probe':d});mount(b,'a','probe')
        with self.assertRaises(Exception): await b.modules.call('a','probe','run',{'count':'bad'})
        with self.assertRaises(Exception): await b.modules.call('a','probe','run',{'count':1})

    async def test_local_context_and_json_values_are_isolated(self):
        saved=[]
        async def execute(ctx, activation):
            saved.append(ctx)
            self.assertFalse(hasattr(ctx,'backend'));self.assertFalse(hasattr(ctx,'node'))
            self.assertFalse(hasattr(ctx,'register_tool'))
            with self.assertRaises(TypeError): activation.parameters['x']=2
            with self.assertRaises(TypeError): ctx.config['x']=2
            return ComponentResult(data=ctx.metadata())
        b=backend({'probe':definition(execute)});mount(b,'a','probe')
        result=await b.modules.call('a','probe','run',{'x':1})
        self.assertEqual(result['data']['node_id'],'a')
        with self.assertRaises(PermissionError): saved[0].metadata()

    async def test_independent_calls_start_before_wait_and_are_joined(self):
        started=set();both=asyncio.Event();finished=[]
        async def receiver(ctx, activation):
            started.add(ctx.node_id)
            if len(started)==2:both.set()
            await asyncio.wait_for(both.wait(),1)
            await asyncio.sleep(.01);finished.append(ctx.node_id)
            return ComponentResult(data=ctx.node_id)
        async def sender(ctx, activation):
            one=ctx.network.call('b','recv','run')
            two=ctx.network.call('c','recv','run')
            await asyncio.wait_for(both.wait(),1)
            return ComponentResult(data='no explicit wait')
        b=backend({'send':definition(sender),'recv':definition(receiver)})
        for n in ('b','c'):b.network.nodes['a'].connect(n,channels=['red']);mount(b,n,'recv')
        mount(b,'a','send',1,['red'])
        await b.modules.call('a','send','run')
        self.assertCountEqual(finished,['b','c'])

    async def test_callee_uses_own_grant_and_can_forward_back(self):
        async def sender(ctx, activation): return ComponentResult(data=await ctx.network.call('b','forward','run'))
        async def forward(ctx, activation):
            metadata=await ctx.network.metadata('c',channels=['blue'])
            value=await ctx.network.call('a','leaf','run')
            return ComponentResult(data=[metadata['node_id'],value['data']])
        async def leaf(ctx, activation): return ComponentResult(data=activation.source)
        b=backend({'send':definition(sender),'forward':definition(forward),'leaf':definition(leaf)})
        b.network.nodes['a'].connect('b',channels=['red'])
        b.network.nodes['b'].connect('a',channels=['red']);b.network.nodes['b'].connect('c',channels=['blue'])
        mount(b,'a','send',1,['red']);mount(b,'a','leaf');mount(b,'b','forward',1,['red','blue'])
        result=await b.modules.call('a','send','run')
        self.assertEqual(result['data']['data'],['c','b'])

    async def test_node_id_payload_never_grants_access(self):
        async def execute(ctx, activation):
            return ComponentResult(data=await ctx.network.metadata(activation.parameters['target']))
        b=backend({'probe':definition(execute)});mount(b,'a','probe',1,['red'])
        with self.assertRaises(PermissionError):await b.modules.call('a','probe','run',{'target':'hidden'})

    async def test_handled_denial_does_not_fail_callback_join(self):
        async def execute(ctx, activation):
            try:await ctx.network.call('hidden','probe','run')
            except PermissionError:return ComponentResult(data='denied')
        b=backend({'probe':definition(execute)});mount(b,'a','probe')
        self.assertEqual((await b.modules.call('a','probe','run'))['data'],'denied')

    async def test_zero_hop_access(self):
        async def first(ctx, activation): return ComponentResult(data=await ctx.network.call('a','second','run'))
        async def second(ctx, activation): return ComponentResult(data=42)
        b=backend({'first':definition(first),'second':definition(second)})
        mount(b,'a','first',0,['red']);mount(b,'a','second')
        self.assertEqual((await b.modules.call('a','first','run'))['data']['data'],42)

    async def test_access_payload_is_copied_when_request_starts(self):
        async def first(ctx, activation):
            arguments={'value':'original'}
            request=ctx.network.call('b','second','run',arguments)
            arguments['value']='changed'
            return ComponentResult(data=(await request)['data'])
        async def second(ctx, activation):return ComponentResult(data=activation.parameters['value'])
        b=backend({'first':definition(first),'second':definition(second)})
        b.network.nodes['a'].connect('b',channels=['red'])
        mount(b,'a','first',1,['red']);mount(b,'b','second')
        self.assertEqual((await b.modules.call('a','first','run'))['data'],'original')

    async def test_emitted_wave_survives_source_completion(self):
        gate=asyncio.Event();done=[]
        async def send(ctx, activation): return ComponentResult(data=ctx.network.emit(channels=['red'],strength=1,content={'hello':'wave'}))
        async def recv(ctx, activation):
            await gate.wait();done.append(activation.signal.content['hello']);return ComponentResult()
        b=backend({'send':definition(send),'recv':definition(recv,signals=['red'])})
        b.network.nodes['a'].connect('b',channels=['red']);mount(b,'a','send',1,['red']);mount(b,'b','recv')
        receipt=(await b.modules.call('a','send','run'))['data']
        self.assertEqual(done,[]);gate.set()
        report=await b.signals.wait(receipt['signal_id'])
        self.assertEqual(report['status'],'completed');self.assertEqual(done,['wave'])

    async def test_cancelling_waiter_does_not_cancel_wave(self):
        gate=asyncio.Event()
        b=backend({});b.network.nodes['a'].connect('b',channels=['red'])
        async def recv(ctx):await gate.wait();return 'ok'
        b.signals.bind('b',recv)
        signal=Signal('a',['red'],1);b.signals.emit(signal)
        task=asyncio.create_task(b.signals.wait(signal.signal_id));await asyncio.sleep(.01);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        gate.set();self.assertEqual((await b.signals.wait(signal.signal_id))['status'],'completed')

    async def test_signal_layer_barrier_joins_receiver_access(self):
        log=[];both=asyncio.Event();entered=set()
        async def execute(ctx, activation):
            if ctx.node_id in ('b','c'):
                entered.add(ctx.node_id)
                if len(entered)==2:both.set()
                await asyncio.wait_for(both.wait(),1)
                if ctx.node_id=='b':ctx.network.call('hidden','leaf','run')
                log.append(ctx.node_id)
            else:self.assertIn('leaf',log);self.assertCountEqual(log[:3],['b','c','leaf']);log.append('last')
            return ComponentResult()
        async def leaf(ctx, activation):await asyncio.sleep(.02);log.append('leaf');return ComponentResult()
        b=backend({'recv':definition(execute,signals=['red']),'leaf':definition(leaf)})
        b.network.add_node(Node('last','last',None))
        for target in ('b','c'):
            b.network.nodes['a'].connect(target,channels=['red']);b.network.nodes[target].connect('last',channels=['red']);mount(b,target,'recv',1,['red'])
        b.network.nodes['b'].connect('hidden',channels=['blue']);mount(b,'hidden','leaf')
        mount(b,'last','recv')
        b.network.nodes['b'].connect('hidden',channels=['red'])
        report=await b.signals.propagate(Signal('a',['red'],2))
        self.assertEqual(report['status'],'completed',report);self.assertEqual(log[-1],'last')

    async def test_signal_explicit_cancel_and_queued_restore(self):
        b=backend({});b.network.nodes['a'].connect('b',channels=['red'])
        async def recv(ctx):await asyncio.sleep(10)
        b.signals.bind('b',recv)
        signal=Signal('a',['red'],1);b.signals.emit(signal)
        self.assertEqual(restore_records(b.network.signal_runs)[signal.signal_id]['status'],'interrupted')
        await asyncio.sleep(.01);await b.signals.cancel(signal.signal_id)
        with self.assertRaises(asyncio.CancelledError):await b.signals.wait(signal.signal_id)
        self.assertEqual(b.signals.status(signal.signal_id)['status'],'cancelled')

    async def test_cancelled_emitter_does_not_own_wave_lifetime(self):
        emitted=asyncio.Event();finish=asyncio.Event();receipt=[]
        async def execute(ctx, activation):
            receipt.append(ctx.network.emit(channels=['red'],strength=1))
            emitted.set();await asyncio.sleep(10)
            return ComponentResult()
        b=backend({'send':definition(execute)});mount(b,'a','send',1,['red'])
        b.network.nodes['a'].connect('b',channels=['red'])
        async def recv(context):await finish.wait();return 'done'
        b.signals.bind('b',recv)
        task=asyncio.create_task(b.modules.call('a','send','run'));await emitted.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        finish.set();self.assertEqual((await b.signals.wait(receipt[0]['signal_id']))['status'],'completed')

    async def test_unmount_and_disable_revoke_saved_context(self):
        saved=[]
        async def execute(ctx, activation):saved.append(ctx);return ComponentResult()
        b=backend({'probe':definition(execute)});b.components.module_owners['probe']='test';b.components.enabled.add('test')
        mount(b,'a','probe');await b.modules.call('a','probe','run')
        b.components.enabled.clear()
        with self.assertRaises(PermissionError):await b.modules.call('a','probe','run')
        b.components.enabled.add('test');b.modules.unmount('a','probe');mount(b,'a','probe')
        with self.assertRaises(PermissionError):saved[0].metadata()

    async def test_operation_channel_requires_its_own_path(self):
        async def first(ctx, activation):return ComponentResult(data=await ctx.network.call('b','leaf','run'))
        async def leaf(ctx, activation):return ComponentResult()
        b=backend({'first':definition(first),'leaf':definition(leaf)})
        b.network.nodes['a'].connect('b',channels=['blue'])
        mount(b,'a','first',1,['blue','red']);mount(b,'b','leaf')
        with self.assertRaises(PermissionError):await b.modules.call('a','first','run')

    async def test_official_gateway_is_explicit_and_target_bounded(self):
        source=Path(__file__).resolve().parents[1]/'extensions/foundation/capabilities/network_gateway/python/datanet/abilities/network_gateway/services.py'
        spec=importlib.util.spec_from_file_location('test_official_gateway_v3',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        registry=object.__new__(ComponentServices)
        registry.module_types={};registry.module_owners={};registry.module_extensions={};registry.loading_component=None
        module.register(registry)
        b=backend(registry.module_types);b.components.module_extensions=registry.module_extensions
        b.modules.mount('a','network.gateway',access=dict(strength=0,channels=['network.extended']))
        with self.assertRaises(PermissionError):await b.modules.call('a','network.gateway','metadata',{'target':'b'})
        b.modules.unmount('a','network.gateway')
        b.modules.mount('a','network.gateway',access=dict(strength=0,channels=['network.extended'],extension={'operations':['metadata'],'targets':['b']}))
        self.assertEqual((await b.modules.call('a','network.gateway','metadata',{'target':'b'}))['data']['node_id'],'b')
        with self.assertRaises(PermissionError):await b.modules.call('a','network.gateway','metadata',{'target':'hidden'})
        with self.assertRaises(PermissionError):await b.modules.call('a','network.gateway','nodes')

    async def test_old_manifest_rejected_before_importing_source(self):
        source=Path(__file__).resolve().parents[1]/'extensions/foundation/capabilities/module_sdk/python/datanet/studio/contract.py'
        spec=importlib.util.spec_from_file_location('test_sdk_v3',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'module.json').write_text(json.dumps({'format':'nexarbor-module/v2'}))
            (folder/'module.py').write_text('raise AssertionError("Source was imported")')
            with self.assertRaisesRegex(ValueError,'v3'):module.factory(folder)


class OfferedTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.b=backend({})
        self.b.network.nodes.pop('a');self.agent=AgentNode('a','Agent',file_path=Path(self.temp.name)/'memory.md')
        self.b.network.add_node(self.agent);self.b.network.nodes['a'].connect('b',channels=['tools'])
        self.b.network.nodes['b'].offered_tools=[dict(ref='host:echo',channels=['tools'])]
        async def execute(actor,name,arguments):return dict(actor=actor,value=arguments['value'])
        self.b.external_tools.register('host',[dict(name='echo',description='Echo',parameters={'type':'object','required':['value'],'properties':{'value':{'type':'string'}},'additionalProperties':False})],execute)
    async def asyncTearDown(self):self.temp.cleanup()

    async def test_tools_only_acquired_after_visit(self):
        registry=self.b.external_tools
        self.assertEqual(registry.acquired('a',strength=1,channels=['tools']),[])
        offers=registry.visit('a','b',strength=1,channels=['tools'])
        self.assertEqual(offers[0]['ref'],'host:echo')
        self.assertEqual(len(registry.acquired('a',strength=1,channels=['tools'])),1)
        self.assertEqual(await registry.invoke('a','b','host:echo',{'value':'ok'},strength=1,channels=['tools']),{'actor':'a','value':'ok'})

    async def test_unreachable_and_spoofed_references_rejected(self):
        self.b.network.nodes['b'].offered_tools.append(dict(ref='fake:echo',channels=['tools']))
        with self.assertRaises(ValueError):self.b.external_tools.validate_node(self.b.network.nodes['b'])
        with self.assertRaises(PermissionError):await self.b.external_tools.invoke('a','b','fake:echo',{},strength=1,channels=['tools'])
        with self.assertRaises(PermissionError):self.b.external_tools.visit('a','hidden',strength=1,channels=['tools'])

    async def test_tool_removed_or_path_changed_revokes_execution(self):
        registry=self.b.external_tools;registry.visit('a','b',strength=1,channels=['tools'])
        self.agent.interfaces.clear()
        self.assertEqual(registry.acquired('a',strength=1,channels=['tools']),[])
        with self.assertRaises(PermissionError):await registry.invoke('a','b','host:echo',{'value':'x'},strength=1,channels=['tools'])
        self.agent.connect('b',channels=['tools']);self.b.network.nodes['b'].offered_tools.clear()
        with self.assertRaises(PermissionError):await registry.invoke('a','b','host:echo',{'value':'x'},strength=1,channels=['tools'])

    async def test_channels_and_schema_rechecked(self):
        with self.assertRaises(PermissionError):await self.b.external_tools.invoke('a','b','host:echo',{'value':'x'},strength=1,channels=['wrong'])
        with self.assertRaises(Exception):await self.b.external_tools.invoke('a','b','host:echo',{'value':3},strength=1,channels=['tools'])

    async def test_offers_persist_and_old_network_is_rejected(self):
        doc=network_document(self.b.network,self.temp.name)
        self.assertEqual(doc['version'],8)
        restored=_build(doc,Path(self.temp.name))
        self.assertEqual(restored.nodes['b'].offered_tools,self.b.network.nodes['b'].offered_tools)
        doc['version']=7
        with self.assertRaises(ValueError):_build(doc,Path(self.temp.name))


if __name__=='__main__':unittest.main()
