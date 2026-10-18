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
            self.assertIn(name,self.work['files'])
            with self.assertRaises(PermissionError):self.save(name,'替换规范')
        (self.folder/'FRONTEND_GUIDE.md').write_text('旧规范',encoding='utf-8')
        self.studio.prepare_agent({'id':self.work['id']})
        self.assertNotEqual((self.folder/'FRONTEND_GUIDE.md').read_text(encoding='utf-8'),'旧规范')
    def test_uncollected_test_functions_cannot_pass_validation(self):
        self.save('tests/test_not_collected.py','def test_wrong():\n    assert False\n')
        job=self.check();self.assertEqual(job['status'],'failed',job)
        self.assertIn('未收集到测试',job['log'])


if __name__=='__main__':unittest.main()
