"""节点组件装配与依赖操作的集成验证。"""

import unittest

from domain.core import DependencyError
from domain.core import Module
from domain.core import Node
from domain.core import NodeInfo
from domain.core import CallableTool


class NodeTests(unittest.TestCase):
    def test_plain_node_and_independent_containers(self):
        info = NodeInfo('first', '第一个节点')
        first = Node(info)
        second = Node(NodeInfo('second', '第二个节点'))
        self.assertIs(first.info, info)
        self.assertFalse(hasattr(first, 'dataer'))
        self.assertIsNot(first.tools, second.tools)
        self.assertIsNot(first.modules, second.modules)

    def test_node_delegates_dependency_installation_and_removal(self):
        node = Node(NodeInfo('first', '节点'))
        dependency = Module('data')
        action = CallableTool('query', lambda: 'ok', modules=(dependency,))
        node.install(action)
        self.assertIs(node.modules.get('data'), dependency)
        self.assertEqual(node.tools.list(), [action])
        with self.assertRaises(DependencyError):
            node.remove(dependency)
        self.assertTrue(node.remove(action))
        self.assertIs(node.modules.get('data'), dependency)
        self.assertTrue(node.remove(dependency))

    def test_module_tools_are_visible_and_removed_with_the_module(self):
        action = CallableTool('run', lambda: 'ok')
        module = Module('application', tools=[action])
        node = Node(NodeInfo('first', '节点'))
        node.install(module)
        self.assertEqual(list(node.tools), [action])
        self.assertTrue(node.remove(module))
        self.assertEqual(list(node.tools), [])


if __name__ == '__main__':
    unittest.main()
