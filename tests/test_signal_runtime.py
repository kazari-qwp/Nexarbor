"""原信号/动态拓扑断言迁到新节点；信号不调用 access 遍历。"""

import asyncio
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.runtime.backend import Backend
from app.runtime.requester import requester_id
from app.runtime.signal_authority import current_authority, signal_authority
from app.runtime.signal_runtime import SignalRuntime
from app.runtime.signal_work import current_work
from domain.core import Link, MaxAggregation, MinAggregation, AverageAggregation, Multiplier, Network, Node, NodeInfo
from domain.pulse_node import PulseNode
from domain.signals import Signal, restore_records

ROOT=Path(__file__).resolve().parents[1]


def network(*names):
    return Network(Node(NodeInfo(name,name)) for name in names)


def link(net,source,target,channels=('tick',),**kwargs):
    edge=Link(target,channels,**kwargs)
    net.get(source).links.add(edge)
    return edge


class SignalValues(unittest.TestCase):
    def test_immutable_roundtrip_and_validation(self):
        signal=Signal('s',['a','a','b'],3,content={'items':[1,2]})
        self.assertEqual(signal,Signal.from_dict(json.loads(json.dumps(signal.to_dict()))))
        self.assertEqual(signal.channels,('a','b'))
        with self.assertRaises(TypeError):signal.content['x']=1
        with self.assertRaises(FrozenInstanceError):signal.strength=4
        for channels in ([],[''],[' ']):
            with self.assertRaises(ValueError):Signal('s',channels,3)
        with self.assertRaises(ValueError):Signal('s',['a'],float('nan'))

    def test_restore_marks_incomplete_work_without_replaying(self):
        signal=Signal('s',['tick'],1)
        records={signal.signal_id:dict(signal=signal.to_dict(),status='running',deliveries=[dict(status='processing')])}
        restored=restore_records(records)[signal.signal_id]
        self.assertEqual(restored['status'],'interrupted')
        self.assertEqual(restored['deliveries'][0]['status'],'interrupted')
        self.assertEqual(records[signal.signal_id]['status'],'running')


