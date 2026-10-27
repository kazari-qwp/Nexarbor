"""新节点接入原增量存储、恢复包和模块/工具箱配置。"""

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.persistence.recovery import acknowledge_executors, required_contexts, restore_bundle
from app.runtime.backend import Backend
from domain.core import CallableTool, Link, Module, Network, Node, NodeInfo, Tools, access
from modules.context_assembler import ContextAssemblerModule
from modules.tool_discovery import ToolDiscoveryModule

ROOT = Path(__file__).resolve().parents[1]


class Counter(Module):
    def __init__(self):
        super().__init__('counter')
        self.config = {'step': 1}
        self.state = {'count': 0}
        self.published = {'status': 'ready'}
        self.tools._add(CallableTool('increment', self.increment))

    @access(channels=())
    def increment(self, node):
        self.state['count'] += self.config['step']
        return [node.info.node_id, self.state['count']]


def saver():
    result = NetworkSaver()
    result.tables.module_types['counter'] = lambda spec: Counter()
    return result


class PersistentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.persistent-', dir=ROOT / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def backend(self, name='runtime', **kwargs):
        backend = Backend(self.home / name, **kwargs)
        self.addCleanup(backend.close)
        return backend

    def test_incremental_commit_uses_live_files_without_export_copies(self):
        backend = self.backend()
        node = backend.network.get('root')
        node.dataer.write('before')
        backend.bindings['root'] = {'executor': 'harness', 'strength': 6}
        backend.save()
        before = backend.store.head
        node.dataer.write('after')
        backend.save()
        document = backend.store.latest()
        self.assertEqual(document['files']['root-memory.md'], 'after')
        self.assertEqual(backend.store.read(before)['files']['root-memory.md'], 'before')
        self.assertEqual(document['network']['nodes'][0]['data']['path'], 'root-memory.md')
        self.assertFalse((backend.directory / 'network_data').exists())
        self.assertEqual(backend.bindings['root']['strength'], 6)

    def test_modules_rebind_new_nodes_with_state_publications_and_dependency_identity(self):
        codec = saver()
        node = Node(NodeInfo('counter', 'Counter'))
        module = Counter()
        relay = ToolDiscoveryModule('tools', 3)
        relay._dependencies = (module,)
        node.install(relay)
        module.state['count'] = 8
        module.config['step'] = 2
        module.published['status'] = 'running'
        document = codec.document(Network([node]), self.home)
        loaded = codec.build(document, self.home).get('counter')
        copied = loaded.modules.get('counter')
        self.assertIsNot(copied, module)
        self.assertIs(loaded.modules.get('tool_discovery').modules[0], copied)
        self.assertEqual(copied.published, {'status': 'running'})
        self.assertEqual(next(iter(loaded.tools)).invoke(), {'counter': ['counter', 10]})
        self.assertEqual(module.state['count'], 8)
        with self.assertRaises(ValueError):loaded.remove(copied)

    def test_restoring_module_tables_does_not_reinstall_removed_or_extra_tools(self):
        codec = saver()
        codec.tables.tool_types['extra'] = lambda node, spec: CallableTool('extra', lambda: 'extra')
        node = Node(NodeInfo('a', 'A'))
        module = Counter()
        node.install(module)
        original = next(iter(module.tools))
        module.tools._remove(original)
        module.tools._add(CallableTool('extra', lambda: 'original'))
        loaded = codec.build(codec.document(Network([node]), self.home), self.home).get('a')
        self.assertEqual([tool.name for tool in loaded.tools], ['extra'])
        self.assertEqual(next(iter(loaded.tools)).invoke(), 'extra')

    def test_toolbox_shared_groups_and_registered_functions_roundtrip(self):
        codec = saver()
        codec.tables.tool_types['one'] = lambda node, record: CallableTool('one', lambda: node.info.name)
        node = Node(NodeInfo('a', 'A'))
        shared = Tools([CallableTool('one', lambda: 'original')])
        node.install(Tools([shared, Tools([shared])]))
        loaded = codec.build(codec.document(Network([node]), self.home), self.home).get('a')
        group = loaded.tools.members[1]
        self.assertIs(group.members[0], group.members[1].members[0])
        self.assertEqual([tool.invoke() for tool in loaded.tools], ['A'])
        self.assertIsNot(group.members[0], shared)

    def test_recovery_branch_requires_exact_executor_ack_and_preserves_source(self):
        backend = self.backend()
        node = backend.network.get('root')
        backend.agents['root'] = {'session_id': 'old-session'}
        node.dataer.write('before')
        backend.save()
        with self.assertRaises(ValueError):backend.mark(contexts={})
        cursors = {'root': {'adapter': 'fixture', 'session_id': 'old-session', 'seq': 7}}
        point = backend.mark(contexts=cursors, expected_commit=backend.store.head, kind='full')
        node.dataer.write('after')
        backend.save()
        bundle = backend.store.bundle(point['id'])
        result = restore_bundle(bundle, self.home / 'branch')
        self.assertEqual(result['executor_restore']['status'], 'pending')
        branch = self.backend('branch')
        self.assertEqual(branch.network.get('root').dataer.read(), 'before')
        self.assertEqual(node.dataer.read(), 'after')
        self.assertEqual(required_contexts(branch.store)['root']['seq'], 7)
        with self.assertRaises(ValueError):acknowledge_executors(branch, {})
        acknowledge_executors(branch, {'root': 'forked-at-seq-7'})
        self.assertEqual(branch.agents['root']['session_id'], 'forked-at-seq-7')
        self.assertFalse(required_contexts(branch.store))
        self.assertTrue(acknowledge_executors(branch, {'root': 'forked-at-seq-7'})['ready'])
        with self.assertRaises(ValueError):restore_bundle(bundle, self.home / 'branch')
        bundle['point']['contexts']['root']['seq'] = 999
        with self.assertRaises(ValueError):restore_bundle(bundle, self.home / 'tampered')

    def test_checkpoint_captures_cursor_and_reuses_only_consistent_version(self):
        backend = self.backend()
        backend.agents['root'] = {'session_id': 'native'}
        info = backend.persistence_info()
        args = dict(expected_commit=info['commit_id'], bindings=info['bindings'],
                    contexts={'root': {'session_id': 'native', 'seq': 3}})
        point = backend.checkpoint(**args)
        args['expected_commit'] = backend.store.head
        self.assertEqual(backend.checkpoint(**args)['id'], point['id'])
        self.assertEqual(backend.store.latest()['agents']['root']['context_cursor']['seq'], 3)
        backend.agents['root']['status'] = 'ready'
        backend.save()
        with self.assertRaises(RuntimeError):backend.checkpoint(**args)
        args.update(expected_commit=backend.store.head, bindings={'root': 'wrong'})
        with self.assertRaises(ValueError):backend.checkpoint(**args)

    def test_restore_validates_every_resource_before_writing(self):
        backend = self.backend()
        document = backend.snapshot()
        document['files'] = {'root-memory.md': 'must not write', '../escape.md': 'outside'}
        with self.assertRaises(ValueError):backend.restore(document)
        self.assertEqual(backend.network.get('root').dataer.read(), '')
        self.assertFalse((self.home / 'escape.md').exists())

    def test_restore_removes_new_files_inside_owned_directory(self):
        from projects.knowledge_archive.nodes.collection import CollectionNode
        codec = saver()
        codec.node_types['knowledge_collection'] = CollectionNode
        directory = self.home / 'runtime' / 'collection'
        directory.mkdir(parents=True)
        (directory / 'committed.md').write_text('before', encoding='utf-8')
        node = CollectionNode(NodeInfo('collection', 'Collection'), directory)
        backend = self.backend(network=Network([node]), saver=codec)
        document = backend.snapshot()
        (directory / 'uncommitted.md').write_text('transient', encoding='utf-8')
        (directory / 'committed.md').write_text('after', encoding='utf-8')
        backend.restore(document)
        self.assertFalse((directory / 'uncommitted.md').exists())
        self.assertEqual((directory / 'committed.md').read_text(encoding='utf-8'), 'before')

    def test_persistence_failure_closes_access_admission(self):
        backend = self.backend()
        with patch.object(backend.store, 'commit', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):backend.save()
        self.assertTrue(backend.failed)
        with self.assertRaises(RuntimeError):
            with backend.node_locks.access_sync(['root']):pass


class PersistentTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_commit_masks_all_uncommitted_fields_and_new_directory_files(self):
        with TemporaryDirectory(prefix='.persistent-txn-', dir=ROOT / 'build') as folder:
            backend = Backend(folder, saver=saver())
            try:
                node = backend.network.get('root')
                counter = Counter()
                node.install(counter)
                node.dataer.write('OLD')
                backend.agents['root'] = {'activity': 'before'}
                backend.bindings['root'] = {'executor': 'harness', 'timeout': 30}
                backend.network.add(Node(NodeInfo('other', 'before')))
                backend.save()
                async with backend.node_locks.transaction(['root']):
                    node.info.name = 'uncommitted'
                    node.dataer.write('NEW')
                    node.update_inputs('event', inputs=[{'id': 'new', 'text': 'uncommitted'}])
                    counter.state['count'] = 99
                    backend.agents['root']['activity'] = 'during'
                    backend.bindings['root']['timeout'] = 50
                    backend.network.get('other').info.name = 'independent'
                    backend.save()
                    record = backend.store.latest()
                    saved = next(entry for entry in record['network']['nodes'] if entry['node_id'] == 'root')
                    self.assertEqual(saved['name'], '起始节点')
                    self.assertEqual(saved['execution']['timeout'], 30)
                    self.assertEqual(saved['tables']['modules'][0]['state']['count'], 0)
                    self.assertEqual(saved['agent']['inputs'], {})
                    self.assertEqual(record['files']['root-memory.md'], 'OLD')
                    self.assertEqual(record['agents']['root']['activity'], 'before')
                    self.assertEqual(next(entry for entry in record['network']['nodes'] if entry['node_id'] == 'other')['name'], 'independent')
                self.assertEqual(backend.store.latest()['files']['root-memory.md'], 'NEW')
            finally:backend.close()
