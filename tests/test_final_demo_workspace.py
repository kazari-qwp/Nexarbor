"""最终演示源 Workspace/日志模块：真实 Git 与官方终端；不调用模型。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from domain.core import Node,NodeInfo,Network
from projects.discussion_collaboration.modules.git_workspace import GitWorkspaceModule
from projects.discussion_collaboration.modules.execution_logs import ExecutionLogsModule
from test_git_integrator import OfficialTerminal
ROOT=Path(__file__).resolve().parents[1]

class FinalDemoWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=TemporaryDirectory(prefix='final-demo-workspace-',dir=ROOT/'build');self.addCleanup(self.folder.cleanup);self.directory=Path(self.folder.name)
        self.node=Node(NodeInfo('group','Group'));self.git=GitWorkspaceModule(self.directory);self.logs=ExecutionLogsModule(self.directory);self.node.install(self.git);self.node.install(self.logs);self.network=Network([self.node])

    async def test_publish_snapshot_source_results_and_exact_original_git_layout(self):
        prepared=await self.git.prepare(members=['a','b']);own=Path(prepared['members']['a'])
        (own/'test_app.py').write_text('assert 2+2==4\n',encoding='utf-8');published=await self.git.publish(actor='a',message='source and test')
        self.assertEqual(published['status'],'integrated')
        (own/'result.txt').write_text('actual supplied test log',encoding='utf-8')
        proposal=await self.git.proposal(actor='a',test_scripts=['test_app.py'],test_results=['result.txt'])
        self.assertEqual((Path(proposal['source_path'])/'test_app.py').read_text(encoding='utf-8'),'assert 2+2==4\n')
        (Path(published['integrated_path'])/'test_app.py').write_text('later uncommitted content',encoding='utf-8')
        self.assertEqual((Path(proposal['source_path'])/'test_app.py').read_text(encoding='utf-8'),'assert 2+2==4\n')
        self.assertEqual(json.loads(Path(proposal['manifest_path']).read_text(encoding='utf-8'))['commit'],(await self.git.repository())['head_commit'])
        with self.assertRaises(PermissionError):await self.git.inspect(actor='outsider')

    async def test_proposal_rejects_script_outside_committed_source(self):
        await self.git.prepare(members=['a'])
        with self.assertRaisesRegex(ValueError,'测试脚本'):await self.git.proposal(actor='a',test_scripts=['../outside.py'])

    async def test_log_actor_time_filter_and_pagination_keep_original_evidence(self):
        home=self.directory/'.nexarbor/command-logs';home.mkdir(parents=True)
        for id,actor,start in [('old','a',1),('own','a',3),('other','b',4)]:
            (home/(id+'.json')).write_text(json.dumps(dict(id=id,actor=actor,started_at=start,finished_at=start+1,result={'stdout':'evidence'})),encoding='utf-8')
        rows=await self.logs.collect(actor='a',since=2);self.assertEqual([r['id'] for r in rows],['own'])
        page=await self.logs.query(actor='a',since=2,action='read',log_id='own',offset=1,limit=2);self.assertEqual(len(page['lines']),2)
        with self.assertRaisesRegex(ValueError,'Unknown command log'):await self.logs.query(actor='a',action='read',log_id='other')

    async def test_actual_official_terminal_creates_source_log_consumed_by_module(self):
        terminal=OfficialTerminal(self.directory)
        try:
            await terminal.start();result=await terminal.request('invoke',{'actor':'worker','name':'pwsh','arguments':{'command':'Write-Output FINAL_DEMO_COMMAND','description':'Validate original command log path'}})
            self.assertFalse(result['isError']);rows=await self.logs.collect(actor='worker');self.assertEqual(len(rows),1)
            self.assertIn('FINAL_DEMO_COMMAND',Path(rows[0]['path']).read_text(encoding='utf-8'));self.assertEqual(await self.logs.collect(actor='outsider'),[])
        finally:await terminal.close()
