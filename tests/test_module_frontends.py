"""可选页面的发布完整性、路径检查和真实测试收集；不调用模型。"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'extensions/development/capabilities/component_studio/python'),
              str(ROOT/'extensions/foundation/capabilities/module_sdk/python')]
from datanet.studio.contract import manifest
from datanet.studio.service import Studio,GUIDES


class ModuleFrontendTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'build/module-frontend-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        backend=SimpleNamespace(directory=Path(self.temp.name),
            components=SimpleNamespace(standard_modules={},module_types={},module_owners={}),
            modules=SimpleNamespace(instances={}))
        self.studio=Studio(backend)
        self.work=self.studio.create({'sample':'blank'})
        self.folder=self.studio.folder(self.work['id'])
    def tearDown(self):self.studio.close();self.temp.cleanup()
    def save(self,name,text):
        old=self.studio.read({'id':self.work['id']})['files'].get(name,'')
        return self.studio.save(dict(id=self.work['id'],file=name,content=text,expected=hashlib.sha256(old.encode()).hexdigest()))
    def page(self,entry='ui.html',**extra):
        self.save('ui.html','<!doctype html><html><head><title>配置</title></head><body>元数据</body></html>')
        spec=json.loads((self.folder/'module.json').read_text(encoding='utf-8'))
        spec['frontend']=dict(entry=entry,title='测试页面',height=320,**extra)
        self.save('module.json',json.dumps(spec,ensure_ascii=False))
    def check(self):
        job=self.studio.validate({'id':self.work['id'],'timeout':15});deadline=time.monotonic()+25
        while job['status']=='running' and time.monotonic()<deadline:
            time.sleep(.05);job=self.studio.job({'job':job['id']})
        self.assertNotEqual(job['status'],'running',job)
        return job
    def test_no_frontend_keeps_original_contract(self):
        self.assertIsNone(self.studio.frontend({'id':self.work['id']}))
        self.assertEqual(self.check()['status'],'passed')
    def test_creation_folder_survives_work_copy_read_publish_and_fork(self):
        work=self.studio.create({'sample':'blank','display_folder':'maker-folder'})
        self.work=work;self.folder=self.studio.folder(work['id'])
        self.assertEqual(self.studio.read({'id':work['id']})['display_folder'],'maker-folder')
        self.assertEqual(self.check()['status'],'passed')
        release=self.studio.publish({'id':work['id']})
        self.assertEqual(release['display_folder'],'maker-folder')
        fork=self.studio.fork({'module':release['id']})
        self.assertEqual(fork['display_folder'],'maker-folder')
    def test_preview_reads_html_without_importing_python(self):
        self.page();self.save('module.py',"raise RuntimeError('页面预览不应执行 Python')\n")
        result=self.studio.frontend({'id':self.work['id']})
        self.assertEqual(result['title'],'测试页面');self.assertIn('元数据',result['html'])
    def test_frontend_is_validated_before_module_import(self):
        self.page();self.save('module.py',"raise RuntimeError('不应执行')\n")
        for entry in ('../outside.html','/outside.html','C:/outside.html','ui\\page.html','ui.js','missing.html'):
            with self.subTest(entry=entry):
                spec=json.loads((self.folder/'module.json').read_text(encoding='utf-8'));spec['frontend']['entry']=entry
                self.save('module.json',json.dumps(spec))
                with self.assertRaises(ValueError):manifest(self.folder)
    def test_unknown_frontend_privileges_are_rejected(self):
        self.page(network=True)
        with self.assertRaises(Exception):manifest(self.folder)
    def test_optional_preview_is_display_metadata_without_external_image_requests(self):
        spec=json.loads((self.folder/'module.json').read_text(encoding='utf-8'))
        spec.update(description='计数器',preview='data:image/svg+xml,%3Csvg%20xmlns="http://www.w3.org/2000/svg"/%3E')
        self.save('module.json',json.dumps(spec));self.assertEqual(manifest(self.folder)['description'],'计数器')
        for invalid in ('https://example.com/preview.png','file:///C:/preview.png','data:text/html,hello'):
            spec['preview']=invalid;self.save('module.json',json.dumps(spec))
            with self.assertRaises(Exception):manifest(self.folder)
    def test_html_limits_are_checked(self):
        self.page();(self.folder/'ui.html').write_bytes(b'x'*(1024*1024+1))
        with self.assertRaisesRegex(ValueError,'1 MiB'):manifest(self.folder)
        (self.folder/'ui.html').write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError):manifest(self.folder)
    def test_page_is_fingerprinted_published_and_loaded_as_readonly(self):
        self.page();job=self.check();self.assertEqual(job['status'],'passed',job['log'])
        release=self.studio.publish({'id':self.work['id']})
        self.assertEqual(self.studio.frontend({'module':release['id']})['title'],'测试页面')
        self.assertTrue(self.studio.release_read({'module':release['id']})['readOnly'])
        self.assertIn('ui.html',self.studio.release_read({'module':release['id']})['files'])
        self.save('ui.html','<html>修改页面</html>')
        with self.assertRaisesRegex(ValueError,'Test the current source'):self.studio.publish({'id':self.work['id']})
        released=self.studio.root/release['folder']/'ui.html';released.write_text('篡改',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'源码发生变化'):self.studio.frontend({'module':release['id']})
    def test_all_three_guides_are_current_and_readonly(self):
        for name in GUIDES:
            self.assertNotIn(name,self.work['files']);self.assertIn(name,self.work['references'])
            with self.assertRaises(PermissionError):self.save(name,'替换规范')
        (self.folder/'FRONTEND_GUIDE.md').write_text('旧规范',encoding='utf-8')
        self.studio.prepare_agent({'id':self.work['id']})
        self.assertNotEqual((self.folder/'FRONTEND_GUIDE.md').read_text(encoding='utf-8'),'旧规范')
    def test_uncollected_test_functions_cannot_pass_validation(self):
        self.save('tests/test_not_collected.py','def test_wrong():\n    assert False\n')
        job=self.check();self.assertEqual(job['status'],'failed',job)
        self.assertIn('未收集到测试',job['log'])

    def test_component_files_exclude_host_guides_and_dependency_references(self):
        dependencies=self.folder/'dependencies';dependencies.mkdir(exist_ok=True)
        (dependencies/'catalog.json').write_text('[]',encoding='utf-8')
        data=self.studio.read({'id':self.work['id']})
        self.assertEqual(set(data['files']),{'module.py','module.json','example.json','README.md'})
        self.assertIn('dependencies/catalog.json',data['references'])
        self.assertTrue((self.folder/'AGENTS.md').is_file())
        job=self.check();self.assertEqual(job['status'],'passed',job['log'])
        release=self.studio.publish({'id':self.work['id']})
        published=self.studio.release_read({'module':release['id']})
        self.assertNotIn('AGENTS.md',published['files']);self.assertIn('AGENTS.md',published['references'])

    def test_delete_optional_file_archives_it_and_invalidates_validation(self):
        job=self.check();self.assertEqual(job['status'],'passed',job['log'])
        original=self.work['files']['README.md']
        value=self.studio.delete_file(dict(id=self.work['id'],file='README.md',expected=hashlib.sha256(original.encode()).hexdigest()))
        self.assertNotIn('README.md',value['files'])
        archived=list((self.studio.root/'trash/files').glob('*/README.md'))
        self.assertEqual(len(archived),1);self.assertEqual(archived[0].read_text(encoding='utf-8'),original)
        with self.assertRaisesRegex(ValueError,'Test the current source'):self.studio.publish({'id':self.work['id']})

    def test_delete_rejects_necessary_files_references_stale_edits_and_active_work(self):
        for name in ('module.py','module.json','example.json','AGENTS.md'):
            with self.subTest(file=name),self.assertRaises(PermissionError):self.studio.delete_file(dict(id=self.work['id'],file=name))
        with self.assertRaises(ValueError):self.studio.delete_file(dict(id=self.work['id'],file='../outside.py'))
        with self.assertRaisesRegex(ValueError,'文件已变化'):self.studio.delete_file(dict(id=self.work['id'],file='README.md',expected='stale'))
        self.studio.workspace_busy=lambda id:True
        with self.assertRaisesRegex(ValueError,'先停止'):self.studio.delete_workspace(dict(id=self.work['id'],expected=self.work['digest']))
        with self.assertRaisesRegex(ValueError,'先停止'):self.studio.delete_file(dict(id=self.work['id'],file='README.md'))
        self.assertTrue((self.folder/'README.md').is_file())

    def test_delete_work_copy_preserves_published_release_and_files(self):
        job=self.check();self.assertEqual(job['status'],'passed',job['log'])
        release=self.studio.publish({'id':self.work['id']})
        with self.assertRaisesRegex(ValueError,'工作副本已变化'):self.studio.delete_workspace(dict(id=self.work['id'],expected='stale'))
        self.studio.delete_workspace(dict(id=self.work['id'],expected=self.studio.read({'id':self.work['id']})['digest']))
        self.assertFalse(self.folder.exists());self.assertEqual(self.studio.catalog()['workspaces'],[])
        archive=list((self.studio.root/'trash/workspaces').glob(self.work['id']+'-*'))
        self.assertEqual(len(archive),1);self.assertTrue((archive[0]/'module.py').is_file())
        self.assertIn('module.py',self.studio.release_read({'module':release['id']})['files'])

    def deletion_backend(self):
        backend=self.studio.backend
        backend.network=SimpleNamespace(nodes={},signals=SimpleNamespace(_active=False))
        backend.modules.executing=0;backend.node_locks=SimpleNamespace(lifecycle=lambda:None)
        return backend

    def test_delete_release_removes_owned_files_and_suppresses_standard_reinstall(self):
        self.assertEqual(self.check()['status'],'passed');release=self.studio.publish({'id':self.work['id']});backend=self.deletion_backend();name=release['id']
        backend.components.standard_modules={name:dict(folder=self.folder,manifest=release['manifest'])}
        path=self.studio.root/release['folder'];self.assertTrue(path.exists())
        info=self.studio.release_delete_info({'module':name});self.assertTrue(info['canDelete']);self.assertGreater(len(info['files']),0)
        result=self.studio.delete_release({'module':name,'confirm':name});self.assertGreater(result['filesDeleted'],0);self.assertFalse(path.exists());self.assertTrue((self.folder/'module.py').exists())
        self.studio.close();self.studio=Studio(backend);self.assertNotIn(name,self.studio.library);self.assertNotIn(name,backend.components.module_types)

    def test_delete_release_refuses_live_draft_dependency_and_external_folder(self):
        self.assertEqual(self.check()['status'],'passed');release=self.studio.publish({'id':self.work['id']});backend=self.deletion_backend();name=release['id'];path=self.studio.root/release['folder']
        backend.network.nodes={'a':SimpleNamespace(node_id='a',modules={name:{}})}
        with self.assertRaisesRegex(ValueError,'运行节点'):self.studio.delete_release({'module':name,'confirm':name})
        backend.network.nodes={};(self.studio.root/'draft.json').write_text(json.dumps({'document':{'network':{'nodes':[dict(node_id='b',modules={name:{}})]}}}),encoding='utf-8')
        self.assertIn('待应用草稿',self.studio.release_delete_info({'module':name})['reason']);(self.studio.root/'draft.json').unlink()
        self.studio.library['dependent']={'manifest':{'requires':[name]}}
        self.assertIn('依赖模块',self.studio.release_delete_info({'module':name})['reason']);self.studio.library.pop('dependent')
        old=release['folder'];release['folder']='../outside'
        with self.assertRaisesRegex(ValueError,'不一致'):self.studio.release_delete_info({'module':name})
        release['folder']=old;self.assertTrue((path/'module.py').exists())


if __name__=='__main__':unittest.main()
