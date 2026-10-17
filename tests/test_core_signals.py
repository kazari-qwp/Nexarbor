"""New core signal contracts. Deliberately no legacy application fixtures."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import asdict,FrozenInstanceError
from types import SimpleNamespace
from datanet.core.interface import Interface,InterfaceMetadata
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.text_node import TextFileNode
from datanet.core.network import Network
from datanet.core.signals import Signal
from datanet.core.pulse_node import PulseNode
from datanet.core.signal_runtime import SignalRuntime
from datanet.core.serialization import save_network,load_network,_build
from datanet.core.access_budget import active_agent


def add(network,*ids):
    for id in ids:network.add_node(Node(id,id,None))

def link(network,source,target,channels=('tick',),**metadata):
    edge=Interface(target,dict(channels=channels,**metadata))
    network.nodes[source].interfaces.append(edge)
    return edge

class ValueTests(unittest.TestCase):
    def test_metadata_and_signal_roundtrip_are_immutable(self):
        edge=Interface('target',dict(channels=['A','A','B'],attributes={'labels':['x']}))
        self.assertEqual(edge.metadata.channels,('A','B'))
        self.assertEqual(Interface(**asdict(edge)),edge)
        with self.assertRaises(TypeError):edge.metadata.attributes['labels']='changed'
        signal=Signal('origin',['A','A','B'],3,content={'items':[1,2]})
        restored=Signal.from_dict(json.loads(json.dumps(signal.to_dict())))
        self.assertEqual(restored,signal)
        with self.assertRaises(TypeError):signal.content['items']=[]
        with self.assertRaises(FrozenInstanceError):signal.channels=('x',)
        for bad in [[],[''],[' ']]:
            with self.assertRaises(ValueError):Signal('o',bad,3)
        with self.assertRaises(TypeError):Interface('x',threshold=1)
        with self.assertRaises(TypeError):Interface('x',{'unknown':True})
        with self.assertRaises(TypeError):Interface('x',{'visibility':'private'})
        with self.assertRaises(ValueError):Interface('x',{'threshold':True})
        with self.assertRaises(ValueError):Signal('o',['x'],float('nan'))

    def test_new_core_formats_pulse_metadata_and_old_format_rejected(self):
        network=Network();network.add_node(PulseNode('pulse','Pulse',channels=['tick'],strength=3))
        add(network,'clock');link(network,'pulse','clock',channels=['tick'],attributes={'purpose':'clock'})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'network.json';save_network(network,path)
            document=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(document['version'],7)
            self.assertEqual(set(document['nodes'][0]['connections']['interfaces'][0]),{'target_node_id','metadata'})
            restored=load_network(path)
            self.assertIsInstance(restored.nodes['pulse'],PulseNode)
            self.assertEqual(restored.nodes['pulse'].channels,('tick',))
            self.assertEqual(restored.nodes['pulse'].interfaces[0].metadata.attributes['purpose'],'clock')
            for old_version in [3,4,5,6]:
                document['version']=old_version
                with self.assertRaises(ValueError):_build(document,Path(folder))

    def test_core_interface_management_and_node_creation_use_metadata(self):
        from datanet.core.interface_management import attach_interface_management_tools
        from datanet.core.node_creation import attach_node_creation_tools
        network=Network();add(network,'root','other');network.nodes['other'].management_parent_id='root'
        root=network.nodes['root'];attach_interface_management_tools(network,root,scope='descendants')
        result=root.invoke_tool('manage_interfaces', action='add', target_node_id='other', interface={'metadata': {'channels': ['tick'], 'threshold': 1}})
        self.assertEqual(result.status,'ok')
        result=root.invoke_tool('manage_interfaces', action='update', target_node_id='other', changes={'metadata': {'channels': ['changed']}})
        self.assertEqual(result.status,'ok');self.assertEqual(root.interfaces[0].metadata.channels,('changed',))
        with tempfile.TemporaryDirectory() as folder:
            attach_node_creation_tools(network,root,storage_dir=folder,allow_custom=True)
            result=root.invoke_tool('create_child_node',child_id='pulse',node_spec={'type':'pulse','parameters':{'channels':['tick'],'strength':3}})
            self.assertEqual(result.status,'ok',result.errors)
            self.assertIsInstance(network.nodes['root/pulse'],PulseNode)

    def test_metadata_without_optional_component_is_standard_and_extends_automatically(self):
        n=Network();add(n,'plain')
        node=n.nodes['plain'];base=node.standard_metadata()
        self.assertEqual(node.get_metadata(),base);self.assertEqual(n.get_metadata('plain'),base)
        n.metadata_registry.register('test',lambda id:{'example':{'x':1}})
        self.assertEqual(node.describe(include_schema=False)['extensions'],{'example':{'x':1}})
        self.assertEqual(n.get_metadata('plain')['name'],'plain')
        n.metadata_registry.unregister('test');self.assertEqual(node.get_metadata(),base)

class PropagationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.runtimes=[]
    def runtime(self,n,**options):
        runtime=SignalRuntime(n,**options);self.runtimes.append(runtime);return runtime
    async def asyncTearDown(self):
        for r in self.runtimes:await r.close()

    async def test_channels_or_remain_unchanged_and_domains_are_filtered(self):
        n=Network();add(n,'source','a','b','private','wrong')
        link(n,'source','a',channels=['A']);link(n,'a','b',channels=['B'])
        link(n,'source','private',channels=['private']);link(n,'source','wrong',channels=['C'])
        r=self.runtime(n);seen=[]
        async def handler(c):seen.append((c.delivery.node_id,c.signal.channels));return {'ok':True}
        for id in ['a','b','private','wrong']:r.bind(id,handler)
        report=await r.propagate(Signal('source',['A','B'],3))
        self.assertEqual(seen,[('a',('A','B')),('b',('A','B'))]);self.assertEqual(report['status'],'completed')
        self.assertNotIn('private',[node.node_id for node,_ in n.walk('source',channels=('A',),strength=3)])
        self.assertIn('private',[node.node_id for node,_ in n.walk('source',channels=('private',),strength=3)])

    async def test_each_layer_parallel_but_next_waits_for_entire_layer(self):
        n=Network();add(n,'s','clock','a','b','sink')
        link(n,'s','clock');link(n,'clock','a');link(n,'clock','b');link(n,'a','sink');link(n,'b','sink')
        r=self.runtime(n);events=[];started=set();both=asyncio.Event()
        async def handler(c):
            id=c.delivery.node_id;events.append(('start',id))
            if id in ['a','b']:
                started.add(id)
                if len(started)==2:both.set()
                await asyncio.wait_for(both.wait(),.5)
                if id=='a':await asyncio.sleep(.02)
            if id=='sink':self.assertIn(('end','a'),events);self.assertIn(('end','b'),events)
            events.append(('end',id))
        for id in ['clock','a','b','sink']:r.bind(id,handler)
        report=await r.propagate(Signal('s',['tick'],4))
        self.assertEqual(report['layers'],[['clock'],['a','b'],['sink']])
        self.assertEqual(sum(e==('start','sink') for e in events),1)
        sink=next(d for d in report['deliveries'] if d['node_id']=='sink')
        self.assertEqual(set(sink['parents']),{'a','b'});self.assertEqual(sink['strength'],1)

    async def test_no_activation_filter_and_agent_without_response_is_a_relay(self):
        with tempfile.TemporaryDirectory() as folder:
            n=Network();add(n,'s','sink');n.add_node(AgentNode('a','Agent',file_path=Path(folder)/'a.md'))
            link(n,'s','a');link(n,'a','sink');r=self.runtime(n);seen=[]
            async def handler(c):seen.append(c.delivery.node_id)
            r.bind('sink',handler)
            report=await r.propagate(Signal('s',['tick'],3))
            self.assertEqual(seen,['sink']);self.assertEqual(report['deliveries'][0]['status'],'relay')
            with self.assertRaises(TypeError):Signal('s',['tick'],3,activation={})
            with self.assertRaises(TypeError):PulseNode('p','Pulse',activation={})

    async def test_sender_identity_strength_and_receiver_authority(self):
        n=Network();add(n,'source','target');link(n,'source','target');r=self.runtime(n)
        async def handler(c):
            self.assertEqual(active_agent.get()[1],'target');self.assertEqual(active_agent.get()[0].max_signal_strength,1)
            with self.assertRaises(PermissionError):await r.propagate(Signal('source',['tick'],3))
            return None
        r.bind('target',handler,access_strength=1)
        token=active_agent.set((SimpleNamespace(max_signal_strength=2),'source'))
        try:
            with self.assertRaises(PermissionError):await r.propagate(Signal('source',['tick'],3))
            with self.assertRaises(PermissionError):await r.propagate(Signal('target',['tick'],1))
            await r.propagate(Signal('source',['tick'],2));self.assertEqual(active_agent.get()[1],'source')
        finally:active_agent.reset(token)

    async def test_visit_cycle_and_return_once_no_fanin_amplification(self):
        n=Network();add(n,'s','clock','a','b');link(n,'s','clock');link(n,'clock','a');link(n,'clock','b')
        link(n,'a','s');link(n,'b','s');link(n,'a','clock')
        r=self.runtime(n)
        report=await r.propagate(Signal('s',['tick'],3,close_loop=True))
        self.assertEqual(report['layers'],[['clock'],['a','b'],['s']]);self.assertTrue(report['returned'])
        returns=[d for d in report['deliveries'] if d['status']=='returned'];self.assertEqual(len(returns),1)
        self.assertEqual(returns[0]['strength'],0)
        report=await r.propagate(Signal('s',['tick'],3));self.assertFalse(report['returned'])

    async def test_signal_idempotence_budget_timeout_cancel_and_failures(self):
        n=Network();add(n,'s','a','b');link(n,'s','a');link(n,'a','b');r=self.runtime(n);calls=[]
        async def slow(c):calls.append(c.delivery.node_id);await asyncio.sleep(1)
        r.bind('a',slow)
        signal=Signal('s',['tick'],3,node_timeout_seconds=.02)
        report=await r.propagate(signal);self.assertEqual(report['status'],'timed_out')
        self.assertEqual(await r.propagate(signal),report);self.assertEqual(calls,['a'])
        with self.assertRaises(ValueError):await r.propagate(Signal('s',['other'],3,signal_id=signal.signal_id))
        report=await r.propagate(Signal('s',['tick'],3,max_deliveries=1,node_timeout_seconds=.01,failure_policy='continue'))
        self.assertEqual(report['status'],'partial')
        r.unbind('a');report=await r.propagate(Signal('s',['tick'],3,max_hops=1));self.assertEqual(report['status'],'budget_exhausted')
        r.bind('a',slow);signal=Signal('s',['tick'],3)
        task=asyncio.create_task(r.propagate(signal));await asyncio.sleep(.01);await r.cancel(signal.signal_id)
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(n.signal_runs[signal.signal_id]['status'],'cancelled')

    async def test_all_receivers_wait_and_old_nonwait_option_is_rejected(self):
        n=Network();add(n,'s','a','sink');link(n,'s','a');link(n,'a','sink')
        r=self.runtime(n);started=asyncio.Event();release=asyncio.Event();seen=[]
        async def handler(c):
            seen.append(c.delivery.node_id)
            if c.delivery.node_id=='a':started.set();await release.wait()
        r.bind('a',handler);r.bind('sink',handler)
        job=asyncio.create_task(r.propagate(Signal('s',['tick'],3)))
        await asyncio.wait_for(started.wait(),.5);self.assertFalse(job.done());self.assertEqual(seen,['a'])
        release.set();report=await job;self.assertEqual(seen,['a','sink']);self.assertEqual(report['status'],'completed')
        with self.assertRaises(TypeError):Interface('a',{'wait_for_completion':False})

    async def test_topology_frozen_and_new_signal_observes_updates(self):
        n=Network();add(n,'s','a','b');link(n,'s','a');r=self.runtime(n)
        async def handler(c):
            if not n.nodes['a'].interfaces:link(n,'a','b')
        r.bind('a',handler)
        first=await r.propagate(Signal('s',['tick'],3));self.assertEqual(first['layers'],[['a']])
        second=await r.propagate(Signal('s',['tick'],3));self.assertEqual(second['layers'],[['a'],['b']])

    async def test_pulse_runs_new_ids_and_settlement_before_next_cycle(self):
        n=Network();pulse=PulseNode('p','Pulse',channels=['tick'],strength=3);n.add_node(pulse);add(n,'clock','a','b')
        link(n,'p','clock');link(n,'clock','a');link(n,'clock','b');link(n,'a','p');link(n,'b','p')
        r=self.runtime(n);events=[];settled=[]
        async def handler(c):
            seq=c.signal.sequence
            if seq>1:self.assertEqual(settled[-1],seq-1)
            events.append((seq,c.delivery.node_id));return seq
        async def settle(pulse,report):settled.append(pulse.state['sequence'])
        for id in ['clock','a','b']:r.bind(id,handler)
        result=await pulse.run(r,cycles=2,cycle_complete=settle)
        self.assertEqual(result['cycles'],2);self.assertEqual(settled,[1,2]);self.assertEqual(pulse.state['sequence'],2)
        self.assertNotEqual(result['reports'][0]['signal']['signal_id'],result['reports'][1]['signal']['signal_id'])
        self.assertEqual(result['reports'][1]['signal']['parent_id'],result['reports'][0]['signal']['signal_id'])
        self.assertEqual(events,[(1,'clock'),(1,'a'),(1,'b'),(2,'clock'),(2,'a'),(2,'b')])
        with self.assertRaises(ValueError):await pulse.run(r,cycles=0)

    async def test_pulse_without_return_or_failed_required_stops(self):
        n=Network();p=PulseNode('p','Pulse',channels=['tick']);n.add_node(p);add(n,'a');link(n,'p','a');r=self.runtime(n)
        result=await p.run(r,cycles=3);self.assertEqual(result['cycles'],1);self.assertEqual(result['status'],'blocked')
        link(n,'a','p')
        async def fail(c):raise ValueError('failed receiver')
        r.bind('a',fail);result=await p.run(r,cycles=3);self.assertEqual(result['cycles'],1);self.assertEqual(result['reports'][0]['status'],'failed')

    async def test_compacted_signal_identity_still_prevents_reexecution(self):
        n=Network();add(n,'s','a');link(n,'s','a');r=self.runtime(n,history_limit=1);calls=[]
        async def handler(c):calls.append(c.signal.signal_id)
        r.bind('a',handler)
        first=Signal('s',['tick'],2);await r.propagate(first)
        await r.propagate(Signal('s',['tick'],2))
        self.assertTrue(n.signal_runs[first.signal_id]['compacted'])
        await r.propagate(first);self.assertEqual(len(calls),2)

    async def test_strength_cannot_go_below_zero_and_gain_extra_hop(self):
        n=Network();add(n,'s','clock','a');link(n,'s','clock');link(n,'clock','a');link(n,'a','s')
        r=self.runtime(n);report=await r.propagate(Signal('s',['tick'],2,close_loop=True))
        self.assertFalse(report['returned']);self.assertEqual(report['layers'],[['clock'],['a'],[]])

    async def test_executor_normal_completion_is_readiness_without_ready_tool(self):
        from datanet.core.execution import ExecutorRegistry,ExecutionResult
        class Executor:
            def run(self,request,tools):return ExecutionResult('completed',output=request.message,steps=1)
            def cancel(self,session):return True
        with tempfile.TemporaryDirectory() as folder:
            n=Network();add(n,'s');n.add_node(AgentNode('a','Agent',file_path=Path(folder)/'a.md'));link(n,'s','a')
            registry=ExecutorRegistry(n);registry.register('test',Executor());registry.bind('a','test','session-a',max_signal_strength=2)
            r=self.runtime(n);registry.bind_signals(r,'a')
            report=await r.propagate(Signal('s',['tick'],2,content='Collect the information you hold'))
            self.assertEqual(report['deliveries'][0]['status'],'processed')
            self.assertEqual(report['deliveries'][0]['value']['output'],'Collect the information you hold')

    async def test_timed_out_executor_cannot_be_restarted_while_old_thread_runs(self):
        import threading
        from datanet.core.execution import ExecutorRegistry,ExecutionResult
        class Executor:
            def __init__(self):self.release=threading.Event();self.calls=0
            def run(self,request,tools):
                self.calls+=1;self.release.wait(1);return ExecutionResult('completed')
            def cancel(self,session):return False
        with tempfile.TemporaryDirectory() as folder:
            n=Network();add(n,'s');n.add_node(AgentNode('a','Agent',file_path=Path(folder)/'a.md'));link(n,'s','a')
            executor=Executor();registry=ExecutorRegistry(n);registry.register('test',executor);registry.bind('a','test','session-a')
            r=self.runtime(n);registry.bind_signals(r,'a')
            try:
                first=await r.propagate(Signal('s',['tick'],2,node_timeout_seconds=.02));self.assertEqual(first['status'],'timed_out')
                second=await r.propagate(Signal('s',['tick'],2));self.assertEqual(second['status'],'failed')
                self.assertEqual(executor.calls,1)
            finally:
                executor.release.set()
                await asyncio.gather(*registry._signal_workers.values(),return_exceptions=True)

    async def test_total_pulse_timeout_cancels_and_requires_reconciliation(self):
        n=Network();p=PulseNode('p','Pulse',channels=['tick']);n.add_node(p);add(n,'a');link(n,'p','a');link(n,'a','p');r=self.runtime(n)
        started=asyncio.Event();cancelled=asyncio.Event()
        async def handler(c):
            started.set()
            try:await asyncio.sleep(10)
            finally:cancelled.set()
        r.bind('a',handler)
        with self.assertRaises(TimeoutError):await p.run(r,timeout_seconds=.03)
        self.assertTrue(started.is_set());self.assertTrue(cancelled.is_set());self.assertEqual(p.state['phase'],'interrupted')
        with self.assertRaises(RuntimeError):await p.run(r)

    async def test_checkpoint_and_interrupted_restore_do_not_replay(self):
        from datanet.core.backend import Backend
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);p=PulseNode('p','Pulse',channels=['tick']);b.network.add_node(p);add(b.network,'a')
            link(b.network,'p','a');link(b.network,'a','p');r=b.signals
            try:
                result=await p.run(r,cycles=2);self.assertEqual(result['cycles'],2)
                saved_id=p.state['last_signal']
                snapshot=b.snapshot()
            finally:b.close()
            b=Backend(folder)
            try:
                restored=b.network.nodes['p'];self.assertEqual(restored.state['sequence'],2)
                signal=Signal.from_dict(b.network.signal_runs[saved_id]['signal'])
                report=await b.signals.propagate(signal);self.assertEqual(report['status'],'completed')
                # An in-flight saved request is never silently replayed after restore.
                snapshot['network']['signals'][saved_id]['status']='running'
                pulse_entry=next(e for e in snapshot['network']['nodes'] if e['node_id']=='p')
                pulse_entry['parameters']['state']['phase']='finalizing'
                pulse_entry['parameters']['state']['active_signal']=saved_id
                b.restore(snapshot)
                self.assertEqual(b.network.signal_runs[saved_id]['status'],'interrupted')
                with self.assertRaises(RuntimeError):await b.signals.propagate(signal)
                with self.assertRaises(RuntimeError):await b.network.nodes['p'].run(b.signals)
                b.network.nodes['p'].reconcile('Operator reconciled the interrupted settlement')
            finally:b.close()

if __name__=='__main__':unittest.main()
