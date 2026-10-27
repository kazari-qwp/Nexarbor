"""最终协作协议：真实Git成果与测试材料→通知全体→投票→归档结束。"""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from app.runtime.backend import Backend
from app.runtime.module_signals import ModuleSignals
from app.studio.service import Studio
from domain.agent import MarkdownAgentNode
from domain.core import Network,Node,NodeInfo,Link
ROOT=Path(__file__).resolve().parents[1];MODULES=ROOT/'projects/discussion_collaboration/modules'

class FinalDemoCollaboration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(prefix='final-collaboration-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name);runtime=self.folder/'runtime';runtime.mkdir()
        nodes=[Node(NodeInfo('root','根')),Node(NodeInfo('group','协作组'))]
        for actor in ('a','b','c'):
            file=runtime/(actor+'.md');file.write_text('',encoding='utf-8');nodes.append(MarkdownAgentNode(NodeInfo(actor,actor),file))
        self.done=set();self.ready=asyncio.Event();self.candidate_ready=asyncio.Event();self.calls=[]
        library={key:MODULES/name for key,name in [('collaboration.group','collaboration_group'),('collaboration.member','collaboration_member'),('git.workspace','git_workspace'),('execution.logs','execution_logs'),('groups.control','groups_control')]}
        async def run(actor,message):
            member=self.backend.network.get(actor).modules.get('collaboration.member');self.calls.append(actor)
            claim=await member.datanet_team_claim(action='claim',scope=actor,paths=['component_'+actor+'.py','test_'+actor+'.py'])
            own=Path((await member.datanet_team_workspace(action='inspect'))['personal_path'])
            (own/('component_'+actor+'.py')).write_text('def value(): return '+repr(actor)+'\n',encoding='utf-8')
            (own/('test_'+actor+'.py')).write_text('import unittest\nfrom component_'+actor+' import value\nclass Test(unittest.TestCase):\n def test_value(self): self.assertEqual(value(),'+repr(actor)+')\n',encoding='utf-8')
            published=await member.datanet_team_workspace(action='publish',message=actor+' contribution');self.assertEqual(published['status'],'integrated')
            await member.datanet_team_claim(action='complete',claim_id=claim['id'],evidence='已提交 '+published['commit'])
            self.done.add(actor)
            if len(self.done)==3:self.ready.set()
            await self.ready.wait()
            if actor=='c':
                self.assertEqual((await member.datanet_team_workspace(action='sync'))['status'],'ok')
                process=await asyncio.to_thread(subprocess.run,[sys.executable,'-B','-m','unittest','discover','-s','.','-p','test_*.py'],cwd=own,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.assertEqual(process.returncode,0,process.stderr);(own/'test-results.txt').write_text(process.stdout+process.stderr,encoding='utf-8')
                result=await member.datanet_team_finish(action='propose',content='三个组件及实际测试均已完成',evidence='真实unittest通过',test_scripts=['test_a.py','test_b.py','test_c.py'],test_results=['test-results.txt'])
                self.assertTrue(result['conclude']);self.assertEqual(result['data']['phase'],'review');self.candidate_ready.set()
            else:
                await self.candidate_ready.wait();candidate=(await member.datanet_team_status(section='candidate'))['candidate']
                source=Path(candidate['review']['source_path']);self.assertTrue((source/('component_'+actor+'.py')).is_file())
                result=await member.datanet_team_finish(action='approve',candidate_id=candidate['id'],evidence='已检查不可变候选与测试结果');self.assertTrue(result['conclude'])
            return dict(status='completed')
        def configure(backend):Studio(backend,library,project_directory=self.folder,agent_run=run)
        self.backend=Backend(runtime,network=Network(nodes),configure=configure)
        async def close():await self.backend.signals.close();self.backend.close()
        self.addAsyncCleanup(close)
        await self.backend.studio.mount({'node':'root','module':'groups.control','access':dict(channels=['collaboration'],strength=6)})
        self.backend.network.get('root').links.add(Link('group',['collaboration']))
        for module in ('collaboration.group','git.workspace','execution.logs'):
            await self.backend.studio.mount({'node':'group','module':module,'access':dict(channels=['collaboration'],strength=6)})
        group=self.backend.network.get('group')
        for actor in ('a','b','c'):
            await self.backend.studio.mount({'node':actor,'module':'collaboration.member','config':dict(group_module='collaboration.group',channel='collaboration'),'access':dict(channels=['collaboration'],strength=6)})
            group.links.add(Link(actor,['collaboration','collaboration.work']));self.backend.network.get(actor).links.add(Link('group',['collaboration','collaboration.work']))
        self.signals=ModuleSignals(self.backend.signals);self.signals.refresh()

    async def test_any_member_proposes_materials_all_approve_and_loops_conclude(self):
        root=self.backend.network.get('root').modules.get('groups.control');accepted=await root.datanet_cooperate(action='start',task='三个组件与测试')
        group=self.backend.network.get('group').modules.get('collaboration.group')
        report=await asyncio.wait_for(self.backend.signals.wait(group.group(self.backend.network.get('group'))['signal']),15)
        self.assertEqual(report['status'],'completed',report)
        result=await root.wait_group();self.assertEqual(result['phase'],'completed');self.assertEqual(set(result['candidate']['approvals']),{'a','b','c'})
        self.assertEqual(sorted(self.calls),['a','b','c'],'proposal and approval end each member activity')
        review=result['candidate']['review'];self.assertEqual(len(review['test_scripts']),3);self.assertEqual(len(review['test_results']),1)
        self.assertIn('Ran 3 tests',Path(review['test_results'][0]).read_text(encoding='utf-8'))
        archive=Path(result['archive_path']);self.assertTrue(archive.is_relative_to(self.folder/'workspace/cooperation-archives'));self.assertTrue((archive/'result.md').is_file())
        for actor in ('a','b','c'):
            member=self.backend.network.get(actor).modules.get('collaboration.member');self.assertFalse(member.state['running']);self.assertGreaterEqual(member.state.get('notification',0),1)
        self.assertEqual(self.backend.store.pending(),[])

    async def test_proposal_requires_materials_and_rejection_returns_to_work(self):
        self.signals.clear();group=self.backend.network.get('group').modules.get('collaboration.group');await group.control(action='start',task='人工验证状态门禁')
        await self.backend.signals.wait(group.group(self.backend.network.get('group'))['signal'])
        with self.assertRaisesRegex(ValueError,'测试脚本和真实测试结果'):await group.finish(actor='a',action='propose',content='无材料',evidence='说明')
        own=Path((await group.workspace(actor='a',action='inspect'))['personal_path']);(own/'test_app.py').write_text('assert True\n',encoding='utf-8');await group.workspace(actor='a',action='publish');(own/'results.txt').write_text('actual test evidence',encoding='utf-8')
        proposed=await group.finish(actor='a',action='propose',content='待审',evidence='材料',test_scripts=['test_app.py'],test_results=['results.txt'])
        with self.assertRaisesRegex(ValueError,'验收'):await group.claim(actor='b',action='claim',scope='new',paths=['new.py'])
        rejected=await group.finish(actor='b',action='reject',candidate_id=proposed['candidate']['id'],evidence='发现具体问题')
        self.assertEqual(rejected['phase'],'running');self.assertIsNone(rejected['candidate'])
