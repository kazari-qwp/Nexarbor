"""真实小镇成品配置与原固定模板宿主验收；不调用模型。"""

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.templates.service import checked_templates
from projects.npc_town.runtime import TownProject

ROOT=Path(__file__).resolve().parents[1]


class TownProjectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='.town-project-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.host=TownProject(self.temp.name);self.addCleanup(lambda:self.host.close())
        template=next(iter(self.host.templates.templates.values()))
        self.template=template['id'];self.actor=template['callers'][0]
        self.arguments={'name':'小芽','parents':['林','悦'],'home':'居民楼A'}

    async def instantiate(self,key='birth-1',**overrides):
        arguments={**self.arguments,**overrides}
        return await self.host.templates.instantiate(self.actor,template=self.template,key=key,arguments=arguments)

    async def test_actual_graph_preserves_agents_resources_and_has_no_legacy_runtime(self):
        backend=self.host.backend
        self.assertEqual(len(backend.network),52);self.assertEqual(len(backend.bindings),7)
        self.assertEqual(len(backend.snapshot()['files']),33)
        for node in backend.network:
            self.assertTrue(type(node).__module__.startswith(('domain.','projects.')))
            if node.node_type!='agent':continue
            self.assertIsNotNone(node.modules.get('tool_discovery'))
            self.assertNotIn('tool_sources',backend.bindings[node.info.node_id])
            tables=await asyncio.to_thread(node.available_tools)
            tools=[tool for group in tables.values() for tool in group]
            self.assertGreater(len(tools),20);self.assertEqual(len({tool.name for tool in tools}),len(tools))
            packet=await node.modules.get('context.assembler').assemble()
            self.assertEqual(packet['errors'],[]);self.assertGreaterEqual(len(packet['sources']),6)

    async def test_registered_real_template_has_fresh_memory_actual_tools_and_fixed_attachments(self):
        first=await self.instantiate();second=await self.instantiate()
        self.assertTrue(second['duplicate']);self.assertEqual(first['node_ids'],second['node_ids'])
        child=self.host.backend.network.get(first['node_ids']['child'])
        self.assertEqual(child.info.name,'小芽');self.assertEqual(child.node_type,'agent')
        self.assertEqual(child.dataer.read(),'')
        self.assertTrue(child.saver.path.is_relative_to(Path(self.temp.name)/'created/templates'))
        self.assertIsNotNone(child.modules.get('tool_discovery'))
        values=(await child.modules.get('records.store').read())['values']
        self.assertEqual(values['name'],'小芽');self.assertEqual(values['home'],'居民楼A')
        self.assertEqual(values['parent_a'],'林');self.assertEqual(values['parent_b'],'悦')
        self.assertTrue(any(edge.target_id==child.info.node_id for edge in self.host.backend.network.get('居民楼A').links))
        self.assertIn(child.info.node_id,self.host.backend.bindings)
        tools=await asyncio.to_thread(child.available_tools)
        names=[tool.name for group in tools.values() for tool in group]
        self.assertEqual(len(names),len(set(names)))
        self.assertIn(child.info.node_id,self.host.backend.signals.bindings)
        self.assertEqual(child.inputs.snapshot(),{})

    async def test_template_identity_arguments_and_fixed_caller_are_enforced(self):
        await self.instantiate()
        with self.assertRaisesRegex(ValueError,'同一实例键'):await self.instantiate(name='different')
        with self.assertRaises(PermissionError):
            await self.host.templates.instantiate('林',template=self.template,key='one',arguments=self.arguments)
        bad=deepcopy(next(iter(self.host.templates.templates.values())))
        bad['bindings'][0]['path']='/network/nodes/0/tables/modules/0/strength'
        with self.assertRaises(ValueError):checked_templates([bad],{node.info.node_id for node in self.host.backend.network})

    async def test_template_write_failure_has_no_half_nodes_edges_bindings_or_receipts(self):
        backend=self.host.backend;count=len(backend.network);bindings=deepcopy(backend.bindings)
        edges={node.info.node_id:tuple(node.links) for node in backend.network}
        with patch.object(backend,'write_documents',side_effect=RuntimeError('file write failed')):
            with self.assertRaisesRegex(RuntimeError,'file write failed'):await self.instantiate()
        self.assertEqual(len(backend.network),count);self.assertEqual(backend.bindings,bindings)
        self.assertEqual(backend.extension_state.get('template_receipts'),{})
        for node in backend.network:self.assertEqual(tuple(node.links),edges[node.info.node_id])
        self.assertEqual(len(self.host.backend.signals.bindings),10)
        self.assertFalse((await self.instantiate())['duplicate'])

    async def test_template_commit_failure_restores_graph_and_owned_files(self):
        backend=self.host.backend;before=len(backend.network)
        with patch.object(backend,'save',side_effect=RuntimeError('commit fixture failure')):
            with self.assertRaisesRegex(RuntimeError,'commit fixture failure'):await self.instantiate()
        self.assertEqual(len(backend.network),before)
        self.assertEqual(list((Path(self.temp.name)/'created').rglob('*.md')),[])
        self.assertEqual(backend.extension_state.get('template_receipts'),{})
        self.assertFalse((await self.instantiate())['duplicate'])

    async def test_template_and_new_agent_survive_cold_reopen_with_same_receipt(self):
        result=await self.instantiate();child_id=result['node_ids']['child']
        child=self.host.backend.network.get(child_id);child.dataer.append('child memory')
        self.host.backend.save();self.host.close();self.host=TownProject(self.temp.name)
        child=self.host.backend.network.get(child_id)
        self.assertEqual(child.dataer.read(),'child memory')
        self.assertTrue((await self.instantiate())['duplicate'])
        self.assertEqual(child.info.name,'小芽')
        self.assertEqual((await child.modules.get('records.store').read())['values']['name'],'小芽')
        self.assertEqual(len(self.host.backend.network),53)
