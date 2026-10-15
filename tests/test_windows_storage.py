"""Exercise graph storage beyond MAX_PATH and compact external-tool workspaces."""
import os
import shutil
import sys
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'adapters/harness/backend'))
from server import Backend
from datanet.core.storage_paths import storage_path
from datanet.workspace.git import Workspace
from datanet.features.network_presets.decentralized_group.runtime import Plugin
from types import SimpleNamespace


@unittest.skipUnless(os.name == 'nt', 'Windows extended paths')
class WindowsStorageTests(unittest.TestCase):
    def test_long_graph_resources_restore_and_git_worktree(self):
        staging = ROOT / 'build' / 'test-data'
        staging.mkdir(parents=True, exist_ok=True)
        base = storage_path(tempfile.mkdtemp(prefix='datanet-path-', dir=staging))
        directory = base / ('a' * 95) / ('b' * 95) / ('c' * 95)
        self.assertGreater(len(str(directory)), 260)
        backend = None
        try:
            backend = Backend(directory)
            result = backend.dispatch('create_network', dict(actor='root', preset='discussion_group', instance_id='hone-plan', project='完整资料', rounds=2, strength=100))
            self.assertEqual(result['status'], 'ok', result)
            self.assertIn('hone-plan/project', backend.network.nodes)
            backend.close();backend = None
            backend = Backend(directory)
            self.assertIn('hone-plan/project', backend.network.nodes)
            backend.close();backend = None
            plugin = object.__new__(Plugin)
            plugin.r = SimpleNamespace(directory=directory, config={'workspace': str(base)})
            workspace = plugin.workspace({'group_id': 'a-group', 'members': ['group/worker1']})
            self.assertLess(len(str(workspace.personal('group/worker1'))), 260)
            workspace.prepare()
            (workspace.personal('group/worker1') / 'proof.txt').write_text('long path publication', encoding='utf-8')
            result = workspace.invoke('group/worker1', 'publish', 'Test long paths')
            self.assertEqual(result['status'], 'integrated', result)
            self.assertEqual((workspace.main / 'proof.txt').read_text(encoding='utf-8'), 'long path publication')
        finally:
            if backend is not None:
                backend.close()
            def writable_remove(operation, path, _error):
                os.chmod(path, stat.S_IWRITE)
                operation(path)
            shutil.rmtree(base, onerror=writable_remove)
