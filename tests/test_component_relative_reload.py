"""重新导入多文件组件会刷新辅助文件，同时旧实例保留旧代码。"""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datanet.studio.contract import factory

ROOT = Path(__file__).resolve().parents[1]


class RelativeReloadTests(unittest.TestCase):
    def test_relative_helpers_are_revision_local(self):
        directory = ROOT / 'build/relative-reload-tests'
        directory.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=directory) as temporary:
            folder = Path(temporary)
            spec = {'format': 'nexarbor-module/v3', 'id': 'test.relative', 'version': '0.1.0', 'entry': 'module.py:execute', 'node_types': ['node'], 'requires': [], 'config_schema': {'type': 'object'}, 'state_schema': {'type': 'object'}, 'operations': [], 'signals': []}
            (folder / 'module.json').write_text(json.dumps(spec), encoding='utf-8')
            (folder / 'module.py').write_text('from .helper import VALUE\nfrom datanet.core.module_protocol import ComponentResult\nasync def execute(ctx, activation):\n    return ComponentResult(data=VALUE)\n', encoding='utf-8')
            (folder / 'helper.py').write_text('VALUE="old"\n', encoding='utf-8')
            old = factory(folder)[1]
            (folder / 'helper.py').write_text('VALUE="new revision"\n', encoding='utf-8')
            new = factory(folder)[1]
            self.assertEqual(asyncio.run(old.execute(None, None)).data, 'old')
            self.assertEqual(asyncio.run(new.execute(None, None)).data, 'new revision')


if __name__ == '__main__':
    unittest.main()
