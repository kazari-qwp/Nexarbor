"""独立进程验证当前数据节点，不污染其他测试的组件选择。"""
import os,subprocess,sys,unittest
from pathlib import Path
class DataNodes(unittest.TestCase):
 def test_resources_copy_permissions_and_restore(self):
  root=Path(__file__).resolve().parents[1]
  result=subprocess.run([sys.executable,str(root/'scripts/verify_data_nodes.py')],cwd=root,env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,encoding='utf-8',timeout=180)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
