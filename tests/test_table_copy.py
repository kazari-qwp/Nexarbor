"""表副本独立增删，复制过程不执行装配、展开或依赖检查。"""

import unittest
from unittest.mock import patch

from domain.core import CallableTool, Installer, Module, Modules, Tools


def action(name):
    return CallableTool(name, lambda: name)


class TableCopyTests(unittest.TestCase):
    def test_tools_copy_preserves_nested_references_and_order_without_flattening(self):
        first = action('first')
        nested = Tools([action('nested')])
        original = Tools([first, nested, action('last')])
        with patch.object(Tools, '__iter__', side_effect=AssertionError('不能展开工具箱')):
            copied = original.copy()
        self.assertIsNot(copied, original)
        self.assertEqual(copied.members, original.members)
        self.assertIs(copied.members[0], first)
        self.assertIs(copied.members[1], nested)
        copied._remove(first)
        copied._add(action('copy-only'))
        self.assertEqual([tool.name for tool in original], ['first', 'nested', 'last'])
        self.assertEqual([tool.name for tool in copied], ['nested', 'last', 'copy-only'])

    def test_tools_copy_does_not_reject_existing_names_or_inspect_dependencies(self):
        first, second = action('same'), action('same')
        # 表复制只搬运现有内容；即使调用方曾绕过安装器，也不进行补装或修复。
        first.modules = (object(),)
        original = Tools([first, second])
        with patch.object(Installer, 'install', side_effect=AssertionError('不能安装')):
            copied = original.copy()
        self.assertEqual(copied.members, (first, second))
        self.assertIs(copied.members[0].modules, first.modules)

    def test_modules_copy_does_not_read_dependencies_or_bind_again(self):
        class UninspectedModule(Module):
            @property
            def modules(self):
                raise AssertionError('不能读取依赖表')

            def _bind(self, node):
                raise AssertionError('不能重新绑定模块')

        module = UninspectedModule('module', tools=[action('owned')])
        original = Modules()
        original._add(module)
        with patch.object(Installer, 'install', side_effect=AssertionError('不能安装')):
            copied = original.copy()
        self.assertIsNot(copied, original)
        self.assertIs(copied.get('module'), module)
        self.assertIsNot(copied.tools, original.tools)
        self.assertEqual(copied.tools.members, (module.tools,))
        self.assertTrue(copied._remove('module'))
        copied._add(Module('copy-only'))
        self.assertIs(original.get('module'), module)
        self.assertIsNone(original.get('copy-only'))
        self.assertEqual([tool.name for tool in original.tools], ['owned'])
        self.assertEqual(list(copied.tools), [])


if __name__ == '__main__':
    unittest.main()
