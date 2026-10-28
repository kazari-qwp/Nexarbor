"""原元数据模块：真实模块、频道访问、发布副本和检查点恢复。"""
from copy import deepcopy
from pathlib import Path
import unittest
from app.studio.testing import ModuleHarness
ROOT=Path(__file__).resolve().parents[1]
class MetadataFieldsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h=ModuleHarness(ROOT/'projects/workbench/modules/metadata_fields');self.addAsyncCleanup(self.h.close)
        self.h.add_node('root');self.h.add_node('other')
    async def test_read_keeps_json_types_and_publishes_an_independent_copy(self):
        fields={'text':'中文','number':2,'flag':False,'empty':None,'list':[1,{'a':3}]}
        module=self.h.mount('root',config={'fields':fields});result=await self.h.call('root','read')
        self.assertEqual(result['data'],{'fields':fields});self.assertEqual(module.published,fields)
        result['data']['fields']['list'].append(4);self.assertEqual(module.config['fields'],fields);self.assertEqual(module.published,fields)
    async def test_remote_access_uses_existing_channel_and_strength_rules(self):
        self.h.mount('root');self.h.connect('other','root',channels=['metadata'],threshold=2)
        for strength,channels in [(1,['metadata']),(2,['wrong'])]:
            with self.assertRaises(PermissionError):await self.h.call('root','read',actor='other',channels=channels,strength=strength)
        self.assertEqual((await self.h.call('root','read',actor='other',channels=['metadata'],strength=2))['data'],{'fields':{}})
    async def test_signal_publication_and_persistence_use_real_module_tables(self):
        from types import SimpleNamespace
        module=self.h.mount('root',config={'fields':{'kind':'shop'}})
        await module.on_signal(SimpleNamespace(signal=SimpleNamespace(channels=('metadata.refresh',))))
        snapshot=self.h.backend.snapshot();self.h.backend.restore(snapshot);restored=self.h.network.get('root').modules.get('metadata.fields')
        self.assertEqual(restored.published,{'kind':'shop'});self.assertEqual(await restored.read(),{'fields':{'kind':'shop'}})
