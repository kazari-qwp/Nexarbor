"""单值节点及网络读取检查，不使用外部存储。"""

import unittest

from datanet.network import Network
from datanet.nodes.node import Node
from datanet.nodes.value_node import ValueNode


class ValueNodeTests(unittest.TestCase):
    def make_node(self, value):
        return ValueNode("value_node", "单值", "test", value)

    def test_value_and_source(self):
        result = self.make_node("说明").get("value")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items, [{"value": "说明"}])
        self.assertEqual(result.sources[0]["node_id"], "value_node")
        self.assertEqual(result.sources[0]["storage"], "memory")

    def test_unknown_key(self):
        result = self.make_node("说明").get("other")
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.items, [])

    def test_empty_and_none_values_are_present(self):
        for value in (None, "", 0, False, [], {}):
            with self.subTest(value=value):
                result = self.make_node(value).get("value")
                self.assertEqual(result.status, "ok")
                self.assertEqual(result.items[0]["value"], value)

    def test_mutable_values_are_isolated(self):
        value = {"settings": [1]}
        node = self.make_node(value)
        value["settings"].append(2)
        result = node.get("value")
        result.items[0]["value"]["settings"].append(3)
        self.assertEqual(node.get("value").items, [{"value": {"settings": [1]}}])

    def test_path_is_only_a_value(self):
        path = "missing/directory/file.txt"
        self.assertEqual(self.make_node(path).get("value").items, [{"value": path}])

    def test_non_string_key_is_rejected(self):
        with self.assertRaises(TypeError):
            self.make_node("说明").get(1)

    def test_network_read_and_scope(self):
        root = Node("root", "入口", None)
        node = self.make_node("说明")
        root.weak_read_interfaces.append(node.interface)
        network = Network()
        network.add_node(root)
        network.add_node(node)
        self.assertEqual(network.get("root", "value", "integrated").status, "not_found")
        result = network.get("root", "value", "federated", "test")
        self.assertEqual(result.items, [{"value": "说明"}])
        self.assertEqual(result.sources[0]["retrieval_path"], ["root", "value_node"])


if __name__ == "__main__":
    unittest.main()
