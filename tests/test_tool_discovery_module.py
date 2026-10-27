"""串联发现按各模块的频道与强度工作，结果保留工具表引用。"""

import unittest
from unittest.mock import patch

from domain.link import Link
from domain.network import Network
from domain.node import Node
from domain.node_info import NodeInfo
from domain.tool import CallableTool, Tools
from domain.tool_discovery_module import ToolDiscoveryModule


def make_network(ids):
    nodes = {key: Node(NodeInfo(key, key), bias=-1) for key in ids}
    for key, node in nodes.items():
        node.install(CallableTool(key + '_tool', lambda key=key: key))
    return Network(nodes.values()), nodes


def names(tools):
    return [tool.name for tool in tools]


class ToolDiscoveryTests(unittest.TestCase):
    def relay_network(self):
        network, nodes = make_network('abcde')
        nodes['a'].links.add(Link('b', 'a', threshold=2))
        nodes['b'].links.add(Link('c', 'b'))
        nodes['c'].links.add(Link('d', 'b'))
        nodes['d'].links.add(Link('e', 'b'))
        root = ToolDiscoveryModule(channels='a', strength=2)
        nodes['a'].install(root)
        return network, nodes, root

    def test_discovers_directly_reachable_node_tool_tables(self):
        network, nodes, root = self.relay_network()
        found = root.discover()
        self.assertIsInstance(found, Tools)
        self.assertEqual(names(found), ['a_tool', 'b_tool'])
        self.assertEqual(found.members, (nodes['a'].tools, nodes['b'].tools))
        self.assertEqual([tool.invoke() for tool in found], ['a', 'b'])

    def test_relay_uses_its_own_channel_and_starting_strength(self):
        network, nodes, root = self.relay_network()
        relay = ToolDiscoveryModule(channels='b', strength=2)
        nodes['b'].install(relay)
        with patch.object(relay, '_discover', wraps=relay._discover) as discover:
            found = root.discover()
        discover.assert_called_once()
        self.assertEqual(names(found), ['a_tool', 'b_tool', 'c_tool', 'd_tool'])
        self.assertNotIn('e_tool', names(found))
        self.assertEqual(found.members, tuple(nodes[key].tools for key in 'abcd'))
        # 外层到 b 的剩余强度是 1；中继从自身配置的 2 开始，所以能够到 d。
        relay.strength = 1
        self.assertEqual(names(root.discover()), ['a_tool', 'b_tool', 'c_tool'])

    def test_relay_settings_can_change_between_discovery_calls(self):
        network, nodes, root = self.relay_network()
        relay = ToolDiscoveryModule(channels='b', strength=2)
        nodes['b'].install(relay)
        self.assertIn('d_tool', names(root.discover()))
        relay.channels = 'a'
        self.assertEqual(names(root.discover()), ['a_tool', 'b_tool'])

    def test_unreachable_relay_is_not_called(self):
        network, nodes = make_network('abcd')
        nodes['a'].links.add(Link('b', 'secret'))
        nodes['a'].links.add(Link('c', 'a', threshold=3))
        nodes['b'].links.add(Link('d', 'b'))
        root = ToolDiscoveryModule(channels='a', strength=2)
        hidden = ToolDiscoveryModule(channels='b', strength=10)
        weak = ToolDiscoveryModule(channels='a', strength=10)
        nodes['a'].install(root)
        nodes['b'].install(hidden)
        nodes['c'].install(weak)
        with patch.object(hidden, '_discover', wraps=hidden._discover) as hidden_call:
            with patch.object(weak, '_discover', wraps=weak._discover) as weak_call:
                self.assertEqual(names(root.discover()), ['a_tool'])
        hidden_call.assert_not_called()
        weak_call.assert_not_called()

    def test_negative_received_strength_does_not_activate_a_relay(self):
        network, nodes = make_network('ab')
        nodes['a'].links.add(Link('b', 'a'))
        nodes['b'].bias = -3
        root = ToolDiscoveryModule(channels='a', strength=2)
        relay = ToolDiscoveryModule(channels='b', strength=10)
        nodes['a'].install(root)
        nodes['b'].install(relay)
        with patch.object(relay, '_discover', wraps=relay._discover) as discover:
            self.assertEqual(names(root.discover()), ['a_tool'])
        discover.assert_not_called()

    def test_repeated_relays_are_only_called_once_per_request(self):
        network, nodes = make_network('abcd')
        for node in nodes.values():
            node.bias = 0
        nodes['a'].links.add(Link('b', 'a'))
        nodes['a'].links.add(Link('c', 'a'))
        nodes['b'].links.add(Link('a', 'b'))
        nodes['b'].links.add(Link('d', 'b'))
        root = ToolDiscoveryModule(channels='a', strength=2)
        relay = ToolDiscoveryModule(channels='b', strength=2)
        nodes['a'].install(root)
        nodes['b'].install(relay)
        with patch.object(root, '_read_nodes', wraps=root._read_nodes) as root_call:
            with patch.object(relay, '_read_nodes', wraps=relay._read_nodes) as relay_call:
                for _ in range(2):
                    found = root.discover()
                    self.assertEqual(set(names(found)), {'a_tool', 'b_tool', 'c_tool', 'd_tool'})
                    self.assertEqual(len(found.members), 4)
        self.assertEqual(root_call.call_count, 2)
        self.assertEqual(relay_call.call_count, 2)

    def test_shared_downstream_relay_does_not_duplicate_tools_or_module_calls(self):
        network, nodes = make_network('abcde')
        for node in nodes.values():
            node.bias = 0
        nodes['a'].links.add(Link('b', 'a'))
        nodes['a'].links.add(Link('c', 'a'))
        nodes['b'].links.add(Link('d', 'b'))
        nodes['c'].links.add(Link('d', 'b'))
        nodes['d'].links.add(Link('e', 'c'))
        root = ToolDiscoveryModule('a', 1)
        nodes['a'].install(root)
        nodes['b'].install(ToolDiscoveryModule('b', 1))
        nodes['c'].install(ToolDiscoveryModule('b', 1))
        last = ToolDiscoveryModule('c', 1)
        nodes['d'].install(last)
        with patch.object(last, '_discover', wraps=last._discover) as discover:
            found = root.discover()
        discover.assert_called_once()
        self.assertEqual(set(names(found)), {key + '_tool' for key in 'abcde'})
        self.assertEqual(len(found.members), 5)

    def test_returned_tool_tables_reflect_later_installation_and_removal(self):
        network, nodes, root = self.relay_network()
        found = root.discover()
        action = CallableTool('new_action', lambda: 'new')
        nodes['b'].install(action)
        self.assertIn(action, list(found))
        nodes['b'].remove(action)
        self.assertNotIn(action, list(found))

    def test_removing_a_relay_changes_the_next_discovery(self):
        network, nodes, root = self.relay_network()
        relay = ToolDiscoveryModule('b', 2)
        nodes['b'].install(relay)
        self.assertIn('d_tool', names(root.discover()))
        nodes['b'].remove(relay)
        self.assertEqual(names(root.discover()), ['a_tool', 'b_tool'])

    def test_empty_channel_configuration_only_discovers_local_tools(self):
        network, nodes, root = self.relay_network()
        root.channels = ()
        self.assertEqual(names(root.discover()), ['a_tool'])

    def test_discovery_requires_an_installed_module(self):
        module = ToolDiscoveryModule('a', 2)
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            module.discover()
        network, nodes = make_network('a')
        nodes['a'].install(module)
        self.assertEqual(names(module.discover()), ['a_tool'])
        nodes['a'].remove(module)
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            module.discover()


if __name__ == '__main__':
    unittest.main()
