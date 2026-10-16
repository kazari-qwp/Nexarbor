"""Kills only the fixture-owned Electron/Python process tree, then restores from disk."""
import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXE=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/DeepSeek Harness/DeepSeek Harness.exe'
@unittest.skipUnless(os.name=='nt' and EXE.is_file(),'requires installed Windows Harness')
class NativeCrashTests(unittest.TestCase):
    def test_force_kill_during_mock_thinking_then_restore_both_logs(self):
        import sys
        parent=ROOT/'build/test-data';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='hard-kill-',dir=parent) as folder:
            env=dict(os.environ,ELECTRON_RUN_AS_NODE='1',DATANET_TEST_PYTHON=str(ROOT/'.venv/Scripts/python.exe'))
            command=[str(EXE),'--experimental-vm-modules',str(ROOT/'tests/native_checkpoint_crash.cjs')]
            child=subprocess.Popen(command+['write',folder],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                line=child.stdout.readline().strip()
                if line!='READY':self.fail(line+' '+child.stderr.read()[-5000:])
                stopped=subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                self.assertEqual(stopped.returncode,0);child.wait(timeout=10)
                result=subprocess.run(command+['read',folder],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35,creationflags=subprocess.CREATE_NO_WINDOW)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('PASS hard-killed thinking process',result.stdout)
            finally:
                if child.poll() is None:subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW);child.wait(timeout=10)
                child.stdout.close();child.stderr.close()

if __name__=='__main__':unittest.main()