class SignalTests(unittest.IsolatedAsyncioTestCase):
    def runtime(self,net,**options):
        runtime=SignalRuntime(net,**options)
        self.addAsyncCleanup(runtime.close)
        return runtime

    async def test_channels_thresholds_and_multiplier_filter_before_fanin(self):
        net=network('s','a','b','private','sink')
        link(net,'s','a',('a',));link(net,'s','b',('b',));link(net,'s','private',('private',))
        link(net,'a','sink',('a',),processor=Multiplier(2))
        link(net,'b','sink',('b',),threshold=4)
        runtime=self.runtime(net)
        report=await runtime.propagate(Signal('s',['a','b'],3))
        self.assertEqual(report['layers'],[['a','b'],['sink']])
        self.assertEqual(report['deliveries'][-1]['strength'],6)

    async def test_layer_parallel_fanin_and_deferred_work_barrier(self):
        net=network('s','a','b','sink')
        for source,target in [('s','a'),('s','b'),('a','sink'),('b','sink')]:link(net,source,target)
        runtime=self.runtime(net);started=set();both=asyncio.Event();events=[]
        async def handle(context):
            node_id=context.delivery.node_id
            if node_id in ('a','b'):
                started.add(node_id)
                if len(started)==2:both.set()
                await asyncio.wait_for(both.wait(),1)
                async def later():
                    await asyncio.sleep(.01)
                    events.append('deferred:'+node_id)
                current_work.get().post(later,node_id)
            else:
                self.assertEqual(set(events),{'deferred:a','deferred:b'})
                self.assertEqual(context.delivery.strength,6)
                self.assertEqual(context.delivery.parents,('a','b'))
                self.assertFalse(hasattr(context,'network'))
            return node_id
        for key in ('a','b','sink'):runtime.bind(key,handle)
        report=await runtime.propagate(Signal('s',['tick'],3))
        self.assertEqual(report['layers'],[['a','b'],['sink']])
        self.assertEqual([entry['status'] for entry in report['deferred']],['processed','processed'])

    async def test_receiver_identity_strength_and_nested_authority(self):
        net=network('s','a');link(net,'s','a')
        runtime=self.runtime(net);observed=[]
        async def handle(context):
            observed.append((requester_id.get(),current_authority.get().strength))
            with self.assertRaises(PermissionError):runtime.emit(Signal('s',['tick'],1))
            with self.assertRaises(PermissionError):runtime.emit(Signal('a',['tick'],2))
        runtime.bind('a',handle,access_strength=1)
        with signal_authority('s',2,['tick']):
            with self.assertRaises(PermissionError):runtime.emit(Signal('s',['tick'],3))
            with self.assertRaises(PermissionError):runtime.emit(Signal('s',['other'],1))
            await runtime.propagate(Signal('s',['tick'],2))
            self.assertEqual(current_authority.get().node_id,'s')
        self.assertEqual(observed,[('a',1)])
        self.assertIsNone(requester_id.get())

    async def test_return_once_without_origin_handler_or_cycle_revisit(self):
        net=network('s','clock','a','b')
        for source,target in [('s','clock'),('clock','a'),('clock','b'),('a','s'),('b','s'),('a','clock')]:link(net,source,target)
        net.get('s').aggregation=MaxAggregation()
        runtime=self.runtime(net);calls=[]
        async def origin(context):calls.append('s')
        runtime.bind('s',origin)
        report=await runtime.propagate(Signal('s',['tick'],3,close_loop=True))
        self.assertEqual(report['layers'],[['clock'],['a','b'],['s']])
        self.assertTrue(report['returned']);self.assertEqual(calls,[])
        self.assertEqual(sum(entry['status']=='returned' for entry in report['deliveries']),1)
        self.assertFalse((await runtime.propagate(Signal('s',['tick'],3)))['returned'])

    async def test_all_aggregation_strategies_and_negative_stop(self):
        for aggregation,expected in [(None,6),(MaxAggregation(),4),(MinAggregation(),1),(AverageAggregation(),2.5)]:
            net=network('s','a','b','sink')
            for source,target in [('s','a'),('s','b'),('a','sink')]:link(net,source,target)
            link(net,'b','sink',processor=Multiplier(2.5))
            sink=net.get('sink');sink.bias=-1
            if aggregation is not None:sink.aggregation=aggregation
            runtime=self.runtime(net)
            report=await runtime.propagate(Signal('s',['tick'],2))
            self.assertEqual(report['deliveries'][-1]['strength'],expected)
            sink.bias=-100
            report=await runtime.propagate(Signal('s',['tick'],2))
            self.assertEqual(report['layers'],[['a','b'],[]])

    async def test_failure_policies_budgets_and_compacted_identity(self):
        net=network('s','a','b','sink');link(net,'s','a');link(net,'s','b');link(net,'b','sink')
        runtime=self.runtime(net,history_limit=1)
        async def fail(context):raise ValueError('receiver failed')
        runtime.bind('a',fail)
        first=Signal('s',['tick'],2)
        self.assertEqual((await runtime.propagate(first))['status'],'failed')
        report=await runtime.propagate(Signal('s',['tick'],2,failure_policy='continue'))
        self.assertEqual(report['status'],'partial');self.assertEqual(report['layers'],[['a','b'],['sink']])
        self.assertTrue(runtime.status(first.signal_id)['compacted'])
        self.assertEqual((await runtime.propagate(first))['status'],'failed')
        with self.assertRaises(ValueError):runtime.emit(Signal('s',['other'],2,signal_id=first.signal_id))
        runtime.unbind('a')
        self.assertEqual((await runtime.propagate(Signal('s',['tick'],2,max_hops=1)))['status'],'budget_exhausted')
        self.assertEqual((await runtime.propagate(Signal('s',['tick'],2,max_deliveries=1)))['layers'],[])

    async def test_waiter_cancellation_does_not_cancel_independent_wave(self):
        net=network('s','a');link(net,'s','a');runtime=self.runtime(net)
        entered=asyncio.Event();release=asyncio.Event()
        async def hold(context):entered.set();await release.wait()
        runtime.bind('a',hold)
        signal=Signal('s',['tick'],2)
        waiter=asyncio.create_task(runtime.propagate(signal))
        await asyncio.wait_for(entered.wait(),1)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):await waiter
        self.assertIn(signal.signal_id,runtime._active)
        release.set()
        self.assertEqual((await runtime.wait(signal.signal_id))['status'],'completed')

    async def test_explicit_cancel_cancels_handlers_and_deferred_tasks(self):
        net=network('s','a');link(net,'s','a');runtime=self.runtime(net)
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def hold(context):
            async def later():
                entered.set()
                try:await asyncio.Event().wait()
                finally:cancelled.set()
            current_work.get().post(later,'deferred')
        runtime.bind('a',hold)
        signal=Signal('s',['tick'],2);runtime.emit(signal)
        await asyncio.wait_for(entered.wait(),1)
        self.assertTrue(await runtime.cancel(signal.signal_id))
        with self.assertRaises(asyncio.CancelledError):await runtime.wait(signal.signal_id)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(runtime.status(signal.signal_id)['status'],'cancelled')

    async def test_current_topology_expands_after_all_handlers(self):
        net=network('s','fast','slow','old','new')
        link(net,'s','fast');link(net,'s','slow');edge=link(net,'fast','old')
        runtime=self.runtime(net);ready=asyncio.Event()
        async def fast(context):ready.set()
        async def slow(context):
            await ready.wait()
            net.get('fast').links.remove(edge);link(net,'fast','new')
        runtime.bind('fast',fast);runtime.bind('slow',slow)
        self.assertEqual((await runtime.propagate(Signal('s',['tick'],2)))['layers'],[['fast','slow'],['new']])

    async def test_disabled_receiver_blocks_relay(self):
        net=network('s','a','b');link(net,'s','a');link(net,'a','b')
        runtime=self.runtime(net,enabled=lambda node:node.info.node_id!='a')
        report=await runtime.propagate(Signal('s',['tick'],2))
        self.assertEqual(report['status'],'failed');self.assertEqual(report['layers'],[['a']])


