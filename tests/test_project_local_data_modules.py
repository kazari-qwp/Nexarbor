"""真实结构化DataNode、通用模块工厂、只读权限和保存冷重开。"""
import json
from pathlib import Path
import sqlite3
import unittest
from app.studio.testing import ModuleHarness
from domain.core import DataNode,NodeInfo
from projects.knowledge_archive.nodes.value import ValueNode
from projects.knowledge_archive.nodes.csv import CsvNode
from projects.knowledge_archive.nodes.sqlite import SqliteNode
from projects.knowledge_archive.nodes.collection import CollectionNode
from projects.knowledge_archive.nodes.vector.node import LlamaIndexNode
ROOT=Path(__file__).resolve().parents[1]
LIBRARY={name:ROOT/'projects/knowledge_archive/modules'/folder for name,folder in [('data.local','data_local'),('data.knowledge','data_knowledge')]}

class LocalDataModules(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h=ModuleHarness(None,library=LIBRARY);self.addAsyncCleanup(self.h.close)
        self.h.backend.saver.node_types.update(value=ValueNode,csv=CsvNode,sqlite=SqliteNode,knowledge_collection=CollectionNode,llamaindex=LlamaIndexNode)

    async def test_actual_file_and_table_tools_survive_cold_reopen_and_reject_readonly_writes(self):
        home=self.h.folder
        (home/'value.json').write_text('0',encoding='utf-8');(home/'table.csv').write_text('id,text\none,original\n',encoding='utf-8')
        db=sqlite3.connect(home/'table.sqlite3');db.execute('CREATE TABLE records(id TEXT PRIMARY KEY,text TEXT)');db.commit();db.close()
        nodes=[ValueNode(NodeInfo('value','JSON'),home/'value.json'),CsvNode(NodeInfo('csv','CSV'),home/'table.csv','id'),SqliteNode(NodeInfo('sqlite','SQLite'),home/'table.sqlite3','records','id')]
        for node in nodes:
            self.assertIsInstance(node,DataNode);self.h.network.add(node);self.h.mount(node.info.node_id,module='data.local')
        for actor,value in [('value',7),('csv',{'text':'new CSV'}),('sqlite',{'text':'new SQLite'})]:
            result=await self.h.call(actor,'write',{'key':'value' if actor=='value' else 'two','value':value},module='data.local')
            self.assertEqual(result['data'].status,'ok')
        await self.h.restart()
        for actor in ('value','csv','sqlite'):
            self.assertEqual(self.h.network.get(actor).node_type,actor)
            result=await self.h.call(actor,'read',{'key':'value' if actor=='value' else 'two'},module='data.local')
            self.assertEqual(result['data'].status,'ok');self.assertTrue(result['data'].items)
        module=self.h.network.get('csv').modules.get('data.local');module.config['read_only']=True
        with self.assertRaisesRegex(PermissionError,'只读'):await self.h.call('csv','write',{'key':'two','value':{'text':'forbidden'}},module='data.local')
        self.assertEqual((await self.h.call('csv','read',{'key':'two'},module='data.local'))['data'].items[0]['text'],'new CSV')
        self.assertEqual(self.h.backend.store.pending(),[])

    async def test_collection_commands_use_installed_local_dependency_and_original_versions(self):
        node=CollectionNode(NodeInfo('wiki','Wiki'),self.h.folder/'wiki');self.h.network.add(node)
        self.h.mount('wiki',module='data.knowledge');self.assertIsNotNone(node.modules.get('data.local'))
        first=await self.h.call('wiki','put',{'key':'guide','value':'# 原始正文'},module='data.knowledge');self.assertEqual(first['data'].status,'ok')
        await self.h.call('wiki','put',{'key':'guide','value':'# 新正文','expected_version':1},module='data.knowledge')
        self.assertEqual(len((await self.h.call('wiki','history',{'key':'guide'},module='data.knowledge'))['data'].items),2)
        node.modules.get('data.local').config['read_only']=True
        with self.assertRaisesRegex(PermissionError,'只读'):await self.h.call('wiki','remove',{'key':'guide'},module='data.knowledge')
        self.assertEqual((await self.h.call('wiki','fetch',{'key':'guide'},module='data.knowledge'))['data'].status,'ok')
        await self.h.restart()
        self.assertEqual(len((await self.h.call('wiki','history',{'key':'guide'},module='data.knowledge'))['data'].items),2)

    def test_each_application_data_node_has_its_actual_serialized_type(self):
        self.assertEqual([cls.node_type for cls in (ValueNode,CsvNode,SqliteNode,CollectionNode,LlamaIndexNode)],['value','csv','sqlite','knowledge_collection','llamaindex'])
