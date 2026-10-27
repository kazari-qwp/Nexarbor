"""原工具收集器的六节点拓扑、来源别名与撤销行为。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jsonschema import ValidationError

from app.runtime.tool_catalog import ToolCatalog
from domain.core import CallableTool, Link, MarkdownNode, Network, Node, NodeInfo
from domain.declared_tool import DeclaredTool
from modules.agent import AgentModule
from modules.tool_discovery import ToolDiscoveryModule, tool_id


class ToolCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.nodes = {str(n): Node(NodeInfo(str(n), str(n)), bias=-1) for n in range(1, 7)}
        self.network = Network(self.nodes.values())
        self.calls = []
        for origin, target in [('1', '2'), ('2', '3'), ('3', '2'), ('2', '4'), ('4', '5'), ('5', '6')]:
            self.nodes[origin].links.add(Link(target, 'tools'))
        for n in range(2, 7):
            node_id = str(n)
            async def run(value=0, node_id=node_id):
                self.calls.append(node_id)
                return dict(node=node_id, value=value)
            self.nodes[node_id].install(DeclaredTool('read_number', run, reference='module:numbers/read',
                description='读取数字', access_channels=('tools',),
                parameters={'type': 'object', 'properties': {'value': {'type': 'integer'}},
                            'additionalProperties': False}))
        self.root = ToolDiscoveryModule('tools', 2)
        self.relay = ToolDiscoveryModule('tools', 10)
        self.nodes['1'].install(self.root)
        self.nodes['3'].install(self.relay)
        self.catalog = ToolCatalog(self.root)

    async def test_original_requested_topology_and_shortest_forwarding_route(self):
        items = await self.root.collect()
        self.assertEqual({item['origin']['node_id'] for item in items}, {'2', '3', '4', '5', '6'})
        self.assertEqual(len(items), 5)
        self.assertEqual(next(item for item in items if item['origin']['node_id'] == '2')['via'], [])
        self.assertEqual(next(item for item in items if item['origin']['node_id'] == '4')['via'], [])
        self.assertEqual(next(item for item in items if item['origin']['node_id'] == '6')['via'], ['3'])
        self.assertEqual(self.calls, [])

    async def test_same_names_have_distinct_stable_aliases_and_origin(self):
        definitions = await self.catalog.refresh()
        self.assertEqual(len(definitions), 5)
        self.assertEqual(len({item['name'] for item in definitions}), 5)
        self.assertTrue(all(item['name'].startswith('mod_') for item in definitions))
        self.assertEqual(await self.catalog.refresh(), definitions)
        self.assertEqual(await ToolCatalog(self.root).refresh(), definitions)
        for entry in self.catalog.entries.values():
            self.assertEqual(entry['tool_id'], tool_id(entry['origin']['node_id'], 'module:numbers/read'))
        self.assertEqual(self.calls, [])

    async def test_can_invoke_six_via_relay_and_return_tool_result(self):
        await self.catalog.refresh()
        entry = next(item for item in self.catalog.entries.values() if item['origin']['node_id'] == '6')
        self.assertEqual(await self.catalog.invoke(entry['alias'], {'value': 42}), {'node': '6', 'value': 42})
        self.assertEqual(self.calls, ['6'])

    async def test_reduced_relay_budget_and_wrong_channel_remove_distant_tools(self):
        self.relay.strength = 1
        self.assertEqual({item['origin']['node_id'] for item in await self.root.collect()}, {'2', '3', '4'})
        self.relay.strength = 10
        self.nodes['3'].links.list()[0].channels = ('other',)
        self.assertEqual({item['origin']['node_id'] for item in await self.root.collect()}, {'2', '3', '4'})

    async def test_retained_alias_and_forged_id_cannot_bypass_revocation(self):
        await self.catalog.refresh()
        six = next(item for item in self.catalog.entries.values() if item['origin']['node_id'] == '6')
        self.nodes['3'].links.remove(self.nodes['3'].links.list()[0])
        with self.assertRaises(PermissionError):
            await self.catalog.invoke(six['alias'], {})
        with self.assertRaises(PermissionError):
            await self.root.invoke(six['tool_id'], {})
        with self.assertRaises(PermissionError):
            await self.catalog.invoke('mod_forged', {})
        self.assertIn(six['alias'], self.catalog.history)
        self.assertNotIn(six['alias'], self.catalog.entries)
        self.assertEqual(self.calls, [])

    async def test_unmounting_relay_revokes_forwarding(self):
        await self.catalog.refresh()
        six = next(item for item in self.catalog.entries.values() if item['origin']['node_id'] == '6')
        self.nodes['3'].remove(self.relay)
        with self.assertRaises(PermissionError):
            await self.catalog.invoke(six['alias'], {})
        self.assertEqual(self.calls, [])

    async def test_removed_tool_and_changed_operation_channels_are_rechecked(self):
        await self.catalog.refresh()
        two = next(item for item in self.catalog.entries.values() if item['origin']['node_id'] == '2')
        tool = self.nodes['2'].tools.list()[0]
        tool.access_channels = ('other',)
        with self.assertRaises(PermissionError):
            await self.catalog.invoke(two['alias'], {})
        tool.access_channels = ('tools',)
        await self.catalog.refresh()
        self.nodes['2'].remove(tool)
        with self.assertRaises(PermissionError):
            await self.catalog.invoke(two['alias'], {})
        self.assertEqual(self.calls, [])

    async def test_arguments_validated_before_side_effect(self):
        await self.catalog.refresh()
        alias = next(iter(self.catalog.entries))
        with self.assertRaises(ValidationError):
            await self.catalog.invoke(alias, {'value': 'bad'})
        self.assertEqual(self.calls, [])

    async def test_saved_history_does_not_restore_executable_permissions(self):
        await self.catalog.refresh()
        saved = self.catalog.snapshot()
        other = ToolCatalog(self.root)
        other.restore(saved)
        self.assertEqual(other.history, self.catalog.history)
        with self.assertRaises(PermissionError):
            await other.invoke(next(iter(other.history)), {})
        self.assertEqual(other.entries, {})
        await other.refresh()
        self.assertTrue(other.entries)

    async def test_returned_descriptors_do_not_mutate_live_definitions(self):
        definitions = await self.catalog.refresh()
        before = deepcopy(self.catalog.entries)
        definitions[0]['parameters']['properties'].clear()
        self.assertEqual(self.catalog.entries, before)

    async def test_private_memory_never_exported_through_relay(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'build') as directory:
            path = Path(directory) / 'memory.md'
            path.write_text('secret', encoding='utf-8')
            memory = MarkdownNode(NodeInfo('memory', 'memory'), path)
            memory.install(AgentModule())
            self.network.add(memory)
            self.nodes['3'].links.add(Link('memory', 'tools'))
            self.assertEqual(len(await self.root.collect()), 5)
            # 本 Agent 可直接使用自己的三个记忆工具，公开收集目录不重复导出。
            self.assertEqual(len(list(memory.tools)), 3)

    async def test_explicit_empty_operation_channels_only_export_locally(self):
        self.nodes['1'].install(DeclaredTool('local', lambda: 1, access_channels=()))
        self.nodes['2'].install(DeclaredTool('remote_local', lambda: 2, access_channels=()))
        names = [item['name'] for item in await self.root.collect()]
        self.assertIn('local', names)
        self.assertNotIn('remote_local', names)

    async def test_denied_tool_channels_and_unattached_local_node(self):
        node = Node(NodeInfo('standalone', 'standalone'))
        discovery = ToolDiscoveryModule(['secret'], 1, channel_mode='deny')
        node.install(discovery)
        node.install(DeclaredTool('public', lambda: 1, access_channels=('tools',)))
        node.install(DeclaredTool('hidden', lambda: 1, access_channels=('secret',)))
        self.assertEqual([item['name'] for item in await discovery.collect()], ['public'])


if __name__ == '__main__':
    unittest.main()
