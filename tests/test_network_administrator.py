"""在独立进程运行管理员的真实后端验收，避免污染其他测试的组件选择。"""
import os,subprocess,sys,unittest
from pathlib import Path
class NetworkAdministrator(unittest.TestCase):
 def test_permissions_submission_rollback_and_restore(self):
  root=Path(__file__).resolve().parents[1]
  result=subprocess.run([sys.executable,str(root/'scripts/verify_network_administrator.py')],cwd=root,env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,encoding='utf-8',timeout=90)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
