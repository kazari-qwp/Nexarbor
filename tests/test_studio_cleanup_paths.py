"""The release has a deeper product path; validation must clean deep owned files."""
from pathlib import Path
import unittest
from app.studio.testing import ModuleHarness
from adapt.files.storage_paths import storage_path
ROOT=Path(__file__).resolve().parents[1]

class StudioCleanupPaths(unittest.IsolatedAsyncioTestCase):
    async def test_validation_cleanup_removes_owned_paths_beyond_windows_max_path(self):
        h=ModuleHarness(ROOT/'projects/knowledge_archive/modules/data_local');self.addAsyncCleanup(h.close)
        folder=h.folder;file=folder
        for index in range(8):file=file/('version-'+str(index)+'-'+'a'*32)
        file=file/'payload.json';self.assertGreater(len(str(file)),300)
        physical=storage_path(file);physical.parent.mkdir(parents=True);physical.write_text('{"data":"owned"}',encoding='utf-8')
        await h.close();self.assertFalse(storage_path(folder).exists())
