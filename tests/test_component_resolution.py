"""Dependency failures and isolated component loading."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComponentResolutionTests(unittest.TestCase):
    def isolated(self, code, selection):
        env = dict(os.environ, PYTHONPATH=str(ROOT/'python'), PYTHONDONTWRITEBYTECODE='1',
                   DATANET_COMPONENT_ROOT=str(ROOT/'extensions/multi_agent'),
                   DATANET_COMPONENT_SELECTION=json.dumps(selection), DATANET_COMPONENT_PROFILE='{}')
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_csv_loads_no_agents_or_application(self):
        self.isolated("""
import sys
from datanet.core.component_registry import codecs, enabled_components
assert set(codecs()) == {'node', 'agent', 'text_file', 'pulse', 'csv'}
assert enabled_components() == {'nodes/csv', 'capabilities/csv'}
assert not any(x.startswith('datanet.features') or 'llamaindex_node' in x for x in sys.modules)
""", ['nodes/csv'])

    def test_agent_runtime_has_no_network_management(self):
        self.isolated("""
import tempfile
from datanet.core.backend import Backend
from datanet.core.application import Application
with tempfile.TemporaryDirectory() as folder:
    b=Backend(folder)
    app=Application(b, lambda op,p: {'ok':True}, {})
    assert set(app.plugins)=={'capabilities/agent_runtime','capabilities/context_assembly'}
    assert not app.tools and not app.boxes
    assert 'create_network' not in b.components.routes
    assert 'ensure_agent_node' in b.components.routes
    b.close()
""", ['capabilities/agent_runtime'])

    def test_project_root_recipe_loads_its_default_tools(self):
        self.isolated("""
import tempfile
from datanet.core.backend import Backend
from datanet.core.application import Application
with tempfile.TemporaryDirectory() as folder:
    b=Backend(folder)
    app=Application(b,lambda op,p: {'ok':True},dict(rootNetwork='project_root'))
    grant=app.resolve(app.defaults['rootToolboxes'])
    assert 'datanet_create_network' in grant['framework']
    assert 'capabilities/agent_delegation' in app.enabled
    assert 'discussion_group' in b.components.network_presets
    assert 'decentralized_group' in b.components.network_presets
    assert 'number_network' not in b.components.network_presets
    b.close()
""", ['network_presets/project_root'])

    def test_dependency_errors_and_deterministic_order(self):
        from datanet.component_catalog import resolve
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def put(name, dependencies=(), version='0.4.0'):
                path=root/'capabilities'/name/'component.json'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(dict(id='capabilities/'+name,kind='capabilities',version=version,requires=list(dependencies))),encoding='utf-8')
            put('a', ['capabilities/b'])
            with self.assertRaisesRegex(ValueError, 'Missing component dependency'):
                resolve(root,['capabilities/a'])
            put('b', ['capabilities/a'])
            with self.assertRaisesRegex(ValueError, 'dependency cycle'):
                resolve(root,['capabilities/a'])
            put('b')
            self.assertEqual(resolve(root,['capabilities/a'])[1], ['capabilities/b','capabilities/a'])
            put('a',[{'id':'capabilities/b','version':'>=0.5.0'}])
            with self.assertRaisesRegex(ValueError, 'version conflict'):
                resolve(root,['capabilities/a'])

    def test_duplicate_sources_do_not_duplicate_components(self):
        from datanet.component_catalog import resolve
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'common'; source.mkdir()
            p=source/'nodes/test'; p.mkdir(parents=True)
            (p/'component.json').write_text(json.dumps(dict(id='nodes/test',kind='nodes',requires=[])))
            (root/'extension.json').write_text(json.dumps(dict(sources=['common','common'],select=['nodes/test'])))
            self.assertEqual(resolve(root)[1],['nodes/test'])


if __name__ == '__main__':
    unittest.main()
