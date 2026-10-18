"""Authorization regressions for node-local modules, not town application tests."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from datanet.core.node import Node
from datanet.core.network import Network
from datanet.core.node_modules import NodeModule, NodeModules, validate_modules
from datanet.core.signals import Signal
from datanet.core.access_budget import access_context


class Probe(NodeModule):
    def install(self):
        self.operation('inspect', self.inspect_local)
        self.operation('query', self.query)
        self.operation('forward', self.forward, channels=['red', 'blue', 'network.extended'])
        self.operation('value', self.value, channels=['red'])
        self.operation('local', self.value)
        self.operation('who', lambda:self.context.caller_id, channels=['red'])
        self.operation('emit', self.emit)
        self.operation('tool_call', self.tool_call)
        self.operation('tools', lambda target: self.context.network.tools(target))
        self.operation('inputs', self.context.update_inputs)
        self.operation('publish', self.context.publish_metadata)
        self.tool('count', self.count, description='counter', parameters={'type':'object'}, access_channels=['red'])
    def inspect_local(self):
        return dict(metadata=self.context.metadata(), caller=self.context.caller_id,
                    host=hasattr(self, 'backend') or hasattr(self, 'node') or hasattr(self.context, 'backend'),
                    extended=hasattr(self.context, 'extended'))
    def value(self): return self.state
    def query(self, **options): return self.context.network.nodes(**options)
    async def forward(self, target, module='probe', operation='value', arguments=None):
        return await self.context.network.call(target, module, operation, arguments)
    async def emit(self, **options): return await self.context.network.emit(**options)
    async def tool_call(self, target, tool): return await self.context.network.invoke(target, tool)
    def count(self):
        self.state['n'] = self.state.get('n', 0) + 1
        return self.state['n']


def make():
    backend = SimpleNamespace(network=Network(), _transaction_lock=RLock(),
        components=SimpleNamespace(module_owners={'probe':'test'}, enabled={'test'}, module_extensions={}))
    for key in ('a','b','c','hidden'): backend.network.add_node(Node(key,key,None))
    backend.modules = NodeModules(backend, {'probe':Probe})
    backend.dispatch = lambda *args: None
    backend.signals = backend.network.signals
    return backend


def mount(backend, node, strength=0, channels=(), name='probe', **kwargs):
    return backend.modules.mount(node,name,access=dict(strength=strength,channels=list(channels)),**kwargs)


class LocalModuleTests(unittest.IsolatedAsyncioTestCase):
    def test_context_has_no_raw_objects_and_default_is_local(self):
        b=make(); m=mount(b,'a',config={'x':1})
        self.assertFalse(b.modules.call('a','probe','inspect')['host'])
        self.assertFalse(b.modules.call('a','probe','inspect')['extended'])
        self.assertEqual([x['metadata']['node_id'] for x in b.modules.call('a','probe','query')],['a'])
        with self.assertRaises(TypeError): m.config['x']=3
        for attr in ('backend','node','application','directory'): self.assertFalse(hasattr(m.context,attr))
        with self.assertRaises(PermissionError): m.context.metadata()

    def test_channel_and_strength_requests_cannot_expand(self):
        b=make(); b.network.nodes['a'].connect('b',channels=['red']);b.network.nodes['b'].connect('c',channels=['red'])
        mount(b,'a',1,['red'])
        result=b.modules.call('a','probe','query');self.assertEqual([x['metadata']['node_id'] for x in result],['a','b'])
        result[1]['metadata']['name']='tamper';self.assertEqual(b.network.nodes['b'].name,'b')
        for args in ({'strength':2},{'channels':['blue']},{'strength':-1}):
            with self.assertRaises((ValueError,PermissionError)): b.modules.call('a','probe','query',args)
        self.assertEqual(len(b.modules.call('a','probe','query',{'strength':0})),1)

    async def test_remote_calls_require_declared_channel_and_copy_state(self):
        b=make();b.network.nodes['a'].connect('b',channels=['red']);mount(b,'a',2,['red']);m=mount(b,'b',9,['red'],state={'n':7})
        value=await b.modules.call('a','probe','forward',{'target':'b'});value['n']=99;self.assertEqual(m.state['n'],7)
        self.assertEqual(await b.modules.call('a','probe','forward',{'target':'b','operation':'who'}),'a')
        with self.assertRaises(PermissionError): await b.modules.call('a','probe','forward',{'target':'hidden'})
        with self.assertRaises(PermissionError): await b.modules.call('a','probe','forward',{'target':'b','operation':'local'})

    async def test_sibling_calls_can_reuse_endpoint_but_recursive_return_is_blocked(self):
        class Twice(Probe):
            def install(self):
                super().install();self.operation('twice',self.twice)
            async def twice(self):
                first=await self.context.network.call('b','probe','value')
                second=await self.context.network.call('b','probe','value')
                return [first,second]
        b=make();b.modules.factories['probe']=Twice
        b.network.nodes['a'].connect('b',channels=['red']);b.network.nodes['b'].connect('a',channels=['red'])
        mount(b,'a',4,['red']);mount(b,'b',4,['red'],state={'n':3})
        self.assertEqual(await b.modules.call('a','probe','twice'),[{'n':3},{'n':3}])
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{'target':'b','operation':'forward','arguments':{'target':'a'}})

    def test_synchronous_public_entry_completes_async_tool(self):
        from datanet.core.tool_access import invoke_tool
        class AsyncTool(Probe):
            def install(self):
                super().install()
                self.tool('delayed',self.delayed,description='async',parameters={'type':'object'},access_channels=['red'])
            async def delayed(self):
                await asyncio.sleep(0);self.state['done']=True;return self.context.metadata()['node_id']
        b=make();b.modules.factories['probe']=AsyncTool;b.network.nodes['a'].connect('b',channels=['red'])
        m=mount(b,'b',3,['red'])
        result=invoke_tool(b.network,'a','b','delayed',{},strength=2)
        self.assertEqual(result.items,[{'result':'b'}]);self.assertTrue(m.state['done'])

    async def test_same_node_operations_are_available_without_remote_authority(self):
        b=make();mount(b,'a',state={'n':2})
        result=await b.modules.call('a','probe','forward',{'target':'a','operation':'local'})
        self.assertEqual(result,{'n':2})

    async def test_nested_call_cannot_reset_strength_or_expand_channels(self):
        b=make();b.network.nodes['a'].connect('b',channels=['red']);b.network.nodes['b'].connect('c',channels=['red','blue'])
        mount(b,'a',1,['red']);mount(b,'b',99,['red','blue']);mount(b,'c',99,['red','blue'])
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{'target':'b','operation':'forward','arguments':{'target':'c'}})
        b.modules.unmount('a','probe');mount(b,'a',5,['red'])
        b.network.nodes['b'].interfaces.clear();b.network.nodes['b'].connect('c',channels=['blue'])
        with self.assertRaises(PermissionError):
            await b.modules.call('a','probe','forward',{'target':'b','operation':'forward','arguments':{'target':'c'}})

    async def test_tools_obey_same_budget_and_do_not_leak_hidden_tools(self):
        b=make();b.network.nodes['a'].connect('b',channels=['red']);mount(b,'a',2,['red']);mount(b,'b',2,['red'])
        self.assertEqual([x['name'] for x in b.modules.call('a','probe','tools',{'target':'b'})],['count'])
        self.assertEqual(await b.modules.call('a','probe','tool_call',{'target':'b','tool':'count'}),1)
        self.assertEqual(await b.modules.call('a','probe','tool_call',{'target':'a','tool':'count'}),1)
        with self.assertRaises(PermissionError):b.modules.call('a','probe','tools',{'target':'hidden'})

    def test_old_constructor_and_old_saved_spec_are_rejected(self):
        with self.assertRaises(ValueError): validate_modules({'x':{'config':{},'state':{}}})
        b=make();b.modules.factories['old']=lambda backend,node,config,state:None
        with self.assertRaises(TypeError):b.modules.mount('a','old')
        self.assertNotIn('old',b.network.nodes['a'].modules)

    def test_unmount_remount_does_not_reactivate_old_tool_or_context(self):
        b=make();old=mount(b,'a',1,['red']);fn=b.network.nodes['a'].tools['count'];ctx=old.context
        self.assertEqual(fn(),1);b.modules.unmount('a','probe');mount(b,'a',1,['red'])
        with self.assertRaises(PermissionError):fn()
        with self.assertRaises(PermissionError):ctx.metadata()
        self.assertEqual(b.network.nodes['a'].tools['count'](),1)

    async def test_delayed_request_rechecks_topology_and_scope(self):
        b=make();b.network.nodes['a'].connect('b',channels=['red']);m=mount(b,'a',2,['red']);mount(b,'b',2,['red'])
        pending=m.context.network.call('b','probe','value')
        with self.assertRaises(PermissionError):await pending
        b.network.nodes['a'].interfaces.clear()
        with self.assertRaises(PermissionError):await b.modules.call('a','probe','forward',{'target':'b'})

    def test_module_cannot_claim_extended_authority(self):
        b=make()
        with self.assertRaises(PermissionError):b.modules.mount('a','probe',access={'strength':0,'channels':[],
            'extension':{'operations':['nodes'],'targets':['*']}})

    def test_input_source_is_owned_and_file_paths_are_rejected(self):
        from datanet.core.agent_node import AgentNode
        with tempfile.TemporaryDirectory() as directory:
            b=make();b.network.nodes['a']=AgentNode('a','a',file_path=Path(directory)/'memory.md');mount(b,'a')
            b.modules.call('a','probe','inputs',{'patch':{'system_prompt':'hello'}})
            self.assertIn('module:probe',b.network.nodes['a'].inputs.snapshot())
            with self.assertRaises(PermissionError):b.modules.call('a','probe','inputs',{'patch':{'system_prompt':{'file':'C:/secret'}}})

    def test_metadata_namespace_and_revocation(self):
        b=make();mount(b,'a');b.modules.call('a','probe','publish',{'fields':{'role':'miner'}})
        self.assertEqual(b.network.get_metadata('a')['extensions']['probe'],{'role':'miner'})
        self.assertNotIn('extensions',b.network.get_metadata('b'))
        b.modules.unmount('a','probe');self.assertNotIn('extensions',b.network.get_metadata('a'))

    def test_disable_hides_published_metadata_even_if_module_changes_owner_attribute(self):
        b=make();m=mount(b,'a');b.modules.call('a','probe','publish',{'fields':{'role':'miner'}})
        m.owner=None;b.components.enabled.clear()
        self.assertNotIn('extensions',b.network.get_metadata('a'))
        with self.assertRaises(PermissionError):b.network.nodes['a'].tools['count']()

    def test_cleanup_error_still_revokes_all_modules(self):
        class BadClose(Probe):
            def close(self):raise RuntimeError('cleanup failed')
        b=make();mount(b,'a');b.modules.factories['bad']=BadClose;mount(b,'b',name='bad')
        fn=b.network.nodes['a'].tools['count']
        with self.assertRaisesRegex(RuntimeError,'cleanup failed'):b.modules.clear()
        self.assertEqual(b.modules.instances,{})
        self.assertNotIn('count',b.network.nodes['a'].tools);self.assertNotIn('count',b.network.nodes['b'].tools)
        with self.assertRaises(PermissionError):fn()

    async def test_signal_has_no_network_and_receiver_does_not_gain_sender_channels(self):
        class Receiver(Probe):
            def install(self):
                super().install();self.receive(['tick'],self.tick)
            def tick(self,context):
                self.state['raw_network']=hasattr(context,'network')
                self.state['seen']=[x['metadata']['node_id'] for x in self.context.network.nodes()]
                try:self.context.network.nodes(channels=['secret'])
                except PermissionError:self.state['blocked']=True
                return self.state
        b=make();b.modules.factories['probe']=Receiver
        b.network.nodes['a'].connect('b',channels=['tick']);b.network.nodes['b'].connect('c',channels=['red'])
        m=mount(b,'b',1,['red'])
        report=await b.signals.propagate(Signal('a',['tick','secret'],2))
        self.assertEqual(report['status'],'completed');self.assertFalse(m.state['raw_network'])
        self.assertEqual(m.state['seen'],['b','c']);self.assertTrue(m.state['blocked'])

    async def test_emit_uses_own_origin_channels_and_returns_only_receipt(self):
        b=make();b.network.nodes['a'].connect('b',channels=['red']);mount(b,'a',2,['red'])
        receipt=await b.modules.call('a','probe','emit',{'channels':['red'],'content':{'x':1}})
        self.assertEqual(receipt['status'],'completed');self.assertNotIn('deliveries',receipt)
        with self.assertRaises(PermissionError):await b.modules.call('a','probe','emit',{'channels':['blue']})
        with self.assertRaises(PermissionError):await b.modules.call('a','probe','emit',{'channels':['red'],'origin':'hidden'})

    async def test_callback_authority_expires_in_background_tasks(self):
        gate=asyncio.Event();tasks=[]
        class Background(Probe):
            def install(self):
                super().install();self.operation('start',self.start)
            def start(self):
                async def later():
                    await gate.wait()
                    return self.context.network.nodes()
                tasks.append(asyncio.create_task(later()))
        b=make();b.modules.factories['probe']=Background;mount(b,'a',2,['red'])
        b.modules.call('a','probe','start');gate.set()
        with self.assertRaises(PermissionError):await tasks[0]

    async def test_revocation_during_async_callback_and_remount(self):
        entered=asyncio.Event();resume=asyncio.Event()
        class Waiting(Probe):
            def install(self):
                super().install();self.operation('wait',self.wait)
            async def wait(self):
                entered.set();await resume.wait();return self.context.metadata()
        b=make();b.modules.factories['probe']=Waiting;mount(b,'a')
        task=asyncio.create_task(b.modules.call('a','probe','wait'));await entered.wait()
        b.modules.unmount('a','probe');mount(b,'a');resume.set()
        with self.assertRaises(PermissionError):await task

    async def test_signal_layers_run_concurrently_and_join_before_forwarding(self):
        workers=[];started=asyncio.Event()
        class Tick(NodeModule):
            def install(self):self.receive(['tick'],self.tick)
            async def tick(self,context):
                self.assert_no_network=hasattr(context,'network')
                if self.context.node_id in ('b','c'):
                    workers.append(self.context.node_id)
                    if len(workers)==2:started.set()
                    await asyncio.wait_for(started.wait(),.5)
                    self.state['done']=True
                elif self.context.node_id=='hidden':self.state['joined']=len(workers)==2
        b=make();b.modules.factories['tick']=Tick
        for key in ('b','c','hidden'):mount(b,key,name='tick')
        for target in ('b','c'):
            b.network.nodes['a'].connect(target,channels=['tick'])
            b.network.nodes[target].connect('hidden',channels=['tick'])
        report=await b.signals.propagate(Signal('a',['tick'],4))
        self.assertEqual(report['status'],'completed');self.assertEqual(report['layers'],[['b','c'],['hidden']])
        self.assertTrue(b.modules.get('hidden','tick').state['joined'])

    async def test_public_async_tool_call_keeps_budget_and_awaits_completion(self):
        from datanet.core.tool_access import invoke_tool_async
        class AsyncTool(Probe):
            def install(self):
                super().install()
                self.tool('lookup',self.lookup,description='lookup',parameters={'type':'object'},access_channels=['red'])
            async def lookup(self):
                await asyncio.sleep(0)
                return self.context.network.nodes()
        b=make();b.modules.factories['probe']=AsyncTool
        b.network.nodes['a'].connect('b',channels=['red']);b.network.nodes['b'].connect('c',channels=['red'])
        mount(b,'b',99,['red'])
        result=await invoke_tool_async(b.network,'a','b','lookup',{},strength=1)
        self.assertEqual([x['metadata']['node_id'] for x in result.items[0]['result']],['b'])


if __name__=='__main__':unittest.main()