class PersistentSignals(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='.signals-',dir=ROOT/'build')
        self.addCleanup(self.temp.cleanup)
        self.net=network('a','old','new')
        self.pulse=PulseNode(NodeInfo('p','Pulse'),channels=['tick'],strength=3)
        self.net.add(self.pulse)
        link(self.net,'p','a');self.edge=link(self.net,'a','old');link(self.net,'old','p');link(self.net,'new','p')
        self.backend=Backend(self.temp.name,network=self.net)
        self.addCleanup(lambda:self.backend.close())

    async def test_source_lock_waits_for_commit_or_rollback_before_expansion(self):
        for rollback in (False,True):
            a=self.net.get('a');a.links._links[:]=[self.edge]
            locked=asyncio.Event();release=asyncio.Event();seen=[]
            async def writer():
                try:
                    async with self.backend.node_locks.transaction(['a']):
                        a.links.remove(self.edge);link(self.net,'a','new')
                        locked.set();await release.wait()
                        if rollback:raise ValueError('rollback')
                except ValueError:pass
            task=asyncio.create_task(writer());await asyncio.wait_for(locked.wait(),1)
            async def hit(context):seen.append(context.delivery.node_id)
            self.backend.signals.bind('a',hit)
            wave=asyncio.create_task(self.backend.signals.propagate(Signal('p',['tick'],3)))
            await asyncio.sleep(.02);self.assertEqual(seen,[]);self.assertFalse(wave.done())
            release.set();await task
            report=await wave
            self.assertEqual(report['layers'][:2],[['a'],['old' if rollback else 'new']])

    async def test_pulse_five_cycles_settlement_and_checkpoint_restart(self):
        settled=[]
        async def finish(pulse,report):settled.append(pulse.state['sequence'])
        result=await self.pulse.run(self.backend.signals,cycles=5,cycle_complete=finish)
        self.assertEqual(result['status'],'completed');self.assertEqual(settled,[1,2,3,4,5])
        self.assertEqual(len({report['signal']['signal_id'] for report in result['reports']}),5)
        self.assertEqual(result['reports'][1]['signal']['parent_id'],result['reports'][0]['signal']['signal_id'])
        saved_id=self.pulse.state['last_signal']
        self.backend.close();self.backend=Backend(self.temp.name)
        pulse=self.backend.network.get('p')
        self.assertEqual(pulse.state['sequence'],5)
        signal=Signal.from_dict(self.backend.signals.status(saved_id)['signal'])
        self.assertEqual((await self.backend.signals.propagate(signal))['status'],'completed')
        snapshot=self.backend.snapshot();snapshot['signals'][saved_id]['status']='running'
        record=next(node for node in snapshot['network']['nodes'] if node['node_id']=='p')
        record['parameters']['state'].update(phase='finalizing',active_signal=saved_id)
        self.backend.restore(snapshot)
        with self.assertRaises(RuntimeError):await self.backend.signals.propagate(signal)
        with self.assertRaises(RuntimeError):await self.backend.network.get('p').run(self.backend.signals)
        self.backend.network.get('p').reconcile('effects reconciled')

    async def test_pulse_cancel_owned_wave_and_requires_reconciliation(self):
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def hold(context):
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        self.backend.signals.bind('a',hold)
        task=asyncio.create_task(self.pulse.run(self.backend.signals))
        await asyncio.wait_for(entered.wait(),1);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(cancelled.is_set());self.assertEqual(self.pulse.state['phase'],'interrupted')
        with self.assertRaises(RuntimeError):await self.pulse.run(self.backend.signals)

    async def test_pulse_parameters_and_state_participate_in_local_rollback(self):
        state=self.pulse.state
        with self.assertRaises(ValueError):
            async with self.backend.node_locks.transaction(['p']):
                self.pulse.strength=10;self.pulse.state['sequence']=99
                raise ValueError('rollback')
        self.assertIs(self.pulse.state,state)
        self.assertEqual(self.pulse.strength,3);self.assertEqual(self.pulse.state['sequence'],0)
