"""原节点锁规则接入新节点、access 和局部快照。"""

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.transactions import NodeBusyError, NodeLockDeadlockError, NodeLocks, NodeSnapshots
from domain.agent import MarkdownAgentNode
from domain.core import CallableTool, Link, Module, Network, Node, NodeInfo, SumAggregation, access


class Probe(Module):
    def __init__(self, key, **kwargs):
        super().__init__('probe', **kwargs)
        self.state = {'value': 'old'}
        self.config = {'value': 'config'}
        self.published = {'value': 'published'}
        self.tools._add(CallableTool('probe_' + key, lambda: self.state['value']))

    @access()
    async def read(self, node):
        return node.info.name

    @access()
    def read_sync(self, node):
        return node.info.name


class NodeLockTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.node-locks-', dir=Path(__file__).resolve().parents[1] / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.nodes, self.probes = {}, {}
        for key in 'abc':
            file = self.directory / (key + '.md')
            file.write_text('OLD', encoding='utf-8')
            node = MarkdownAgentNode(NodeInfo(key, key), file)
            probe = Probe(key, channels='red', strength=2)
            node.install(probe)
            self.nodes[key], self.probes[key] = node, probe
        self.network = Network(self.nodes.values())
        self.execution = {'a': {'session_id': 'session-a'}}
        self.bindings = {'a': {'executor': 'harness', 'model': {'model': 'before'}}}
        self.snapshots = NodeSnapshots(self.network, self.directory, execution=self.execution, bindings=self.bindings)
        self.locks = NodeLocks(self.network, self.snapshots)

    def tearDown(self):
        for field in ('exclusive', 'active', 'waiters', 'dependencies', 'leases', 'suspended', 'tickets'):
            self.assertFalse(getattr(self.locks, field), field)

    async def hold(self, nodes, ready, release):
        async with self.locks.transaction(nodes):
            ready.set()
            await release.wait()

    async def test_access_waits_until_unlock_and_reads_committed_values(self):
        ready, release = asyncio.Event(), asyncio.Event()
        async def writer():
            async with self.locks.transaction(['a']):
                self.nodes['a'].info.name = 'changed'
                ready.set()
                await release.wait()
        owner = asyncio.create_task(writer())
        await ready.wait()
        reader = asyncio.create_task(self.probes['a'].read())
        await asyncio.sleep(.01)
        self.assertFalse(reader.done())
        self.assertEqual(await self.probes['c'].read(), {'c': 'c'})
        release.set()
        await owner
        self.assertEqual(await reader, {'a': 'changed'})

    async def test_deleted_edge_is_not_seen_after_waiting_on_its_source(self):
        self.nodes['c'].links.add(Link('a', 'red'))
        edge = Link('b', 'red')
        self.nodes['a'].links.add(edge)
        ready, release = asyncio.Event(), asyncio.Event()
        owner = asyncio.create_task(self.hold(['a'], ready, release))
        await ready.wait()
        reader = asyncio.create_task(self.probes['c'].read())
        await asyncio.sleep(.01)
        self.assertFalse(reader.done())
        self.nodes['a'].links.remove(edge)
        release.set()
        await owner
        self.assertEqual(await reader, {'c': 'c', 'a': 'a'})

    async def test_bias_and_aggregation_are_read_after_target_unlock(self):
        self.nodes['c'].links.add(Link('a', 'red'))
        self.nodes['a'].bias = -100
        ready, release = asyncio.Event(), asyncio.Event()
        class AfterUnlock(SumAggregation):
            def combine(inner, values):
                self.assertTrue(release.is_set())
                return super().combine(values)
        self.nodes['a'].aggregation = AfterUnlock()
        async def writer():
            async with self.locks.transaction(['a']):
                ready.set()
                await release.wait()
                self.nodes['a'].bias = 0
        owner = asyncio.create_task(writer())
        await ready.wait()
        reader = asyncio.create_task(self.probes['c'].read())
        await asyncio.sleep(.01)
        self.assertFalse(reader.done())
        release.set()
        await owner
        self.assertEqual(await reader, {'c': 'c', 'a': 'a'})

    async def test_lock_waits_for_an_active_operation_to_finish(self):
        entered, finish, acquired = asyncio.Event(), asyncio.Event(), asyncio.Event()
        @access(channels=())
        async def long_read(owner, node):
            entered.set()
            await finish.wait()
        reader = asyncio.create_task(long_read(self.probes['a']))
        await entered.wait()
        async def writer():
            async with self.locks.transaction(['a']):
                acquired.set()
        owner = asyncio.create_task(writer())
        await asyncio.sleep(.01)
        self.assertFalse(acquired.is_set())
        finish.set()
        await asyncio.gather(reader, owner)
        self.assertTrue(acquired.is_set())

    async def test_rollback_restores_local_state_files_inputs_links_and_identities(self):
        node, probe = self.nodes['a'], self.probes['a']
        info, state, tools, group = node.info, probe.state, node.tools, probe.tools
        action = next(iter(probe.tools))
        callback = action.function
        link = Link('b', 'red')
        node.links.add(link)
        processor = link.processor
        with self.assertRaisesRegex(ValueError, 'abort'):
            async with self.locks.transaction(['a']):
                node.info.name = 'changed'
                probe.state['value'] = 'new'
                probe.config['value'] = 'new'
                probe.published['value'] = 'new'
                node.dataer.write('NEW')
                node.update_inputs('producer', tail=['new'])
                self.execution['a']['session_id'] = 'changed'
                link.channels, link.processor.factor = ('wrong',), 9
                node.links.remove(link)
                node.links.add(Link('c', 'red'))
                action.description = 'changed'
                probe.tools._remove(action)
                self.nodes['c'].info.name = 'independent'
                raise ValueError('abort')
        self.assertIs(node.info, info)
        self.assertEqual(node.info.name, 'a')
        self.assertIs(probe.state, state)
        self.assertEqual(probe.state, {'value': 'old'})
        self.assertEqual(probe.config, {'value': 'config'})
        self.assertEqual(probe.published, {'value': 'published'})
        self.assertIs(node.tools, tools)
        self.assertIs(probe.tools, group)
        self.assertIs(next(iter(probe.tools)), action)
        self.assertIs(action.function, callback)
        self.assertIs(probe._access_origin, node)
        self.assertEqual(node.dataer.read(), 'OLD')
        self.assertEqual(node.inputs.tail(), [])
        self.assertEqual(self.execution['a']['session_id'], 'session-a')
        self.assertEqual(node.links.list(), [link])
        self.assertEqual(link.channels, ('red',))
        self.assertIs(link.processor, processor)
        self.assertEqual(processor.factor, 1)
        self.assertEqual(self.nodes['c'].info.name, 'independent')

    async def test_cancel_rolls_back_before_queued_reader_runs(self):
        ready = asyncio.Event()
        async def writer():
            async with self.locks.transaction(['a']):
                self.nodes['a'].info.name = 'partial'
                self.nodes['a'].dataer.write('PARTIAL')
                ready.set()
                await asyncio.Event().wait()
        owner = asyncio.create_task(writer())
        await ready.wait()
        reader = asyncio.create_task(self.probes['a'].read())
        await asyncio.sleep(0)
        owner.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await owner
        self.assertEqual(await reader, {'a': 'a'})
        self.assertEqual(self.nodes['a'].dataer.read(), 'OLD')

    async def test_group_reentry_and_nested_failure_roll_back_whole_group(self):
        with self.assertRaisesRegex(RuntimeError, 'rolled back'):
            async with self.locks.transaction(['a', 'b']):
                with self.assertRaisesRegex(RuntimeError, 'cannot expand'):
                    async with self.locks.transaction(['c']):
                        pass
                try:
                    async with self.locks.transaction(['b']):
                        self.nodes['a'].info.name = 'partial-a'
                        self.nodes['b'].info.name = 'partial-b'
                        raise ValueError('nested')
                except ValueError:
                    pass
        self.assertEqual(await self.probes['a'].read(), {'a': 'a'})
        self.assertEqual(await self.probes['b'].read(), {'b': 'b'})

    async def test_queued_lock_timeout_and_cancellation_clean_waiters(self):
        ready, release = asyncio.Event(), asyncio.Event()
        owner = asyncio.create_task(self.hold(['a'], ready, release))
        await ready.wait()
        with self.assertRaises(TimeoutError):
            async with self.locks.transaction(['a'], timeout=.01):
                pass
        async def wait():
            async with self.locks.access(['a']):
                pass
        waiting = asyncio.create_task(wait())
        await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        release.set()
        await owner

    async def test_sync_wait_does_not_block_an_event_loop(self):
        ready, release = asyncio.Event(), asyncio.Event()
        owner = asyncio.create_task(self.hold(['a'], ready, release))
        await ready.wait()
        with self.assertRaises(NodeBusyError):
            self.probes['a'].read_sync()
        release.set()
        await owner

    async def test_sync_access_can_wait_on_a_worker_thread(self):
        ready, release = asyncio.Event(), asyncio.Event()
        owner = asyncio.create_task(self.hold(['a'], ready, release))
        await ready.wait()
        reader = asyncio.create_task(asyncio.to_thread(self.probes['a'].read_sync))
        await asyncio.sleep(.01)
        self.assertFalse(reader.done())
        release.set()
        await owner
        self.assertEqual(await reader, {'a': 'a'})

    async def test_external_wait_releases_admission_then_reenters(self):
        waiting, returned, held, release = (asyncio.Event() for _ in range(4))
        async def actor():
            async with self.locks.access(['a']):
                async with self.locks.suspend_access():
                    waiting.set()
                    await returned.wait()
                self.assertIn('a', self.locks.active)
                self.assertFalse(self.locks.exclusive)
        task = asyncio.create_task(actor())
        await waiting.wait()
        owner = asyncio.create_task(self.hold(['a'], held, release))
        await held.wait()
        returned.set()
        await asyncio.sleep(.01)
        self.assertFalse(task.done())
        release.set()
        await asyncio.gather(task, owner)

    async def test_explicit_transaction_cannot_suspend_its_node_ownership(self):
        async with self.locks.transaction(['a']):
            with self.assertRaisesRegex(RuntimeError, 'Release node transactions'):
                async with self.locks.suspend_access():
                    pass
            with self.assertRaises(RuntimeError):
                self.nodes['a'].install(Module('new'))
            with self.assertRaises(RuntimeError):
                self.nodes['a'].remove('probe')

    async def test_lock_dependency_cycle_aborts_instead_of_hanging(self):
        a, b = asyncio.Event(), asyncio.Event()
        async def owner(own, target, ready, peer):
            async with self.locks.transaction([own]):
                ready.set()
                await peer.wait()
                async with self.locks.access([target], mutable=False):
                    return True
        results = await asyncio.wait_for(asyncio.gather(owner('a', 'b', a, b), owner('b', 'a', b, a), return_exceptions=True), 1)
        self.assertEqual(sum(isinstance(result, NodeLockDeadlockError) for result in results), 1)
        self.assertIn(True, results)

    async def test_owner_tickets_are_actor_bound_and_expire(self):
        with self.locks.export_owner('a') as ticket:
            with self.locks.import_owner(ticket, 'a'):
                async with self.locks.access(['a']):
                    pass
            with self.assertRaises(PermissionError):
                with self.locks.import_owner(ticket, 'b'):
                    pass
        with self.assertRaises(PermissionError):
            with self.locks.import_owner(ticket, 'a'):
                pass

    async def test_fresh_native_cursor_is_captured_before_body_and_restore_keeps_progress(self):
        events = []
        class Contexts:
            count = 1
            async def capture(self, bindings):
                return {node: dict(session_id=session, event_count=self.count) for node, session in bindings.items()}
            async def restore(self, cursors):
                return {'contexts': {node: dict(cursor, event_count=self.count) for node, cursor in cursors.items()}}
        contexts = self.locks.contexts = Contexts()
        self.locks.commit = lambda group: events.append(('before' if group is None else 'after', self.execution['a']['context_cursor']['event_count']))
        with self.assertRaises(ValueError):
            async with self.locks.transaction(['a']):
                self.assertEqual(events, [('before', 1)])
                self.nodes['a'].dataer.write('PARTIAL')
                contexts.count = 2
                raise ValueError('abort')
        self.assertEqual(self.nodes['a'].dataer.read(), 'OLD')
        self.assertEqual(self.execution['a']['context_cursor']['event_count'], 2)
        self.assertEqual(events, [('before', 1), ('after', 2)])

    async def test_new_network_nodes_receive_the_same_access_gate(self):
        node = Node(NodeInfo('new', 'New'))
        self.network.add(node)
        self.assertIs(node._access_guard, self.locks)

    async def test_link_processor_bound_method_is_not_deepcopied(self):
        class Processor(Module):
            def scale(self, value):
                return value
        module = Processor('processor')
        self.nodes['a'].install(module)
        callback = module.scale
        link = Link('b', 'red', processor=callback)
        self.nodes['a'].links.add(link)
        with self.assertRaises(ValueError):
            async with self.locks.transaction(['a']):
                link.processor = lambda value: 999
                raise ValueError('rollback')
        self.assertIs(link.processor, callback)
        self.assertIs(module._access_origin, self.nodes['a'])

    async def test_unrelated_external_resource_does_not_block_a_local_transaction(self):
        project = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix='.external-node-', dir=project / 'build') as folder:
            file = Path(folder) / 'outside.md'
            file.write_text('outside', encoding='utf-8')
            self.network.add(MarkdownAgentNode(NodeInfo('outside', 'Outside'), file))
            async with self.locks.transaction(['a']):
                self.nodes['a'].info.name = 'committed'
            with self.assertRaises(ValueError):
                async with self.locks.transaction(['outside']):
                    pass
        self.assertEqual(self.nodes['a'].info.name, 'committed')

    async def test_locked_peer_does_not_serialize_same_layer_but_next_layer_waits(self):
        extra = Node(NodeInfo('d', 'd'))
        self.network.add(extra)
        self.nodes['c'].links.add(Link('a', 'red'))
        self.nodes['c'].links.add(Link('b', 'red'))
        self.nodes['b'].links.add(Link('d', 'red'))
        held, release, peer_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
        owner = asyncio.create_task(self.hold(['a'], held, release))
        await held.wait()
        seen = []
        @access(channels='red', strength=2)
        async def read(reader, node):
            seen.append(node.info.node_id)
            if node.info.node_id == 'b':peer_done.set()
            return node.info.name
        task = asyncio.create_task(read(self.probes['c']))
        await asyncio.wait_for(peer_done.wait(), 1)
        self.assertEqual(seen, ['c', 'b'])
        release.set()
        await owner
        result = await task
        self.assertEqual(list(result), ['c', 'a', 'b', 'd'])

    async def test_outgoing_links_are_also_guarded_after_the_node_body(self):
        self.nodes['c'].links.add(Link('a', 'red'))
        self.nodes['c'].links.add(Link('b', 'red'))
        extra = Node(NodeInfo('d', 'd'))
        self.network.add(extra)
        edge = Link('d', 'red')
        self.nodes['a'].links.add(edge)
        a_done, b_done, held, release = (asyncio.Event() for _ in range(4))
        @access(channels='red', strength=2)
        async def read(reader, node):
            if node.info.node_id == 'a':a_done.set()
            if node.info.node_id == 'b':await b_done.wait()
            return node.info.name
        task = asyncio.create_task(read(self.probes['c']))
        await a_done.wait()
        async def writer():
            async with self.locks.transaction(['a']):
                self.nodes['a'].links.remove(edge)
                held.set()
                await release.wait()
        owner = asyncio.create_task(writer())
        await held.wait()
        b_done.set()
        await asyncio.sleep(.01)
        self.assertFalse(task.done())
        release.set()
        await owner
        self.assertEqual(list(await task), ['c', 'a', 'b'])

    async def test_deny_channels_include_restored_links_after_wait(self):
        self.probes['c'].channels = ()
        self.probes['c'].channel_mode = 'deny'
        self.nodes['c'].links.add(Link('a', 'blue'))
        edge = Link('b', 'red')
        self.nodes['a'].links.add(edge)
        held, release = asyncio.Event(), asyncio.Event()
        async def writer():
            try:
                async with self.locks.transaction(['a']):
                    self.nodes['a'].links.remove(edge)
                    held.set()
                    await release.wait()
                    raise ValueError('rollback')
            except ValueError:
                pass
        owner = asyncio.create_task(writer())
        await held.wait()
        reader = asyncio.create_task(self.probes['c'].read())
        await asyncio.sleep(.01)
        self.assertFalse(reader.done())
        release.set()
        await owner
        self.assertEqual(list(await reader), ['c', 'a', 'b'])

    async def test_before_records_include_the_fresh_native_cursor_in_execution_state(self):
        self.execution['a']['context_cursor'] = {'session_id': 'session-a', 'event_count': 0}
        self.snapshots.document = lambda: {
            'network': {'nodes': [{'node_id': node.info.node_id} for node in self.network]},
            'agents': deepcopy(self.execution), 'files': {},
        }
        class Contexts:
            async def capture(inner, bindings):
                return {node: dict(session_id=session, event_count=3) for node, session in bindings.items()}
        self.locks.contexts = Contexts()
        def commit(group):
            if group is None:
                record = self.locks.records()['a']
                self.assertEqual(record['node']['context_cursor']['event_count'], 3)
                self.assertEqual(record['agent']['context_cursor']['event_count'], 3)
                self.assertEqual(record['files']['a.md'], 'OLD')
        self.locks.commit = commit
        async with self.locks.transaction(['a']):
            pass

    async def test_execution_binding_and_runner_roll_back_with_node(self):
        original = self.bindings['a']
        with self.assertRaises(ValueError):
            async with self.locks.transaction(['a']):
                self.bindings['a']['model'] = {'model': 'changed'}
                self.nodes['a'].runner = lambda *_: 'changed'
                raise ValueError('abort')
        self.assertIs(self.bindings['a'], original)
        self.assertEqual(original, {'executor': 'harness', 'model': {'model': 'before'}})
        self.assertIsNone(self.nodes['a'].runner)
