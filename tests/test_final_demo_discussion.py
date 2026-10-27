"""最终演示原讨论协议，经真实 Module/access、信号与 Markdown 文件执行。"""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.runtime.backend import Backend
from app.runtime.module_signals import ModuleSignals
from app.studio.service import Studio
from domain.agent import MarkdownAgentNode
from domain.core import Network,Node,NodeInfo,MarkdownNode,Link
ROOT=Path(__file__).resolve().parents[1]
MODULES=ROOT/'projects/discussion_collaboration/modules'

class FinalDemoDiscussion(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(prefix='final-discussion-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name);runtime=self.folder/'runtime';runtime.mkdir()
        nodes=[Node(NodeInfo('root','根')),Node(NodeInfo('group','讨论组'))]
        for name in ('board','notebook','output'):
            file=runtime/(name+'.md');file.write_text('',encoding='utf-8');nodes.append(MarkdownNode(NodeInfo(name,name),file))
        for name in ('leader','recorder','member'):
            file=runtime/(name+'.md');file.write_text('',encoding='utf-8');nodes.append(MarkdownAgentNode(NodeInfo(name,name),file))
        self.library={key:MODULES/name for key,name in [('discussion.group','discussion_group'),('discussion.member','discussion_member'),('groups.control','groups_control')]}
        self.calls=[];self.final_write=True;self.skip_leader=False
        async def run(actor,message):
            group=self.backend.network.get('group').modules.get('discussion.group');member=self.backend.network.get(actor).modules.get('discussion.member');context=await group.context()
            self.calls.append(dict(actor=actor,phase=context['phase'],round=context['round'],previous=(await member.read_round())['previous_submitted']))
            await asyncio.sleep(.01)
            if context['phase']=='finalizing':
                if self.final_write:await member.write_output(content='CSV 转嵌套 JSON 的共同方案')
            else:
                if actor=='recorder':await member.write_notebook(content='记录第'+str(context['round'])+'轮');await member.write_output(content='草稿')
                if not (actor=='leader' and self.skip_leader):
                    result=await member.submit_round(content=actor+' round '+str(context['round']));self.assertTrue(result['conclude'])
            return dict(status='completed')
        self.run_agent=run
        def configure(backend):Studio(backend,self.library,project_directory=self.folder,agent_run=run)
        self.configure=configure;self.backend=Backend(runtime,network=Network(nodes),configure=configure)
        self.backend_closed=False
        async def close_backend():
            if not self.backend_closed:await self.backend.signals.close();self.backend.close();self.backend_closed=True
        self.addAsyncCleanup(close_backend)
        await self.backend.studio.mount({'node':'root','module':'groups.control','access':dict(channels=['discussion'],strength=6)})
        await self.backend.studio.mount({'node':'group','module':'discussion.group','config':dict(board='board',notebook='notebook',output='output',rounds=2),'access':dict(channels=['discussion','self'],strength=6)})
        group=self.backend.network.get('group');self.backend.network.get('root').links.add(Link('group',['discussion']))
        for name in ('board','notebook','output'):group.links.add(Link(name,['self']))
        for actor in ('leader','recorder','member'):
            await self.backend.studio.mount({'node':actor,'module':'discussion.member','config':dict(group_module='discussion.group',channel='discussion',role=actor),'access':dict(channels=['discussion'],strength=6)})
            group.links.add(Link(actor,['discussion','discussion.round']));self.backend.network.get(actor).links.add(Link('group',['discussion','discussion.round']))
        self.signals=ModuleSignals(self.backend.signals);self.signals.refresh()

    async def test_original_rounds_final_recorder_and_cold_reopen(self):
        control=self.backend.network.get('root').modules.get('groups.control')
        result=await asyncio.wait_for(control.datanet_discuss(task='制定CSV转换方案'),10)
        self.assertEqual(result['status'],'ok');self.assertEqual(result['output'],'CSV 转嵌套 JSON 的共同方案')
        self.assertEqual(len(self.calls),7);self.assertEqual({call['actor'] for call in self.calls if call['phase']=='finalizing'},{'recorder'})
        for call in self.calls:
            if call['round']==2:self.assertEqual(set(call['previous']),{'leader','recorder','member'})
        records=self.backend.signals.records;self.assertEqual(len(records),3)
        self.assertTrue(all(record['status']=='completed' and record['returned'] for record in records.values()))
        self.assertTrue(Path(result['archive_path']).is_relative_to(self.folder/'workspace/discussions'))
        self.assertEqual(Path(result['archive_path']).read_text(encoding='utf-8'),result['output'])
        self.backend.save(full=True);await self.backend.signals.close();self.backend.close();self.backend_closed=True
        restored=Backend(self.folder/'runtime',configure=self.configure)
        try:
            self.assertEqual((await restored.network.get('group').modules.get('discussion.group').status())['phase'],'completed')
            self.assertEqual(restored.network.get('output').dataer.read(),result['output'])
        finally:await restored.signals.close();restored.close()

    async def test_stale_output_is_not_accepted_without_this_run_final_write(self):
        self.final_write=False;group=self.backend.network.get('group').modules.get('discussion.group')
        with self.assertRaisesRegex(ValueError,'FINAL_OUTPUT_NOT_CONFIRMED'):await asyncio.wait_for(group.discuss(task='必须本次定稿'),10)
        self.assertEqual((await group.status())['phase'],'interrupted')
        self.assertEqual(self.backend.network.get('output').dataer.read(),'草稿')

    async def test_leader_failure_interrupts_original_pulse_and_wrong_channel_blocks_group_call(self):
        control=self.backend.network.get('root').modules.get('groups.control');self.backend.network.get('root').links.remove(next(iter(self.backend.network.get('root').links)))
        with self.assertRaisesRegex(ValueError,'唯一的小组入口'):await control.datanet_discuss(task='不可越过连线')
        self.skip_leader=True;group=self.backend.network.get('group').modules.get('discussion.group')
        with self.assertRaisesRegex(RuntimeError,'pulse did not complete'):await asyncio.wait_for(group.discuss(task='Leader未提交'),10)
        self.assertEqual((await group.status())['phase'],'interrupted')
