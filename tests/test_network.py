"""读取范围、读写隔离与环去重的内存图测试。"""

import unittest
from dataclasses import FrozenInstanceError

from datanet.network import Network
from datanet.nodes.node import Node, NodeResult


class CountingNode(Node):
    def __init__(self, node_id):
        super().__init__(node_id, node_id, "test")
        self.calls = 0

    def get(self, key):
        self.calls += 1
        return NodeResult(items=[{"node_id": self.node_id, "key": key}])


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.root = Node("root", "入口", None)
        self.strong = CountingNode("strong")
        self.weak = CountingNode("weak")
        self.write_only = CountingNode("write_only")
        self.network = Network()
        for node in (self.root, self.strong, self.weak, self.write_only):
            self.network.add_node(node)
        self.root.strong_read_interfaces.append(self.strong.interface)
        self.root.weak_read_interfaces.append(self.weak.interface)

    def test_local_does_not_traverse(self):
        self.assertEqual(self.network.get("root", "A", "local").status, "not_found")
        self.assertEqual(self.strong.calls + self.weak.calls, 0)

    def test_integrated_only_follows_strong_reads(self):
        result = self.network.get("root", "A", "integrated")
        self.assertEqual([item["node_id"] for item in result.items], ["strong"])
        self.assertEqual(self.weak.calls, 0)

    def test_federated_follows_both_read_lists(self):
        result = self.network.get("root", "A", "federated")
        self.assertEqual([item["node_id"] for item in result.items], ["strong", "weak"])

    def test_write_lists_do_not_allow_reads(self):
        self.root.strong_write_interfaces.append(self.write_only.interface)
        self.root.weak_write_interfaces.append(self.write_only.interface)
        self.network.get("root", "A", "federated")
        self.assertEqual(self.write_only.calls, 0)

    def test_overlap_and_cycle_only_read_once(self):
        self.root.weak_read_interfaces.append(self.strong.interface)
        self.strong.strong_read_interfaces.append(self.root.interface)
        self.weak.strong_read_interfaces.append(self.strong.interface)
        result = self.network.get("root", "A", "federated")
        self.assertEqual(len(result.items), 2)
        self.assertEqual(self.strong.calls, 1)
        self.assertEqual(self.weak.calls, 1)

    def test_lists_are_independent(self):
        self.assertEqual(self.strong.strong_read_interfaces, [])
        self.assertEqual(self.root.strong_write_interfaces, [])
        self.assertEqual(self.root.weak_write_interfaces, [])

    def test_address_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.root.interface.target_node_id = "changed"

    def test_type_filter_does_not_block_empty_entry(self):
        result = self.network.get("root", "A", "integrated", data_kind="test")
        self.assertEqual(result.status, "ok")


if __name__ == "__main__":
    unittest.main()
