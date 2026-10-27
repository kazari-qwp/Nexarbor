"""安装、移除及工具箱聚合的行为回归。"""

import unittest

from domain.core import DependencyError, Installer
from domain.core import Module, Modules
from domain.core import CallableTool, Tools


def tool(name, *modules):
    return CallableTool(name, lambda: name, modules=modules)


class InstallerTests(unittest.TestCase):
    def test_module_dependencies_are_installed_first_and_shared(self):
        common = Module('common')
        middle = Module('middle', modules=[common])
        app = Module('app', modules=[middle, common])
        installer = Installer()
        installer.install(app)
        installer.install(app)
        self.assertEqual(list(installer.modules), [common, middle, app])

    def test_nested_tool_groups_install_dependencies_once(self):
        dependency = Module('data')
        first, second = tool('first', dependency), tool('second', dependency)
        group = Tools([first, Tools([second, first])])
        installer = Installer()
        installer.install(group)
        self.assertEqual(list(installer.modules), [dependency])
        self.assertEqual(list(installer.tools), [first, second])

    def test_module_tools_can_require_other_modules_and_their_owner(self):
        dependency = Module('data')
        app = Module('app')
        own_tool = tool('app.run', app, dependency)
        app.tools._add(own_tool)
        installer = Installer()
        installer.install(app)
        self.assertEqual(list(installer.modules), [dependency, app])
        self.assertEqual(list(installer.tools), [own_tool])
        self.assertTrue(installer.remove(app))
        self.assertEqual(list(installer.modules), [dependency])
        self.assertEqual(list(installer.tools), [])

    def test_tool_mediated_dependency_cycle_is_rejected(self):
        first = Module('first')
        second = Module('second', modules=[first])
        first.tools._add(tool('run', second))
        installer = Installer()
        with self.assertRaisesRegex(DependencyError, 'first -> second -> first'):
            installer.install(first)
        self.assertEqual(len(installer.modules), 0)
        self.assertEqual(list(installer.tools), [])

    def test_module_identifier_conflicts_do_not_replace_existing_instance(self):
        existing = Module('data')
        installer = Installer()
        installer.install(existing)
        app = Module('app', modules=[Module('data')])
        with self.assertRaisesRegex(ValueError, '模块标识冲突'):
            installer.install(app)
        self.assertEqual(list(installer.modules), [existing])

    def test_tool_conflict_rolls_back_new_dependencies_and_tool(self):
        existing_dependency = Module('existing')
        existing_tool = tool('same', existing_dependency)
        installer = Installer()
        installer.install(existing_tool)
        new_dependency = Module('new')
        with self.assertRaisesRegex(ValueError, '工具名称冲突'):
            installer.install(tool('same', new_dependency))
        self.assertEqual(list(installer.modules), [existing_dependency])
        self.assertEqual(list(installer.tools), [existing_tool])

    def test_tool_group_cycle_rolls_back_already_added_dependencies(self):
        installer = Installer()
        dependency = Module('dependency')
        invalid = Module('invalid', modules=[dependency], tools=[installer.tools])
        with self.assertRaisesRegex(ValueError, '循环包含'):
            installer.install(invalid)
        self.assertEqual(len(installer.modules), 0)
        self.assertEqual(list(installer.tools), [])

    def test_module_in_use_cannot_be_removed_but_dependencies_are_retained(self):
        dependency = Module('data')
        app = Module('app', modules=[dependency])
        installer = Installer()
        installer.install(app)
        with self.assertRaisesRegex(DependencyError, '模块 app'):
            installer.remove('data')
        self.assertTrue(installer.remove('app'))
        self.assertIs(installer.modules.get('data'), dependency)
        self.assertTrue(installer.remove('data'))
        self.assertFalse(installer.remove('data'))

    def test_standalone_tool_blocks_dependency_removal(self):
        dependency = Module('data')
        action = tool('query', dependency)
        installer = Installer()
        installer.install(action)
        with self.assertRaisesRegex(DependencyError, '工具 query'):
            installer.remove(dependency)
        self.assertTrue(installer.remove(action))
        self.assertIs(installer.modules.get('data'), dependency)
        self.assertTrue(installer.remove(dependency))

    def test_external_reference_to_owned_tool_still_blocks_removal(self):
        app = Module('app')
        action = tool('run', app)
        app.tools._add(action)
        installer = Installer()
        installer.install(app)
        installer.install(action)
        with self.assertRaisesRegex(DependencyError, '工具 run'):
            installer.remove(app)
        self.assertTrue(installer.remove(action))
        self.assertTrue(installer.remove(app))

    def test_node_module_aggregate_is_not_an_installable_tool_group(self):
        installer = Installer()
        with self.assertRaises(ValueError):
            installer.install(Tools([installer.modules.tools]))
        self.assertEqual(list(installer.tools), [])

    def test_module_aggregate_cannot_be_modified_as_an_ordinary_toolbox(self):
        installer = Installer()
        with self.assertRaises(ValueError):
            installer.remove(installer.modules.tools)

    def test_binding_empty_containers_preserves_their_identity(self):
        modules, tools = Modules(), Tools()
        installer = Installer(modules, tools)
        self.assertIs(installer.modules, modules)
        self.assertIs(installer.tools, tools)
        self.assertIn(modules.tools, tools.members)

    def test_installed_module_dependencies_are_not_revisited(self):
        class ObservedModule(Module):
            reads = 0

            @property
            def modules(self):
                self.reads += 1
                return super().modules

        existing = ObservedModule('existing', modules=[Module('base')])
        installer = Installer()
        installer.install(existing)
        reads = existing.reads
        installer.install(Module('new', modules=[existing]))
        installer.install(tool('query', existing))
        installer.install(existing)
        self.assertEqual(existing.reads, reads)

    def test_installed_tool_dependencies_are_not_revisited(self):
        class ObservedDependencies(tuple):
            reads = 0

            def __iter__(self):
                self.reads += 1
                return super().__iter__()

        existing = tool('existing', Module('base'))
        existing.modules = ObservedDependencies(existing.modules)
        installer = Installer()
        installer.install(existing)
        reads = existing.modules.reads
        installer.install(Module('new'))
        installer.install(tool('query'))
        installer.install(existing)
        self.assertEqual(existing.modules.reads, reads)

    def test_invalid_dependency_is_rejected(self):
        installer = Installer()
        with self.assertRaisesRegex(TypeError, 'Module 实例'):
            installer.install(tool('query', None))
        self.assertEqual(len(installer.modules), 0)

    def test_remove_does_not_match_a_different_module_instance_by_accident(self):
        app = Module('app')
        installer = Installer()
        installer.install(app)
        with self.assertRaises(ValueError):
            installer.remove(Module('app'))
        self.assertIs(installer.modules.get('app'), app)


if __name__ == '__main__':
    unittest.main()
