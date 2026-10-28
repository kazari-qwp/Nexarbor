"""原发布库的删除边界、文件回滚及真实验证后发布。"""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from app.runtime.backend import Backend
from app.studio.service import Studio,write_json
from domain.core import Network,Node,NodeInfo
ROOT=Path(__file__).resolve().parents[1]

class StudioReleases(unittest.IsolatedAsyncioTestCase):
    async def test_project_release_uses_registered_folder_and_retains_source_on_failure(self):
        with TemporaryDirectory(prefix='studio-release-project-',dir=ROOT/'build') as temp:
            root=Path(temp);folder=root/'modules/custom_folder';folder.mkdir(parents=True)
            files=json.loads((ROOT/'resources/studio/templates/blank.json').read_text(encoding='utf-8'))
            for name,text in files.items():(folder/name).write_text(text,encoding='utf-8')
            write_json(root/'nexarbor.json',{'format':'nexarbor-project/v2','resources':{'modules':{'example.counter':{'folder':'modules/custom_folder'}}}})
            backend=Backend(root/'runtime',network=Network([Node(NodeInfo('node','节点'))]));studio=Studio(backend,project_directory=root)
            try:
                fork=studio.fork({'module':'example.counter'});self.assertEqual(fork['original']['module.py'],files['module.py'])
                await studio.mount({'node':'node','module':'example.counter'})
                info=studio.release_delete_info({'module':'example.counter'});self.assertFalse(info['canDelete']);self.assertIn('运行节点',info['reason'])
                await studio.unmount({'node':'node','module':'example.counter'})
                document=studio.state()['live']['document'];node=document['network']['nodes'][0]
                node['tables']['modules']=[dict(module_id='example.counter')]
                write_json(studio.root/'draft.json',dict(applied=False,document=document))
                self.assertIn('待应用草稿',studio.release_delete_info({'module':'example.counter'})['reason'])
                write_json(studio.root/'draft.json',dict(applied=True))
                manifest_before=(root/'nexarbor.json').read_text(encoding='utf-8');failed=False
                def fail_once(path,value):
                    nonlocal failed
                    if path.name=='library.json' and not failed:failed=True;raise OSError('injected metadata failure')
                    return write_json(path,value)
                with patch('app.studio.service.write_json',side_effect=fail_once):
                    with self.assertRaisesRegex(OSError,'injected'):studio.delete_release({'module':'example.counter','confirm':'example.counter'})
                self.assertEqual((folder/'module.py').read_text(encoding='utf-8'),files['module.py']);self.assertIn('example.counter',studio.library);self.assertEqual((root/'nexarbor.json').read_text(encoding='utf-8'),manifest_before)
                original_load=studio._load_releases;load_count=0
                def fail_reload_once():
                    nonlocal load_count
                    load_count+=1
                    if load_count==1:raise RuntimeError('injected reload failure after manifest write')
                    return original_load()
                with patch.object(studio,'_load_releases',side_effect=fail_reload_once):
                    with self.assertRaisesRegex(RuntimeError,'injected reload'):studio.delete_release({'module':'example.counter','confirm':'example.counter'})
                self.assertTrue(folder.exists());self.assertEqual((root/'nexarbor.json').read_text(encoding='utf-8'),manifest_before)
                result=studio.delete_release({'module':'example.counter','confirm':'example.counter'})
                self.assertGreater(result['filesDeleted'],0);self.assertFalse(folder.exists());self.assertNotIn('example.counter',studio.library)
                self.assertNotIn('example.counter',json.loads((root/'nexarbor.json').read_text(encoding='utf-8'))['resources']['modules'])
                self.assertTrue(studio.folder(fork['id']).is_dir(),'independent work copy must remain')
                studio.project_modules({});self.assertNotIn('example.counter',studio.library)
            finally:studio.close();backend.close()

    async def test_real_validated_workspace_release_deletes_all_versions_and_protects_standards(self):
        with TemporaryDirectory(prefix='studio-release-work-',dir=ROOT/'build') as temp:
            backend=Backend(temp,network=Network());studio=Studio(backend,{'tool_discovery':ROOT/'modules/tool_discovery'})
            try:
                info=studio.release_delete_info({'module':'tool_discovery'});self.assertFalse(info['canDelete']);self.assertEqual(info['ownership'],'official')
                work=studio.create({'sample':'blank'});job=studio.validate({'id':work['id']});deadline=time.monotonic()+45
                while studio.job({'job':job['id']})['status']=='running' and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(studio.job({'job':job['id']})['status'],'passed')
                release=studio.publish({'id':work['id']});folder=studio.root/release['folder'];self.assertTrue(folder.is_dir())
                fork=studio.fork({'module':release['id']});self.assertIn('module.py',fork['files'])
                studio.delete_release({'module':release['id'],'confirm':release['id']});self.assertFalse(folder.exists());self.assertTrue(studio.folder(work['id']).is_dir())
                self.assertIn('tool_discovery',studio.library)
            finally:studio.close();backend.close()
