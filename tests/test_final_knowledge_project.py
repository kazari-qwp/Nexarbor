"""原资料库初始网络、固定模板、节点资源与真实宿主冷恢复。"""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.studio.project import WorkbenchProject
from domain.core import DataNode

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'项目演示/应用2-资料库-初始'

class FinalKnowledgeProject(unittest.TestCase):
    def test_actual_template_data_ownership_and_cold_reopen(self):
        with TemporaryDirectory(prefix='knowledge-project-',dir=ROOT/'build') as temp:
            runtime=Path(temp)/'runtime';host=WorkbenchProject(runtime,PROJECT)
            try:
                backend=host.backend
                self.assertFalse(backend.studio.state()['moduleProblems'])
                self.assertTrue((runtime/'workspace/imports/project-brief.md').exists())
                async def exercise():
                    tools=backend.network.get('root').modules.get('knowledge.tools')
                    await tools.kb_task(content='归档验证',mode='agent')
                    table=await tools.kb_create_node(name='表格',storage='sqlite',schema={'code':'string','n':'integer'})
                    node=backend.network.get(table['node_id']);self.assertIsInstance(node,DataNode)
                    record=await tools.kb_store(collection=table['id'],content={'code':'0001','n':3},key='row')
                    self.assertEqual(node.dataer.read({'method':'key','key':record['id']}).items[0]['content']['code'],'0001')
                    wiki=await tools.kb_create_node(name='原文',storage='wiki')
                    source=await tools.kb_store(collection=wiki['id'],content='# Original\nComplete original.',key='doc')
                    # The existing snapshot service rejects overlapping ownership; every actual node must pass.
                    for id in [table['node_id'],wiki['node_id'],'knowledge']:backend.node_locks.snapshots.capture([id])
                    backend.save(full=True)
                    return record['id'],source['id'],table['node_id']
                record,source,owner=asyncio.run(exercise())
            finally:host.close()
            restored=WorkbenchProject(runtime,PROJECT)
            try:
                async def check():
                    tools=restored.backend.network.get('root').modules.get('knowledge.tools')
                    self.assertEqual((await tools.kb_fetch(id=record))['node_id'],owner)
                    self.assertEqual((await tools.kb_fetch(id=source))['content'],'# Original\nComplete original.')
                    self.assertEqual(len(restored.backend.network),6)
                asyncio.run(check())
            finally:restored.close()

if __name__=='__main__':unittest.main()
