"""历史知识模块的真实文件与网络调用专项；不是完整六阶段应用验收。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from domain.core import Node,NodeInfo,Network,Link,MarkdownNode
from domain.agent import MarkdownAgentNode
from projects.knowledge_archive.modules.knowledge_catalog.module import KnowledgeCatalogModule
from projects.knowledge_archive.modules.knowledge_collection.module import KnowledgeCollectionModule
from projects.knowledge_archive.modules.documents_tasks.module import DocumentsTasksModule
from projects.knowledge_archive.modules.knowledge_tools.module import KnowledgeToolsModule

ROOT=Path(__file__).resolve().parents[1]

class KnowledgeModuleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder=TemporaryDirectory(prefix='knowledge-modules-',dir=ROOT/'build');self.addCleanup(self.folder.cleanup);self.directory=Path(self.folder.name)
        for name in ('memory','input','output'):(self.directory/(name+'.md')).write_text('',encoding='utf-8')
        self.root=MarkdownAgentNode(NodeInfo('root','Root'),self.directory/'memory.md')
        self.catalog_node=Node(NodeInfo('catalog','Catalog'))
        self.input=MarkdownNode(NodeInfo('input','Input'),self.directory/'input.md');self.output=MarkdownNode(NodeInfo('output','Output'),self.directory/'output.md')
        self.network=Network([self.root,self.catalog_node,self.input,self.output])
        self.root.links.add(Link('catalog','knowledge'));self.root.links.add(Link('input','input'));self.root.links.add(Link('output','output'))
        self.created=[]
        async def instantiate(actor,*,template,key,arguments):
            self.assertEqual((actor,template),('catalog','knowledge-collection'))
            endpoint=Node(NodeInfo('collection-'+str(len(self.created)),arguments['label']))
            endpoint.install(KnowledgeCollectionModule({'collection':arguments['collection']},channels=['knowledge'],strength=3))
            endpoint.links.add(Link('catalog','knowledge'));self.network.add(endpoint);self.root.links.add(Link(endpoint.info.node_id,'knowledge'));self.created.append(endpoint)
            return {'node_ids':{'collection':endpoint.info.node_id}}
        self.catalog=KnowledgeCatalogModule(self.directory,instantiate);self.catalog_node.install(self.catalog)
        self.docs=DocumentsTasksModule(self.directory,{'input':'input','output':'output'},channels=['input','output','knowledge'],strength=3)
        self.tools=KnowledgeToolsModule(self.directory,channels=['knowledge'],strength=3)
        self.root.install(self.docs);self.root.install(self.tools)

    async def test_task_inputs_are_immutable_delivery_revision_and_author_are_preserved(self):
        reference=await self.docs.begin(content='original instructions',mode='read')
        self.assertEqual(self.input.dataer.read(),'original instructions')
        await self.docs.reference(intake_id='intake/fixture')
        result=await self.docs.task_document_write(content='answer',expected_revision=0)
        self.assertEqual(result['revision'],1);self.assertEqual(self.output.dataer.read(),'answer')
        delivery=await self.docs.task_document_read(node_id='output')
        self.assertEqual(delivery['author'],'root');self.assertEqual(delivery['references'],['intake/fixture'])
        original=await self.docs.task_document_read();self.assertTrue(original['immutable']);self.assertEqual(original['content'],'original instructions')
        with self.assertRaisesRegex(ValueError,'revision changed'):await self.docs.task_document_write(content='stale',expected_revision=0)
        self.assertEqual(self.output.dataer.read(),'answer')
        self.assertEqual((self.docs.task_directory({'id':reference['task_id']})/'input.md').read_text(encoding='utf-8'),'original instructions')

    async def test_collection_creation_and_access_preserve_record_versions_and_receipts(self):
        await self.docs.begin(content='write archive',mode='write')
        collection=await self.tools.kb_create_node(name='资料',storage='wiki')
        self.assertEqual(collection['node_id'],self.created[0].info.node_id)
        record=await self.tools.kb_store(collection=collection['id'],content='# Original',key='page')
        self.assertEqual((await self.tools.kb_fetch(id=record['id']))['content'],'# Original')
        updated=await self.tools.kb_update(id=record['id'],content='# New',expected_version=1)
        self.assertEqual(updated['version'],2)
        self.assertEqual((await self.tools.kb_fetch(id=record['id'],version=1))['content'],'# Original')
        await self.docs.task_document_write(content='delivery',sources=[record['evidence']],receipts=[record['fetch']])
        self.assertEqual((await self.docs.task_document_read(node_id='output'))['sources'],[record['evidence']])
        with self.assertRaisesRegex(ValueError,'Receipt was not produced'):await self.docs.task_document_write(content='invalid',receipts=[dict(id=record['id'],version=99)])

    async def test_read_only_task_blocks_mutations_and_cannot_read_hidden_collection(self):
        await self.docs.begin(content='prepare archive',mode='write')
        collection=await self.tools.kb_create_node(name='资料',storage='wiki')
        record=await self.tools.kb_store(collection=collection['id'],content='# Stored')
        await self.docs.begin(content='read only',mode='read')
        with self.assertRaisesRegex(ValueError,'read-only'):await self.tools.kb_store(collection=collection['id'],content='# Forbidden')
        self.assertEqual((await self.tools.kb_fetch(id=record['id']))['content'],'# Stored')
        endpoint=self.created[0].info.node_id
        self.root.links.remove(next(edge for edge in self.root.links if edge.target_id==endpoint))
        with self.assertRaises(KeyError):await self.tools.kb_fetch(id=record['id'])
        self.assertEqual((await self.tools.kb_search())['total'],0)

    async def test_csv_intake_keeps_original_file_typed_data_and_task_receipts(self):
        collection=await self.tools.kb_create_node(name='表格',storage='csv',schema={'code':'string','n':'integer'})
        imports=self.directory/'workspace/imports';imports.mkdir(parents=True,exist_ok=True);original=imports/'rows.csv';original.write_text('code,n\n0001,7\n',encoding='utf-8')
        result=await self.tools.kb_ingest(file_path='imports/rows.csv',collection=collection['id'],purpose='archive')
        self.assertEqual(result['status'],'stored')
        receipt=result['records'][0];record=await self.tools.kb_fetch(id=receipt['id'],version=receipt['version'])
        self.assertEqual(record['content'],{'code':'0001','n':7})
        self.assertEqual(Path(record['origins'][0]['archived_path']).read_bytes(),original.read_bytes())
        self.assertEqual((await self.docs.current())['mode'],'write')
        self.assertTrue((await self.docs.task_document_read(node_id='output'))['receipts'])
        with self.assertRaisesRegex(ValueError,'workspace'):await self.tools.kb_ingest(file_path='../outside.csv')
