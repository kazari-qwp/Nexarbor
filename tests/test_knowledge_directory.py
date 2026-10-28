"""集合资源归属、跨集合来源与原入库回执的持久化回归。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from domain.core import NodeInfo
from projects.knowledge_archive.nodes.collection import CollectionNode
from projects.knowledge_archive.modules.knowledge_catalog.directory import KnowledgeDirectory

ROOT=Path(__file__).resolve().parents[1]

class KnowledgeDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='knowledge-directory-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.engine=KnowledgeDirectory(self.root/'catalog',owner_node='directory');self.nodes={}

    def collection(self,name,storage='wiki',schema=None):
        item=self.engine.create_collection(name=name,storage=storage,schema=schema)
        node=CollectionNode(NodeInfo('node-'+item['id'],name),self.root/'collections'/item['id'],storage=storage,schema=schema,collection_id=item['id'])
        self.nodes[item['id']]=node;self.engine.bind({key:node.dataer.store for key,node in self.nodes.items()});return item

    def test_owned_files_and_cross_collection_evidence_survive_cold_reopen(self):
        original=self.collection('原文');notes=self.collection('主题')
        source=self.engine.store(original['id'],'# Original\nOriginal complete text',key='source')
        page=self.engine.store(notes['id'],'# Notes',key='notes',sources=[source['id']])
        self.engine.update(source['id'],'# Updated',expected_version=1)
        self.assertTrue(self.engine.fetch(page['id'])['needs_refresh'])
        self.assertEqual(self.engine.fetch(source['id'],version=1)['content'],'# Original\nOriginal complete text')
        with self.engine.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM records').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM versions').fetchone()[0],0)
        for collection,node in self.nodes.items():
            self.assertTrue((node.saver.path/'catalog.sqlite3').exists())
            self.assertTrue((node.saver.path/'sources').exists())
            self.assertFalse(node.saver.path.is_relative_to(self.root/'catalog'))
        reopened=KnowledgeDirectory(self.root/'catalog',owner_node='directory')
        reopened.bind({key:CollectionNode(node.info,node.saver.path,storage=node.dataer.storage,collection_id=key).dataer.store for key,node in self.nodes.items()})
        self.assertEqual(reopened.fetch(page['id'])['node_id'],self.nodes[notes['id']].info.node_id)
        self.assertTrue(reopened.fetch(page['id'])['needs_refresh'])
        reopened.delete(source['id'],expected_version=2)
        self.assertTrue(reopened.fetch(page['id'])['sources'][0]['deleted'])
        self.assertEqual(reopened.fetch(source['id'],version=1)['content'],'# Original\nOriginal complete text')

    def test_mixed_collection_intake_keeps_typed_values_original_bytes_and_idempotent_receipts(self):
        schema={'code':'string','n':'integer'}
        csv=self.collection('CSV','csv',schema);sql=self.collection('SQL','sqlite',schema)
        original=self.root/'original.csv';original.write_bytes(b'code,n\r\n0001,1\r\n')
        intake=self.engine.stage(content=[{'code':str(i).zfill(4),'n':str(i)} for i in range(4)],purpose='archive',original_file=original)
        partial=self.engine.commit_intake(intake['id'],csv['id'],indices=[0,2]);self.assertEqual(partial['remaining_indices'],[1,3])
        done=self.engine.commit_intake(intake['id'],sql['id']);self.assertEqual(len(done['records']),4)
        self.assertEqual(done,self.engine.commit_intake(intake['id'],sql['id']))
        self.assertEqual(self.engine.intake(intake['id'])['status'],'completed')
        for receipt in done['records']:
            record=self.engine.fetch(receipt['id']);self.assertIsInstance(record['content']['n'],int)
            self.assertEqual(len(record['content']['code']),4)
            self.assertEqual(Path(record['origins'][0]['archived_path']).read_bytes(),original.read_bytes())
            self.assertTrue(Path(record['original_path']).is_relative_to(self.nodes[record['collection_id']].saver.path))

    def test_rag_directory_returns_direct_versioned_wiki_location(self):
        wiki=self.collection('原文')
        text='# Overview\nPreface.\n## Target\nThe exact target passage.\n## Other\nOther text.'
        record=self.engine.store(wiki['id'],text,key='doc');store=self.engine.shard(wiki['id'])
        with store.connection() as db:db.execute("UPDATE records SET index_state='ready'")
        passage='The exact target passage.';start=text.index(passage)
        class Index:
            def search(self,query,top_k):
                return SimpleNamespace(items=[dict(metadata={'file_name':record['id']+'.md'},text=passage,start_char=start,end_char=start+len(passage),chunk_id='chunk',score=0.9)])
        store._index=lambda collection:Index()
        hit=self.engine.search('中文语义问题',semantic=True)['items'][0]
        self.assertEqual(hit['entry']['storage'],'wiki');self.assertIn('#L4',hit['wiki_link'])
        reference=hit['read'];self.engine.update(record['id'],'# New text',expected_version=1)
        excerpt=self.engine.fetch(**reference)
        self.assertEqual(excerpt['version'],1);self.assertIn(passage,excerpt['content'])
        self.assertEqual(hit['matches'][0]['read'],reference)

if __name__=='__main__':unittest.main()
