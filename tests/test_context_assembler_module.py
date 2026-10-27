"""实际 Markdown 文件、频道隔离、串联合并与原四路 patch 行为。"""

import asyncio
from copy import deepcopy
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adapt.files.context_documents import read_text
from domain.core import Link, MarkdownNode, Network, Node, NodeInfo
from modules.context_assembler import ContextAssemblerModule, KINDS


class ContextAssemblerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        self.temporary = TemporaryDirectory(prefix='.context-test-', dir=project)
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        self.network = Network()

    def node(self, key, content=None):
        if content is None:
            node = Node(NodeInfo(key, key), bias=-1)
        else:
            file = self.home / (key + '.md')
            file.write_text(content, encoding='utf-8')
            node = MarkdownNode(NodeInfo(key, key), file)
            node.bias = -1
        self.network.add(node)
        return node

    def connect(self, source, target, channel):
        link = Link(target.info.node_id, channel)
        source.links.add(link)
        return link

    def mount(self, node, config=None, *, channels=(*KINDS, 'chain'), strength=4, **kwargs):
        default = {'channels': ['chain'], **{kind + '_channels': [kind] for kind in KINDS}}
        module = ContextAssemblerModule({**default, **(config or {})}, channels=channels, strength=strength, **kwargs)
        node.install(module)
        return module

    async def test_four_channels_are_separate_and_return_file_addresses_without_routes(self):
        root = self.node('root', '本节点记忆不注入')
        module = self.mount(root)
        for key, kind, body in [('system', 'system_prompt', '人格'), ('doc', 'context', '规则'),
                                ('event', 'inputs', '开始'), ('time', 'tail', '第1天')]:
            source = self.node(key, body)
            self.connect(root, source, kind)
        secret = self.node('secret', '不可混用频道')
        self.connect(self.network.get('system'), secret, 'tail')
        packet = await module.preview()
        self.assertEqual(packet['errors'], [])
        self.assertEqual(packet['patch'], {
            'system_prompt': '人格', 'context': [{'id': 'node:doc', 'text': '规则'}],
            'inputs': [{'id': 'node:event/once', 'text': '开始', 'delivery': 'followup'}], 'tail': ['第1天'],
        })
        for source in packet['sources']:
            self.assertEqual(source['file'], str(self.home / (source['source'] + '.md')))
            self.assertEqual(source['resolved_path'], source['file'])
            self.assertNotIn('path', source)
        self.assertNotIn('本节点记忆不注入', str(packet))
        self.assertNotIn('不可混用频道', str(packet))

    async def test_bfs_order_diamond_dedup_and_strength_limit(self):
        root = self.node('root')
        z, a, shared, blocked = [self.node(key, key) for key in ('z-first', 'a-second', 'shared', 'blocked')]
        self.connect(root, z, 'context')
        self.connect(root, a, 'context')
        self.connect(z, shared, 'context')
        self.connect(a, shared, 'context')
        self.connect(shared, z, 'context')
        self.connect(shared, blocked, 'context')
        module = self.mount(root, strength=2)
        # 菱形汇合使 shared 收到两份 1，再加 -1 后仍有 1；额外降低 blocked 确保不可达。
        blocked.bias = -2
        packet = await module.assemble()
        self.assertEqual([item['text'] for item in packet['patch']['context']], ['z-first', 'a-second', 'shared'])
        self.assertEqual(len(packet['sources']), 3)

    async def test_relays_merge_in_outer_bfs_order_even_when_a_peer_finishes_first(self):
        root, b, c, d = [self.node(key) for key in ('root', 'b', 'c', 'd')]
        self.connect(root, b, 'chain')
        self.connect(root, c, 'chain')
        self.connect(b, d, 'chain')
        self.connect(d, root, 'chain')
        module = self.mount(root, {'sources': [{'id': 'self', 'kind': 'system_prompt', 'type': 'text', 'text': 'A'}]})
        for node, text in ((b, 'B'), (c, 'C'), (d, 'D')):
            self.mount(node, {'sources': [{'id': 'self', 'kind': 'system_prompt', 'type': 'text', 'text': text}]})
        relay = b.modules.get(module.module_id)
        original = relay.collect
        finished = []
        async def slow_collect(config=None):
            await asyncio.sleep(.01)
            result = await original(config)
            finished.append('B')
            return result
        relay.collect = slow_collect
        fast = c.modules.get(module.module_id)
        fast_original = fast.collect
        async def fast_collect(config=None):
            result = await fast_original(config)
            finished.append('C')
            return result
        fast.collect = fast_collect
        packet = await module.assemble()
        self.assertEqual(finished, ['C', 'B'])
        self.assertEqual(packet['patch']['system_prompt'], 'A\n\nB\n\nC\n\nD')
        self.assertEqual(len(packet['sources']), 4)

    async def test_downstream_collect_uses_its_own_channels_and_strength(self):
        root, relay_node = self.node('root'), self.node('relay')
        near, far, blocked = [self.node(key, key) for key in ('near', 'far', 'blocked')]
        self.connect(root, relay_node, 'chain')
        self.connect(relay_node, near, 'context')
        self.connect(near, far, 'context')
        self.connect(far, blocked, 'context')
        root_module = self.mount(root, channels=['chain'], strength=1)
        relay = self.mount(relay_node, channels=['context'], strength=2)
        packet = await root_module.assemble()
        self.assertEqual([doc['text'] for doc in packet['patch']['context']], ['near', 'far'])
        relay.strength = 1
        self.assertEqual([doc['text'] for doc in (await root_module.assemble())['patch']['context']], ['near'])
        relay_node.remove(relay)
        self.assertEqual((await root_module.assemble())['patch']['context'], [])

    async def test_reads_current_file_and_current_connections_on_every_request(self):
        root, doc = self.node('root'), self.node('doc', 'first')
        link = self.connect(root, doc, 'tail')
        module = self.mount(root)
        self.assertEqual((await module.preview())['patch']['tail'], ['first'])
        doc.dataer.write('second')
        self.assertEqual((await module.preview())['patch']['tail'], ['second'])
        root.links.remove(link)
        self.assertEqual((await module.preview())['patch']['tail'], [])

    async def test_direct_sources_and_draft_preview_do_not_mutate_config_or_consume_events(self):
        root = self.node('root')
        source = {'id': 'job', 'kind': 'inputs', 'type': 'text', 'text': '任务', 'event_id': 'job-1'}
        module = self.mount(root, {'sources': [source]})
        before = deepcopy(module.config)
        first, second = await module.preview(), await module.preview()
        self.assertEqual(first, second)
        self.assertEqual(first['patch']['inputs'], [{'id': 'node:root:source:job/job-1', 'text': '任务', 'delivery': 'followup'}])
        draft = {'sources': [{'id': 'draft', 'kind': 'system_prompt', 'type': 'text', 'text': '草稿人格'}]}
        self.assertEqual((await module.preview(draft))['patch']['system_prompt'], '草稿人格')
        self.assertEqual(module.config, before)
        self.assertEqual((await module.assemble())['patch']['inputs'], first['patch']['inputs'])

    async def test_file_sources_require_a_port_and_report_failures_individually(self):
        root = self.node('root')
        (self.home / 'guide.md').write_text('\ufeff文件正文', encoding='utf-8')
        sources = [{'id': 'guide', 'kind': 'context', 'type': 'file', 'path': 'guide.md'},
                   {'id': 'missing', 'kind': 'tail', 'type': 'file', 'path': 'missing.md'},
                   {'id': 'escape', 'kind': 'tail', 'type': 'file', 'path': '../escape.md'}]
        module = self.mount(root, {'sources': sources})
        self.assertEqual(len((await module.preview())['errors']), 3)
        module.read_text = partial(read_text, self.home)
        packet = await module.preview()
        self.assertEqual(packet['patch']['context'], [{'id': 'node:root:source:guide', 'text': '文件正文'}])
        self.assertEqual(len(packet['errors']), 2)
        self.assertEqual(packet['sources'][0]['resolved_path'], str(self.home / 'guide.md'))

    async def test_explicit_external_roots_size_limit_and_async_file_port(self):
        root = self.node('root')
        project = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix='.external-context-', dir=project) as external:
            file = Path(external) / 'outside.md'
            file.write_text('明确授权', encoding='utf-8')
            config = {'sources': [{'id': 'ext', 'kind': 'context', 'type': 'file', 'path': str(file)}]}
            async def port(name, roots):
                await asyncio.sleep(0)
                return read_text(self.home, name, roots)
            module = self.mount(root, config, read_text=port)
            self.assertEqual(len((await module.preview())['errors']), 1)
            module.config['document_roots'] = [external]
            self.assertEqual((await module.preview())['patch']['context'][0]['text'], '明确授权')
            file.write_bytes(b'x' * (1024 * 1024 + 1))
            self.assertIn('1 MiB', (await module.preview())['errors'][0]['error'])

    async def test_shared_source_is_deduplicated_without_reordering(self):
        root, relay_node, doc = self.node('root'), self.node('relay'), self.node('doc', '共享资料')
        self.connect(root, relay_node, 'chain')
        self.connect(root, doc, 'context')
        self.connect(relay_node, doc, 'context')
        module = self.mount(root)
        self.mount(relay_node)
        packet = await module.assemble()
        self.assertEqual(packet['errors'], [])
        self.assertEqual(packet['patch']['context'], [{'id': 'node:doc', 'text': '共享资料'}])
        self.assertEqual(len(packet['sources']), 1)

    async def test_a_source_changing_during_collection_is_reported(self):
        root, relay_node, doc = self.node('root'), self.node('relay'), self.node('doc', 'first')
        self.connect(root, relay_node, 'chain')
        self.connect(root, doc, 'context')
        self.connect(relay_node, doc, 'context')
        module, relay = self.mount(root), self.mount(relay_node)
        original = relay.collect
        async def changed(config=None):
            doc.dataer.write('changed')
            return await original(config)
        relay.collect = changed
        packet = await module.assemble()
        self.assertEqual(packet['patch']['context'], [{'id': 'node:doc', 'text': 'first'}])
        self.assertIn('内容发生变化', packet['errors'][0]['error'])

    async def test_config_filters_cannot_expand_module_channel_grant(self):
        root = self.node('root')
        public, private = self.node('public', 'public'), self.node('private', 'private')
        self.connect(root, public, 'public')
        self.connect(root, private, 'secret')
        module = self.mount(root, {'context_channels': ['public', 'secret']}, channels=['public'])
        self.assertEqual([doc['text'] for doc in (await module.assemble())['patch']['context']], ['public'])
        module.config.update(context_channels=['secret'], channel_modes={'context_channels': 'deny'})
        self.assertEqual([doc['text'] for doc in (await module.assemble())['patch']['context']], ['public'])
        module.channels, module.channel_mode = ('secret',), 'deny'
        fresh = self.node('fresh', 'fresh')
        self.connect(root, fresh, 'new-channel')
        self.assertEqual([doc['text'] for doc in (await module.assemble())['patch']['context']], ['public', 'fresh'])

    async def test_collect_requires_an_installed_module(self):
        module = ContextAssemblerModule()
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            await module.collect()
        node = self.node('root')
        node.install(module)
        self.assertEqual((await module.collect())['sources'], [])
        node.remove(module)
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            await module.collect()


if __name__ == '__main__':
    unittest.main()
