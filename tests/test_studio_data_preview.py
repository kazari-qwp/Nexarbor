"""真实数据预览不改正式图，清空用局部快照并保留原主键/表结构。"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from app.studio.testing import ModuleHarness
from app.studio.data_preview import preview
from app.studio.data_clear import clear_live
from domain.core import NodeInfo
from projects.knowledge_archive.nodes.value import ValueNode
from projects.knowledge_archive.nodes.csv import CsvNode
from projects.knowledge_archive.nodes.sqlite import SqliteNode
ROOT=Path(__file__).resolve().parents[1]
class DataPreview(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h=ModuleHarness(ROOT/'projects/knowledge_archive/modules/data_local');self.addAsyncCleanup(self.h.close)
        self.h.backend.saver.node_types.update(value=ValueNode,csv=CsvNode,sqlite=SqliteNode)
        home=self.h.folder;(home/'table.csv').write_text('id,text\none,original\n',encoding='utf-8')
        self.csv=CsvNode(NodeInfo('csv','正式CSV'),home/'table.csv','id');self.h.network.add(self.csv);self.h.mount('csv')
        self.h.backend.save();self.document=self.h.backend.snapshot();self.record=next(node for node in self.document['network']['nodes'] if node['node_id']=='csv')

    async def test_preview_uses_real_dataer_in_isolation_and_respects_readonly(self):
        result=preview(self.h.backend,dict(node=self.record,files=self.document['files'],operation='write',arguments={'key':'two','value':{'text':'isolated'}}))
        self.assertEqual(result['result']['status'],'ok');self.assertIn('isolated',result['files']['table.csv'])
        self.assertNotIn('isolated',self.csv.dataer.file_path.read_text(encoding='utf-8'))
        self.assertEqual(result['node']['tables'],self.record['tables'])
        readonly=deepcopy(self.record);readonly['tables']['modules'][0]['config']['read_only']=True
        with self.assertRaisesRegex(ValueError,'只读'):preview(self.h.backend,dict(node=readonly,files=self.document['files'],operation='write',arguments={'key':'two','value':{'text':'forbidden'}}))
        escaped=deepcopy(self.record);escaped['data']['path']='../outside.csv'
        with self.assertRaisesRegex(ValueError,'越界'):preview(self.h.backend,dict(node=escaped,files=self.document['files'],operation='clear'))

    async def test_clear_live_keeps_pending_name_header_and_rolls_back_actual_file_on_failure(self):
        original=deepcopy(self.record);original['name']='草稿名称'
        result=await clear_live(self.h.backend,dict(node=original,expected_commit=self.h.backend.store.head))
        self.assertEqual(result['scope'],'live');self.assertTrue(result['rebase_safe']);self.assertEqual(result['node']['name'],'草稿名称')
        self.assertEqual(self.csv.info.name,'正式CSV');self.assertEqual(self.csv.dataer.file_path.read_text().strip(),'id,text')
        self.csv.dataer.file_path.write_text('id,text\nkeep,rollback\n',encoding='utf-8');self.h.backend.save();before=self.csv.dataer.file_path.read_bytes()
        def fail(node,home):node.dataer.file_path.write_text('broken',encoding='utf-8');raise RuntimeError('injected write failure')
        with patch('app.studio.data_clear.clear_node',fail),self.assertRaisesRegex(RuntimeError,'injected'):
            await clear_live(self.h.backend,dict(node=self.record,expected_commit=self.h.backend.store.head))
        self.assertEqual(self.csv.dataer.file_path.read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'网络已变化'):await clear_live(self.h.backend,dict(node=self.record,expected_commit=-1))
        self.assertEqual(self.h.backend.store.pending(),[])

    async def test_value_and_sqlite_previews_restore_actual_structures_and_markdown_read_clear(self):
        home=self.h.folder;(home/'value.json').write_text('5',encoding='utf-8')
        db=sqlite3.connect(home/'data.sqlite3');db.execute('CREATE TABLE records(id TEXT PRIMARY KEY,text TEXT)');db.execute("INSERT INTO records VALUES('one','source')");db.commit();db.close()
        self.h.network.add(ValueNode(NodeInfo('value','JSON'),home/'value.json'))
        self.h.network.add(SqliteNode(NodeInfo('sql','SQLite'),home/'data.sqlite3','records','id'))
        self.h.add_text('text','真实正文');self.h.backend.save();snapshot=self.h.backend.snapshot()
        for id in ('value','sql','text'):
            record=next(node for node in snapshot['network']['nodes'] if node['node_id']==id)
            result=preview(self.h.backend,dict(node=record,files=snapshot['files'],operation='clear'))
            self.assertEqual(result['result']['status'],'ok')
            if id=='value':self.assertIsNone(json.loads(result['files']['value.json']));self.assertEqual((home/'value.json').read_text(),'5')
            elif id=='sql':
                self.assertEqual(result['files']['data.sqlite3']['encoding'],'base64')
                db=sqlite3.connect(home/'data.sqlite3')
                try:self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],1)
                finally:db.close()
            else:
                self.assertEqual(result['files'][record['data']['path']],'');self.assertEqual(self.h.read('text'),'真实正文')
                read=preview(self.h.backend,dict(node=record,files=snapshot['files'],operation='read',arguments={'key':'content'}))
                self.assertEqual(read['result']['items'][0]['content'],'真实正文')


    async def test_directory_clear_preserves_collection_definition_and_resets_vector_storage(self):
        from projects.knowledge_archive.nodes.collection import CollectionNode
        from projects.knowledge_archive.nodes.vector.node import LlamaIndexNode
        self.h.backend.saver.node_types.update(knowledge_collection=CollectionNode,llamaindex=LlamaIndexNode)
        wiki=CollectionNode(NodeInfo('wiki','原集合'),self.h.folder/'wiki');self.h.network.add(wiki)
        wiki.dataer.write('$command',{'operation':'put','arguments':{'key':'guide','value':'# 实际Wiki正文'}})
        definition=wiki.dataer.get_schema()
        vector=LlamaIndexNode(NodeInfo('vector','向量节点'),self.h.folder/'vector',embedding_config={'model_path':str(self.h.folder/'unused-model'),'device':'cpu','max_length':128,'batch_size':2})
        self.h.network.add(vector);self.h.backend.save()
        for id in ('wiki','vector'):
            snapshot=self.h.backend.snapshot();record=next(node for node in snapshot['network']['nodes'] if node['node_id']==id)
            result=await clear_live(self.h.backend,dict(node=record,expected_commit=self.h.backend.store.head))
            self.assertEqual(result['scope'],'live')
        self.assertEqual(wiki.dataer.get_schema()['id'],definition['id'])
        self.assertEqual(wiki.dataer.read({'method':'key','key':'guide'}).status,'not_found')
        self.assertFalse(vector.dataer.has_index())

    async def test_markdown_clear_handles_legacy_backup_and_restores_it_on_failure(self):
        node=self.h.add_text('note','正式正文');backup=node.saver.path.with_name(node.saver.path.name+'.bak')
        relative=backup.relative_to(self.h.folder).as_posix();self.h.backend.write_documents({relative:'旧版备份'});self.h.backend.save()
        snapshot=self.h.backend.snapshot();record=next(entry for entry in snapshot['network']['nodes'] if entry['node_id']=='note')
        from app.studio.data_clear import clear_node
        def fail(target,home):clear_node(target,home);backup.write_text('broken backup',encoding='utf-8');raise RuntimeError('injected backup failure')
        with patch('app.studio.data_clear.clear_node',fail),self.assertRaisesRegex(RuntimeError,'backup failure'):
            await clear_live(self.h.backend,dict(node=record,expected_commit=self.h.backend.store.head))
        self.assertEqual(node.dataer.read(),'正式正文');self.assertEqual(backup.read_text(encoding='utf-8'),'旧版备份')
        result=await clear_live(self.h.backend,dict(node=record,expected_commit=self.h.backend.store.head))
        self.assertEqual(result['scope'],'live');self.assertEqual(node.dataer.read(),'');self.assertFalse(backup.exists())


    async def test_operator_templates_materialize_real_independent_data_and_public_tools(self):
        from app.studio.data_templates import templates
        from app.studio.service import Studio
        from app.studio.network_work import validate_network
        from projects.knowledge_archive.nodes.collection import CollectionNode
        self.h.backend.saver.node_types['knowledge_collection']=CollectionNode
        studio=Studio(self.h.backend,{'data.local':ROOT/'projects/knowledge_archive/modules/data_local','data.knowledge':ROOT/'projects/knowledge_archive/modules/data_knowledge'})
        try:
            values=templates(self.h.backend,studio.library);self.assertEqual([item['id'] for item in values],['value','csv','sqlite','rag','wiki'])
            for item in values:
                snapshot=item['snapshot'];document=validate_network({'network':{'nodes':snapshot['nodes']},'files':snapshot['files']},self.h.backend,studio.library)
                node=document['network']['nodes'][0];self.assertEqual(node['type'],'knowledge_collection' if item['id'] in ('rag','wiki') else item['id'])
                self.assertTrue(node['tables']['modules'][0]['tools']['members'])
                result=preview(self.h.backend,dict(node=node,files=document['files'],operation='inspect'))
                self.assertIsInstance(result['result'],dict)
        finally:studio.close()
