"""真实项目 Git 提交、Skill 资源及 Python 项目冷装配使用同一清单。"""
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from projects.npc_town.runtime import TownProject
from adapt.harness.backend.transport import Transport
from io import StringIO
ROOT=Path(__file__).resolve().parents[1]
class StudioProjectGit(unittest.TestCase):
    def test_current_project_commit_reopens_actual_nodes_and_tools_without_including_user_staging(self):
        with TemporaryDirectory(prefix='studio-project-roundtrip-',dir=ROOT/'build') as temporary:
            result=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'tests/studio_project_git_integration.mjs'),temporary],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            evidence=json.loads((Path(temporary)/'verification.json').read_text(encoding='utf-8'))
            project=TownProject(Path(temporary)/'fresh-python-runtime',evidence['project'],studio=True)
            transport=Transport(project.backend,StringIO())
            try:
                state=transport.dispatch('studio_state',{});nodes=state['live']['document']['network']['nodes']
                self.assertEqual(len(nodes),45)
                resident=next(node for node in nodes if node['name']=='小砾')
                view=transport.dispatch('executor_prepare',{'actor':resident['node_id']})
                self.assertTrue(any('memory_query'==tool['name'] for tool in view['tools']))
                clock=next(node for node in project.backend.network if node.info.name=='世界时间')
                self.assertIn('第1天',clock.dataer.read())
                self.assertEqual(len(transport.dispatch('studio_catalog',{})['library']),19)
            finally:transport.close()
