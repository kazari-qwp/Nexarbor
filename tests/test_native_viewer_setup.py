"""Test the native viewer installer without running a client or model."""
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
install=runpy.run_path(str(ROOT/'scripts/open_harness_test_client.py'))['install_viewer']

class NativeViewerSetupTests(unittest.TestCase):
    def test_package_is_resolvable_and_existing_profile_is_preserved(self):
        base=ROOT/'build/viewer-setup-tests';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            profile=Path(folder);workspace=profile/'workspace'
            (profile/'package.json').write_text(json.dumps({'private':True,'dsh':{'profile':{'bundles':['@deepseek-ai/dsh-base']}}}),'utf-8')
            (profile/'cordis.patch.yml').write_text('- id: user-model\n  config:\n    provider: chosen-by-user\n','utf-8')
            manifest={'workspace':str(workspace),'sessions':[{'session_id':'test-session'}]}
            install(profile,manifest);install(profile,manifest)
            check="const {createRequire}=require('node:module');const r=createRequire(process.argv[1]);process.stdout.write(r.resolve('nexarbor-test-session-list'));"
            result=subprocess.run(['node','-e',check,str(profile/'package.json')],capture_output=True,text=True,encoding='utf-8',check=True)
            self.assertEqual(Path(result.stdout),profile/'node_modules/nexarbor-test-session-list/index.js')
            self.assertIn('chosen-by-user',(profile/'cordis.patch.yml').read_text('utf-8'))
            self.assertTrue((profile/'node_modules/nexarbor-test-session-list/editor-launcher.js').exists())
            data=json.loads((profile/'package.json').read_text('utf-8'))
            self.assertEqual(data['dsh']['profile']['bundles'].count('nexarbor-test-session-list'),1)

if __name__=='__main__':unittest.main()
