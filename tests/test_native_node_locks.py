"""Installed native session SDK checks, with a local mock model and no API use."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
EXE=Path('C:/Users/Dried Fish/AppData/Local/Programs/DeepSeek Harness/DeepSeek Harness.exe')


@unittest.skipUnless(os.name=='nt' and EXE.is_file(),'requires installed Windows Harness')
class NativeNodeLockTests(unittest.TestCase):
    def test_pending_tool_prefix_can_be_captured_and_forked_without_replay(self):
        env=dict(os.environ,ELECTRON_RUN_AS_NODE='1',LOCALAPPDATA=str(EXE.parents[2]))
        result=subprocess.run([str(EXE),'--experimental-vm-modules',str(ROOT/'tests/native_node_lock_positions.cjs')],
            cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('"passed":true',result.stdout)
        print(result.stdout.strip())

    def test_real_harness_tool_collection_still_works_through_new_async_queries(self):
        env=dict(os.environ,ELECTRON_RUN_AS_NODE='1',LOCALAPPDATA=str(EXE.parents[2]))
        result=subprocess.run([str(EXE),'--experimental-vm-modules',str(ROOT/'tests/tool_collector_native.mjs')],
            cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=50,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS requested topology',result.stdout)
        print(result.stdout.strip())


if __name__=='__main__':unittest.main()
